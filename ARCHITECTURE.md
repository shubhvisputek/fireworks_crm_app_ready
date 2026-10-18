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

`/api/me` returns the user's permission list, and the browser builds its navigation from it. Adding a role such as *Manager* or *Cashier* means adding one entry to `ROLE_PERMISSIONS`. No routes or pages change.

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
ui/               layout (sidebar + top bar), modal/toast/forms, small widgets (kpi, table, chart)
billing/cart.js   pure bill arithmetic, mirroring the server
billing/bill.js   the bill being built (new, resumed, or an edit of a finalized bill)
pages/*.js        one module per screen; each calls registerPage({name, label, permission, render})
```

There is no inline JavaScript anywhere: no `onclick=` and no inline `<script>`. That allows the Content-Security-Policy to use `script-src 'self'`, so even a missed escape cannot run an injected script. Combined with the escaping `html` tag, this closes off the stored-XSS bugs the old UI had.

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
