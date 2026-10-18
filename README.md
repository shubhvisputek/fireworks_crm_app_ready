# Fireworks Business CRM

Billing, inventory, expenses and sales analytics for a fireworks shop. It runs as a small local web app (or one shared hosted instance) and works in any browser on a computer, tablet or phone.

## Stack

- Python 3.10+ standard-library HTTP server, SQLite (WAL mode, explicit transactions)
- `openpyxl` (Excel import/export), `reportlab` (PDF invoices and reports), `defusedxml` (safe spreadsheet parsing)
- Plain HTML/CSS and JavaScript ES modules. No framework and no build step.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the code is organised and how to add a feature.

## Run

**You need:** Python 3.10 or newer ([python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH"). The launcher checks everything else and installs the three Python packages for you.

| Computer | Double-click | Or in a terminal |
|---|---|---|
| Windows | `start.bat` | `start.bat start` |
| macOS | `start.command` | `./start.sh start` |
| Linux | `start.sh` | `./start.sh start` |

With no options the launcher shows the requirements check, the status (data folder, accounts, backups, whether it is running) and a menu:

```
  1) Start on this computer only
  2) Start and share on the shop Wi-Fi (phones, tablets, other PCs)
  3) Set up / replace the administrator (force re-setup)
  4) Check requirements and status
  5) Install or repair requirements
  6) Back up the data now
  7) List backups
  8) Restore a backup
  9) Run the tests
  h) Help: every command, for scripts and shortcuts
```

- **First run:** it asks for the administrator username, password (typed twice, hidden) and shop name, then starts the app and opens the browser. Weak passwords such as `admin123` are refused.
- **Forgot the admin password / locked out:** choose **3**, or run `setup --force` (same as `reset-admin`). Type the existing username to give it a new password (it is made an active owner and signed out everywhere), or a new username to add another owner. A leftover demo `admin`/`admin123` account is switched off.
- **Share on Wi-Fi:** choose **2** or run `start --network`. It shows the addresses to open on phones (for example `http://192.168.1.25:8000`). Use only your own password-protected Wi-Fi; on Windows allow Python on **private** networks only.
- **If port 8000 is busy** it picks the next free port and says which. If the app is already running it just opens it.
- **Missing packages:** it offers to install them. If this Python does not allow installing packages (some Linux and Homebrew setups), it creates a private `.venv` folder and uses it automatically from then on.

Every menu item is also a command that runs straight away without questions, for shortcuts and scripts (`python fireworks.py` works on every system too):

```bash
./start.sh help                                    # every command and option
./start.sh start --network --port 8080 --no-browser
./start.sh check                                   # exit code 0 = ready to run
./start.sh backup ; ./start.sh backups ; ./start.sh restore fireworks-20261018-210000-manual.sqlite --yes
# First run or admin reset with no questions (password from standard input or FIREWORKS_ADMIN_PASSWORD):
echo "$ADMIN_PASSWORD" | ./start.sh start --admin-user owner --shop-name "Shree Fireworks" --password-stdin --install --yes
echo "$ADMIN_PASSWORD" | ./start.sh reset-admin --admin-user owner --password-stdin
```

Options: `--data-dir` (another data folder), `--port`, `--network`, `--no-browser` / `--open`, `--demo` (sample data in an empty shop), `--no-backup`, `--reset-admin` (on `start`), `--install`, `--yes`. Exit codes: 0 done, 1 problem, 2 the administrator must be set up first.

Still works the old way: `pip install -r requirements.txt` then `python server.py` (demo login `admin` / `admin123`); `start_windows.bat`, `start_network.bat` and `run.sh` now open the launcher. For one shared online instance, see [DEPLOYMENT.md](DEPLOYMENT.md).

| Environment variable | Default | Purpose |
|---|---|---|
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Where the server listens |
| `FIREWORKS_DATA_DIR` | `./data` | Folder for the database and session key |
| `FIREWORKS_DB`, `FIREWORKS_SECRET` | inside the data folder | Override individual file paths |
| `FIREWORKS_ADMIN_PASSWORD` | – | Password for the first `admin` account (12+ characters); the launcher also reads it for `setup`/`start` |
| `FIREWORKS_REQUIRE_ADMIN_PASSWORD` | off | `1` refuses to create a database without the password above |
| `FIREWORKS_TIMEZONE` | `Asia/Kolkata` | Business day used for bill and report dates |
| `FIREWORKS_SECURE_COOKIES` | off | `1` when served over HTTPS |
| `FIREWORKS_SEED_DEMO` | off | `1` loads demo data into an empty database |
| `FIREWORKS_BACKUP_DIR` | `data/backups` | Where daily and manual database backups are kept |
| `FIREWORKS_AUTO_BACKUP` | on | `0` turns off the automatic daily backup |
| `FIREWORKS_ALLOWED_HOSTS` | – | Extra host names the app answers to, e.g. your domain behind HTTPS. IP addresses, `localhost`, one-word computer names and `.local` names always work |
| `FIREWORKS_TRUST_PROXY` | off | `1` only behind your own reverse proxy: take the visitor's address from `X-Forwarded-For` (for login throttling) |

## Features

- **Billing:** search by Product ID or name (Enter or a barcode scanner adds the exact match), quantities, bill discount (5/10/15% or an amount), hold and resume bills, split payments including Credit, and a printable PDF with customer and seller copies.
- **Edit bills (administrator):** add or remove items and change quantities. The original bill is kept as cancelled and linked to the re-issued bill, with editor, time and reason recorded.
- **Billed by / Edited by:** shown on every invoice PDF, the Sales list and Excel exports.
- **Sales:** collect outstanding credit, return items (stock goes back), void bills, and view cancelled and edited bills.
- **Products:** one-time CSV/Excel product master import with column mapping, preview and all-or-nothing validation. Add products, set the cost price used for profit reports, remove or archive products.
- **Inventory:** purchases/GRN (updates the cost price), stock adjustments, stock removal, per-product stock ledger, low-stock alerts.
- **Customers:** customer master. Customers are also created automatically from a name or mobile number typed on a bill.
- **Expenses** and recurring expense templates.
- **Dashboard with analytics:** pick a period (today, yesterday, last 7/30 days, this/last month, season or any dates); every number is compared with the period before it. Tabs show each point of view, and only the tabs a person's permissions allow:
  - **Overview:** headline numbers with change and trend, sales by day vs the previous period, target progress, payment mix, top products, what needs attention.
  - **Sales:** discounts, credit given, deleted/edited/returned bills, sales by hour, a weekday × hour heatmap of busy times, bill sizes, payment modes.
  - **Products:** revenue and margin by category, top 10 and most profitable products, rising and falling products, slowest sellers, how concentrated sales are.
  - **Customers & credit:** retail vs wholesale, new vs repeat customers, top customers, credit outstanding by age.
  - **Team:** sales, bills, average bill, discounts, deletions, edits and refunds per person.
  - **Stock:** stock value by category, out of stock and low stock, products running out at the current pace, stock that is not selling, licence storage.
  - **Finance:** sales → cost of goods → gross profit → expenses → net profit, sales and profit by day, expenses by category and by day, daily/weekly/monthly/season targets.
  - Cashiers see the same views for **their own bills only**. Charts have hover tooltips and a "Show as table" view.
- **Settings**, sales targets, invoice prefix and footer; audit log of every change.
- **Roles and permissions:** Owner, Manager, Cashier, Stock keeper, Accountant (plus "Staff (legacy)" for accounts created earlier, which keep their old access). The Owner can tick or untick individual permissions per person. The server enforces every rule, not just the menu:
  - Cashiers see only **their own** bills, held bills and expenses.
  - Cost price, profit, margins and stock value are removed from every response unless the user has *See cost, profit and margins*.
  - Changing someone's role or permissions signs them out so the new access applies immediately.
- **Discount approval:** discounts above the limit in Settings (default 10%) need a manager's username and password at the counter. The approver is recorded on the bill.
- **Day-end cash closing:** each cashier sees the cash, UPI and card they took since their last closing (minus refunds and cash expenses), enters the counted cash, and the difference is recorded. Managers and accountants see everyone's closings.
- **Credit dues:** who owes what, oldest bills first, with **Collect**. (WhatsApp reminders are switched off for now; see below.)
- **Suppliers:** supplier list with balance owed, purchase ledger and supplier payments. Purchases (GRN) can include several products and create the supplier automatically.
- **Seasonal reorder plan:** last season's sales plus expected growth, minus stock in hand, per product, with estimated cost.
- **Barcodes:** set a barcode per product; scanning it in Billing adds the item.
- **Thermal receipts:** 80 mm receipt PDF (choose A4 or 80 mm in Settings for after-billing printing).
- **WhatsApp (switched off):** the bill-summary and dues-reminder buttons are hidden. To turn them back on, set `WHATSAPP_ENABLED = true` in `static/js/ui/share.js`.
- **Licence storage limit:** set explosive content per product (kg) and the licence limit in Settings. Stock-in that would exceed it asks for confirmation, and the dashboard warns when over.
- **Wrong passwords:** after 10 wrong passwords, that username is paused for 15 minutes *on that browser or computer only*. Other users can still sign in, and the person's own usual browser (where they signed in before) keeps working even if someone else is guessing their password in another window.
  - **Unlock:** in **Users**, a locked person shows a red **Locked** tag; press **Unlock** and they can sign in at once. Resetting someone's password also unlocks them.
  - **Switch it off:** **Settings → Wrong-password lockout → Off** stops anyone ever being locked out (wrong passwords still never sign anyone in). Leaving it on is safer when the app is reachable from the internet.
- **No tax:** prices are final; the app does not calculate or show GST or any other tax.
- **Audit log:** every change, who made it and when, with before/after details. Filter by date, user and area.
- **Backups:** an automatic database backup every day (keeps the last 30 by default), **Backup now**, download, and **restore** from the list or from a file (a safety copy is taken first). Also JSON export, summary and detailed Excel, PDF sales report.

## Look and feel

- **Themes (owner):** Settings → Appearance offers six looks: Classic, Clean & calm, Festive brand, Counter pro (high contrast, big touch targets), Royal Diwali and Soft modern. Click one to preview it; it applies to everyone after **Save Settings**.
- **Dark mode (each person):** the moon/sun button in the top bar. It follows the phone or computer setting until someone switches, and is remembered on that device. Charts switch to their own dark colours.
- **Menu:** icons and sections (Overview, Sell, Stock, People & money, Admin).
- **Billing counter:** keyboard shortcuts (<kbd>F2</kbd> product search, <kbd>↑</kbd>/<kbd>↓</kbd> + <kbd>Enter</kbd> to pick, <kbd>F4</kbd> customer, <kbd>F8</kbd> hold, <kbd>F9</kbd> pay and again to finalize, <kbd>Esc</kbd> close), a large "Total to pay", a **change calculator** (cash received → change to give back), and a print choice on the payment screen (**A4 invoice**, **80 mm receipt** or **Don't print**, remembered per device). Printing opens the bill in a print page that brings up the print dialog by itself.
- **Lists:** long lists have a search box and show 50 rows at a time with **Show more**.
- **Feedback:** buttons show a spinner and can't be pressed twice while saving; "are you sure?" dialogs say exactly what will happen; green/red messages for success and problems; friendly empty screens with the next step.

## Screen sizes

Every screen works from small phones (320px) through tablets to large desktops:

- **Phones (up to 640px):** navigation opens from the ☰ button; the top bar keeps one row with icon buttons (🔑 password, ⏻ logout); tables turn into cards with each value labelled; dialogs slide up from the bottom; two headline numbers per row.
- **Tablets (up to 1024px):** the same slide-out navigation, so pages use the full width; tables and two-column layouts as on desktop where they fit.
- **Desktop:** fixed sidebar (can be collapsed with ☰), wider content up to 1600px on large screens.

## Tests

```bash
./run_tests.sh        # or, on any system: python fireworks.py test
```

This runs the API, business-rule and database-upgrade tests (Python), the frontend unit tests (Node), and a full browser test of every screen (Playwright, skipped if not installed).

## Production notes

- Prices in the product master are final customer-facing unit prices. No tax is calculated or shown.
- At finalisation, payments must add up to the bill total after discount. Credit counts as sales and is tracked as the bill's outstanding amount until collected.
- Serve over HTTPS when hosted (`FIREWORKS_SECURE_COOKIES=1`), keep one instance per database (SQLite), and download regular backups. The JSON backup has no restore screen yet.
