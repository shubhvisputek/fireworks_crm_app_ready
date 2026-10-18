# Architecture

Fireworks CRM is a small, dependency-light web app: a Python standard-library HTTP server with SQLite on the back end, and plain ES modules in the browser. There is no build step and no framework.

## Back end: `crm/`

Code is split into layers. Each layer only calls the layers below it.

```
web/            HTTP adapter, routing, sessions, controllers      ← knows about HTTP
  │
services/       business rules and use cases                       ← knows nothing about HTTP
  │
repositories/   SQL, one module per area                           ← the only place SQL is written
  │
db/             connections, transactions, schema, migrations

domain/         pure helpers used by all layers: money, validation, permissions
exports/        PDF and Excel rendering (pure functions: rows in, bytes out)
```

| Folder | Responsibility | Examples |
|---|---|---|
| `config.py`, `clock.py` | Settings from environment variables; the shop's business day (IST by default, even on a UTC server) | `Config.from_env()`, `Clock.today_iso()` |
| `errors.py` | Errors that carry their HTTP status | `ValidationError` → 400, `NotFoundError` → 404 |
| `security.py` | Password hashing, signed session tokens, login throttling | `hash_password`, `TokenSigner`, `LoginThrottle` |
| `domain/` | Rules with no I/O | `money()`, `allocate_discount()`, `validation.iso_date()`, `Permission`, `ROLE_PERMISSIONS` |
| `db/` | `Database.session()`, `transaction(conn)` (BEGIN IMMEDIATE / COMMIT / ROLLBACK), `schema.migrate()` | |
| `repositories/` | Parameterised SQL returning plain dicts | `InvoiceRepository.list()`, `ProductRepository.get_active()` |
| `services/` | Use cases. Validate input, enforce rules, run inside one transaction, write the audit log | `SalesService.create_sale/void/edit/record_return/collect_payment` |
| `exports/` | Build invoice PDFs, sales report PDF, Excel workbooks in memory | `pdf.invoice_pdf()`, `excel.sales_detailed()` |
| `web/` | `Application.handle(request) → response`, router, controllers, static files | `routes/sales.py` |

### Request flow

1. `web/server.py` receives the socket request and wraps it in a `Request`.
2. `Application.handle()` serves static files, or for `/api/...`:
   - rejects cross-site POSTs (Origin check),
   - finds the route; each route declares the **permission** it needs,
   - loads the user from the signed session cookie and checks the permission,
   - opens one database connection and builds a `Services` container for this request.
3. The controller (e.g. `routes/sales.py:create_sale`) reads the body and calls one service method.
4. The service validates, opens a transaction, calls repositories, writes the audit log and returns plain data.
5. Errors become JSON: `AppError` subclasses use their status and message. Anything unexpected is logged and returned as a generic 500.

### Permissions

`domain/permissions.py` lists every permission and which roles have it. Routes reference permissions, never roles:

```python
router.add('POST', '/api/invoices/{invoice_id}/edit', edit, P.SALES_MANAGE)
```

A route can also require *any one of* several permissions, e.g. `(P.SALES_VIEW, P.SALES_VIEW_OWN)`; the service then decides how much the user sees.

`/api/me` returns the user's effective permission list, and the browser builds its navigation from it.

| Role | Highlights |
|---|---|
| Owner | Everything; role and permissions cannot be changed |
| Manager | Billing, all bills, edit/void/returns, discount approval, products, stock, purchases, suppliers, dues, expenses, reports, all cash closings. No profit, prices, settings, users or backups |
| Cashier | Billing, own bills/held bills/expenses only, customers (view), own cash closing |
| Stock keeper | Products, stock adjustments, purchases, suppliers, reorder plan |
| Accountant | Analytics with profit, all bills (read), collect credit, dues, expenses, reports, supplier payments, all cash closings |
| Staff (legacy) | Exactly the access staff had before roles existed |

Effective permissions are the role preset unless the Owner customised that user (`users.permissions_json`). Changing a user's role or permissions bumps their session version, which signs them out everywhere.

