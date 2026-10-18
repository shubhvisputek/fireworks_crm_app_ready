# Fireworks Business CRM

A self-contained local web application implementing the supplied Firecracker Business CRM/Billing/Inventory/Analytics specification.

## Stack

- Python 3.10+ standard library HTTP server
- SQLite with transactional updates and WAL mode
- HTML/CSS/JavaScript responsive UI
- `openpyxl` for Excel import/export
- `reportlab` for printable PDF invoices

## Run

```bash
cd fireworks_crm
python server.py
```

Open `http://localhost:8000`.

By default the server only listens on this computer (`127.0.0.1`). To reach it from other devices on your network, set `HOST=0.0.0.0` and also set `FIREWORKS_ADMIN_PASSWORD` (at least 12 characters) before the first run; the server refuses to start a network-exposed database with the demo password.

On Windows, double-click `start_network.bat` to do this for you. On first run it asks for the admin password, then shows the address to open on phones and other computers on the same Wi-Fi (for example `http://192.168.1.25:8000`). Allow Python through Windows Firewall on private networks only, keep the window open while the shop is using the CRM, and use it only on your own password-protected Wi-Fi.

For one shared online instance that both computers can use, see [DEPLOYMENT.md](DEPLOYMENT.md). The hosted setup requires a persistent disk and starts with an empty database.

Demo login:

- Username: `admin`
- Password: `admin123`

The database is created automatically at `data/fireworks.db` and demo data is seeded the first time the app runs. Demo data is clearly intended for testing.

## Main workflows included

- One-time CSV/XLSX Product Master import with column mapping, preview, duplicate rejection, and row-level validation
- Product catalogue based on Product ID, name, category, subcategory, brand, unit, default unit selling price, opening stock, and status
- Billing based on quantity × selling unit price, with transaction-only manual price overrides
- Atomic finalized-sale transaction covering invoice, line snapshots, payment allocation and unit-for-unit stock deduction
- Stock-in, stock adjustments, inventory ledger, and safe product removal
- Customer master with automatic creation from manual billing details
- Returns linked to original invoice
- Edit finalized bills (Owner): add/remove items or change quantities; the original is kept as cancelled and linked to the re-issued bill, with editor, timestamp and reason recorded
- "Billed by" on every invoice PDF, the Sales list and Excel exports, plus "Edited by" with date/time for revised bills
- Expense entry and P&L calculations
- Owner dashboard with refill attention and dedicated Sales Analytics page with top/bottom product views
- Sales targets and progress
- PDF invoices with separate customer and seller copies, plus Excel/JSON export
- Settings and audit trail
- Admin-managed staff accounts restricted to Dashboard, Billing, Expenses, Analytics, and Backup & Export
- Collapsible left-side navigation with a mobile drawer
- Responsive/PWA-ready front end

Administrators can create and deactivate staff accounts from the Users menu. Staff permissions are enforced by the server API as well as the navigation.

## Important production notes

This implementation is designed to be runnable immediately without an external package registry. Before using for real financial operations, change the default credentials and deploy behind HTTPS with a proper production process manager/reverse proxy. Product Master prices are final customer-facing unit prices; no tax is calculated or displayed. At invoice finalization, payment allocations must equal the discounted invoice total. Allocations can be recorded as received payment or marked Credit; Credit counts toward sales but is shown separately from money received as the invoice's outstanding amount. Credit is a payment method only; there is no separate credit-management module.

Generated invoice PDFs are stored in the project `bills/` folder. Sales exports and backups are generated on demand and downloaded; they are not kept on the server. Backups do not include password hashes.
