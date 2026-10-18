# Fireworks Business CRM

Billing, inventory, expenses and sales analytics for a fireworks shop. It runs as a small local web app (or one shared hosted instance) and works in any browser on a computer, tablet or phone.

## Stack

- Python 3.10+ standard-library HTTP server, SQLite (WAL mode, explicit transactions)
- `openpyxl` (Excel import/export), `reportlab` (PDF invoices and reports), `defusedxml` (safe spreadsheet parsing)
- Plain HTML/CSS and JavaScript ES modules. No framework and no build step.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the code is organised and how to add a feature.

## Run

```bash
pip install -r requirements.txt
python server.py
```

Open `http://localhost:8000` and sign in as `admin` / `admin123`, then change the password with the **Password** button.

- The database is created automatically at `data/fireworks.db`. Set `FIREWORKS_SEED_DEMO=1` on the first run to load sample products, customers and bills for testing.
- By default the server only listens on this computer (`127.0.0.1`). To use it from other devices on your Wi-Fi, set `HOST=0.0.0.0` and `FIREWORKS_ADMIN_PASSWORD` (12+ characters). The server refuses to go on the network while any account still uses the demo password.
- On Windows, double-click `start_network.bat` to do this for you. On first run it asks for the admin password, then shows the address to open on phones and other computers (for example `http://192.168.1.25:8000`). Allow Python through Windows Firewall on **private** networks only, and use it only on your own password-protected Wi-Fi.
- For one shared online instance, see [DEPLOYMENT.md](DEPLOYMENT.md).

| Environment variable | Default | Purpose |
|---|---|---|
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Where the server listens |
| `FIREWORKS_DATA_DIR` | `./data` | Folder for the database and session key |
| `FIREWORKS_DB`, `FIREWORKS_SECRET` | inside the data folder | Override individual file paths |
| `FIREWORKS_ADMIN_PASSWORD` | – | Password for the first `admin` account (12+ characters) |
| `FIREWORKS_REQUIRE_ADMIN_PASSWORD` | off | `1` refuses to create a database without the password above |
| `FIREWORKS_TIMEZONE` | `Asia/Kolkata` | Business day used for bill and report dates |
| `FIREWORKS_SECURE_COOKIES` | off | `1` when served over HTTPS |
| `FIREWORKS_SEED_DEMO` | off | `1` loads demo data into an empty database |
| `FIREWORKS_BACKUP_DIR` | `data/backups` | Where daily and manual database backups are kept |
| `FIREWORKS_AUTO_BACKUP` | on | `0` turns off the automatic daily backup |

## Features

- **Billing:** search by Product ID or name (Enter or a barcode scanner adds the exact match), quantities, bill discount (5/10/15% or an amount), hold and resume bills, split payments including Credit, and a printable PDF with customer and seller copies.
- **Edit bills (administrator):** add or remove items and change quantities. The original bill is kept as cancelled and linked to the re-issued bill, with editor, time and reason recorded.
- **Billed by / Edited by:** shown on every invoice PDF, the Sales list and Excel exports.
- **Sales:** collect outstanding credit, return items (stock goes back), void bills, and view cancelled and edited bills.
- **Products:** one-time CSV/Excel product master import with column mapping, preview and all-or-nothing validation. Add products, set the cost price used for profit reports, remove or archive products.
- **Inventory:** purchases/GRN (updates the cost price), stock adjustments, stock removal, per-product stock ledger, low-stock alerts.
- **Customers:** customer master. Customers are also created automatically from a name or mobile number typed on a bill.
- **Expenses** and recurring expense templates; **dashboard** and **analytics** (sales, gross profit after cost of goods, net profit after expenses, top/bottom products, payment mix, presets including the configured season).
- **Settings**, sales targets, invoice prefix and footer; audit log of every change.
- **Roles and permissions:** Owner, Manager, Cashier, Stock keeper, Accountant (plus "Staff (legacy)" for accounts created earlier, which keep their old access). The Owner can tick or untick individual permissions per person. The server enforces every rule, not just the menu:
  - Cashiers see only **their own** bills, held bills and expenses.
  - Cost price, profit, margins and stock value are removed from every response unless the user has *See cost, profit and margins*.
  - Changing someone's role or permissions signs them out so the new access applies immediately.
- **Discount approval:** discounts above the limit in Settings (default 10%) need a manager's username and password at the counter. The approver is recorded on the bill.
- **Day-end cash closing:** each cashier sees the cash, UPI and card they took since their last closing (minus refunds and cash expenses), enters the counted cash, and the difference is recorded. Managers and accountants see everyone's closings.
- **Credit dues:** who owes what, oldest bills first, with **Collect** and a **WhatsApp reminder** message.
- **Suppliers:** supplier list with balance owed, purchase ledger and supplier payments. Purchases (GRN) can include several products and create the supplier automatically.
- **Seasonal reorder plan:** last season's sales plus expected growth, minus stock in hand, per product, with estimated cost.
- **Barcodes:** set a barcode per product; scanning it in Billing adds the item.
- **Thermal receipts and WhatsApp:** 80 mm receipt PDF (choose A4 or 80 mm in Settings for after-billing printing); send a bill summary to the customer on WhatsApp.
- **Licence storage limit:** set explosive content per product (kg) and the licence limit in Settings. Stock-in that would exceed it asks for confirmation, and the dashboard warns when over.
- **Audit log:** every change, who made it and when, with before/after details. Filter by date, user and area.
- **Backups:** an automatic database backup every day (keeps the last 30 by default), **Backup now**, download, and **restore** from the list or from a file (a safety copy is taken first). Also JSON export, summary and detailed Excel, PDF sales report.

## Tests

```bash
./run_tests.sh
```

This runs the API, business-rule and database-upgrade tests (Python), the frontend unit tests (Node), and a full browser test of every screen (Playwright, skipped if not installed).

## Production notes

- Prices in the product master are final customer-facing unit prices. No tax is calculated or shown.
- At finalisation, payments must add up to the bill total after discount. Credit counts as sales and is tracked as the bill's outstanding amount until collected.
- Serve over HTTPS when hosted (`FIREWORKS_SECURE_COOKIES=1`), keep one instance per database (SQLite), and download regular backups. The JSON backup has no restore screen yet.