**Data rules enforced in services, not just routes:**
- Without *See all bills*, invoice lists, details and PDFs are limited to bills the user made (`SalesService.visible_invoice`).
- Held bills and expenses are limited to the user's own unless they have the wider permission.
- The dashboard's analytics (`InsightService`, `GET /api/insights`) add each section only when the user may see it (customers/stock/finance need *Sales analytics*, team needs *See all bills*, credit ageing needs *Credit dues list*). Without *Sales analytics* the sales and product views count only the user's own bills.
- `Service.visible()` strips cost and profit fields (`domain/visibility.py`) from dashboards, analytics, product details, purchases, the reorder plan and the JSON backup for users without *See cost, profit and margins*. The detailed Excel export drops its cost columns too.
- Big discounts are checked in `SalesService._discount_approval`; approver passwords are throttled like logins.
- **Sessions and sign-in:** every cookie carries a random session id; logging out revokes it on the server (`revoked_sessions`). A restore rotates the signing key, so every old session ends. Wrong passwords only ever pause *that username* on *that browser* (`AuthService.login`): a browser where the user signed in before carries a signed `fw_device` cookie and only its own mistakes count; elsewhere failures count per username + address (10) and per username across untrusted places (100). Other users are never affected. Unknown usernames run the same password hash as known ones.
- **Accounts:** only an owner can change, reset or deactivate an owner; nobody can change their own role or permissions, or give access they don't have themselves (`UserService._guard_*`). Restoring a backup is owner-only, because a backup can contain any accounts.
- **Requests:** unknown `Host` names are refused (DNS rebinding; extra names via `FIREWORKS_ALLOWED_HOSTS`). POSTs must come from this site (Origin, or Referer when Origin is missing) and be JSON or an upload. The server handles at most 64 connections at once and drops clients silent for 30 seconds.
- The licence storage limit is checked in `InventoryService.check_storage` for purchases, positive adjustments, opening stock and imports. Confirmed overrides are audited.

**Backups** (`crm/backups.py`): `BackupManager` takes consistent snapshots with SQLite's online backup API. `DailyBackupThread` checks hourly and keeps the configured number of daily backups. A restore validates the file (integrity check and required tables), takes a `-prerestore` safety copy, then copies the backup into the live database.

### Data and migrations

- `db/schema.py` holds the base schema, which matches the original app so existing databases keep working, plus numbered migrations recorded in `schema_migrations`. To change the schema, add a function and append `(next_number, function)` to `MIGRATIONS`.
- Money is stored in rupees and rounded half-up to paise (`domain/money.py`). Bill discounts are split across lines in whole paise, so line totals always add up exactly.
- Bills are never edited in place. An edit voids the original and issues a new linked bill. Voids and returns are separate records, so the history always shows what happened.
- Several product columns (GST, MRP, retail/wholesale price, units per box) are left over from an earlier design. They are kept for old data and hidden from the API.

## Front end: `static/js/`

```
main.js           bootstrap: session, login, page rendering, account actions
core/html.js      html`` template tag: every interpolated value is escaped unless it is html``/raw()
core/api.js       fetch wrapper; errors carry the server message
core/actions.js   event delegation: markup uses data-action / data-change / data-input / data-submit
core/router.js    hash routes; pages declare their permission
core/state.js     shared state (user, products, customers, settings), can(permission)
core/format.js    money/number/date formatting (IST)
ui/               layout (sidebar + top bar), modal/toast/forms, small widgets (kpi, table)
ui/charts.js      SVG/HTML charts (line, columns, bars, stacked bar, heatmap, waterfall, meter, stat tile) and the shared tooltip
billing/cart.js   pure bill arithmetic, mirroring the server
billing/bill.js   the bill being built (new, resumed, or an edit of a finalized bill)
pages/*.js        one module per screen; each calls registerPage({name, label, permission, render})
```

There is no inline JavaScript anywhere: no `onclick=` and no inline `<script>`. That allows the Content-Security-Policy to use `script-src 'self'`, so even a missed escape cannot run an injected script. Combined with the escaping `html` tag, this closes off the stored-XSS bugs the old UI had.

### Screen sizes

Breakpoints (in `static/overrides.css`, the last section is the responsive layer): phones ≤ 560px, card tables ≤ 640px, large phones ≤ 760px, drawer navigation ≤ 1024px (also `isMobile()` in `ui/layout.js`), desktop above. Tables need no per-page work for phones: `ui/responsive.js` copies each column header into a `data-label` on its cells, and CSS shows those labels when rows become cards. The e2e suite opens every page at 320, 390, 768, 1024 and 1440px and fails if anything is wider than the screen.

### Themes and UI building blocks

- `static/themes.css` (loaded last) holds the themes as **tokens**: one block of CSS variables per theme (`:root[data-theme="…"]`), a shared dark block (`:root[data-mode="dark"]`) with each theme's dark accent, and component rules that use only tokens. A new theme is a new block of values plus its name in `THEMES` (`crm/services/settings.py`) and `core/theme.js`.
- `core/theme.js` sets `data-theme` (the shop's `theme` setting, sent to every user in `/api/me` → `limits.theme`) and `data-mode` (each person's choice in `localStorage`, defaulting to the device setting). It also swaps the chart palette (`setChartMode` in `ui/charts.js`) and redraws the dashboard.
- `ui/icons.js`: line icons; pages pass `icon` and `group` to `registerPage`, and the sidebar draws section labels.
- `ui/feedback.js`: `toast(message, 'success' | 'error' | 'info')` and `confirmDialog({title, message, confirmLabel, danger})`, which resolves `true`/`false` and has its own layer so it never closes an open form.
- `core/actions.js`: an async action disables its button (with a spinner) until it finishes, so a double click can't save twice. `core/api.js` shows a thin loading bar for slow requests.
- `ui/widgets.js` `table()` + `ui/lists.js`: lists over 10 rows get a search box; over 50 rows show 50 at a time with "Show more". Pass `{ search: false }` when the page has its own search.
- Printing: `static/print.html` frames `/api/invoice-pdf/<id>` or `/api/invoice-receipt/<id>` and calls `print()`. Only those two responses send `X-Frame-Options: SAMEORIGIN` and `frame-ancestors 'self'`; everything else stays `DENY`.

### Charts

`ui/charts.js` draws every chart as inline SVG or plain HTML, so there is no chart library and nothing breaks the CSP. The rules it follows:

- Categorical colours come from one validated palette (`SERIES`) in a fixed order, and follow the entity: a payment mode or category keeps its colour whatever the filter. Magnitude (the heatmap) uses one blue ramp; ordered buckets (credit age) use its ordinal steps.
- One y-axis per chart. Thin marks, 4px rounded bar ends, 2px gaps between touching fills. Labels use ink colours, never the series colour.
- A legend for two or more series; values are labelled selectively (the peak or the latest point).
- A hover/focus tooltip on every mark (a crosshair on line charts, arrow keys move it), and a "Show as table" view. Labels in the tooltip are set with `textContent`.
- Charts are drawn at the card's pixel width (the dashboard measures it and redraws on resize), so text stays readable on phones.

## Adding a feature (example: "supplier list")

1. **Repository**: add SQL methods to `repositories/misc.py` (or a new module, wired into `Repositories`).
2. **Service**: add a `SupplierService` in `services/`, register it in `services/__init__.py`, and put validation and rules there.
3. **Permission**: add `SUPPLIERS_MANAGE` to `Permission` and to the roles that should have it.
4. **Route**: add `web/routes/suppliers.py` with thin controllers and register it in `web/routes/__init__.py`.
5. **Page**: add `static/js/pages/suppliers.js` calling `registerPage(...)`, and import it in `main.js`.
6. **Tests**: add API tests to `tests/test_api.py`, rule tests to `tests/test_services.py`, and a step to `tests/e2e/app.e2e.mjs`.

## Tests

Run everything with `./run_tests.sh`.

| Suite | What it covers |
|---|---|
| `tests/test_api.py` | Black-box HTTP tests against the real server: every endpoint, the staff/owner permission matrix, security headers, CSRF, throttling, the bill lifecycle |
| `tests/test_services.py` | Business rules in-process: money rounding, IST business day, profit from cost price, stock checks, settings validation, demo data |
| `tests/test_migration.py` | Builds a database with the previous single-file server (from git history) and checks the new server reads and extends it |
| `tests/frontend/cart.test.mjs` | Cart arithmetic and HTML escaping (`node --test`) |
| `tests/e2e/app.e2e.mjs` | Every screen in Chromium as admin and as staff, with the strict CSP. Fails on any page error or CSP violation |
