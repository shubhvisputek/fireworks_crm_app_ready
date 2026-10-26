# Fireworks CRM Test Cases

> Most of these checks are now automated: run `./run_tests.sh` (API, business rules, database upgrade, and a browser test of every screen). See the Tests section of ARCHITECTURE.md. This list remains for manual acceptance testing; GST-related rows refer to an earlier design and no longer apply.

## Test Setup

- URL: `http://localhost:8000`
- User: `admin`
- Password: `admin123`
- Browser: Chromium/Edge, fresh session
- Data: demo database or isolated test database
- Rule baseline: wholesale-only sales, optional manually entered customer name/mobile, no GST, Credit is a payment allocation only (no credit-management module)

## Execution Status

| ID | Area | Expected result | Status |
|---|---|---|---|
| AUTH-01 | Login with valid credentials | Dashboard opens | Pending |
| AUTH-02 | Login with invalid credentials | Error toast; no session | Pending |
| AUTH-03 | Logout | Login screen opens and session is cleared | Pending |
| DASH-01 | Dashboard KPI cards | Sales, profit, expenses, low stock render | Pending |
| DASH-02 | Sales progress | Target/progress renders without errors | Pending |
| DASH-03 | Inventory snapshot | Cost, low stock, bills render; no retail/GST/dues | Pending |
| DASH-04 | Owner attention | At most 10 refill items, ordered by urgency | Pending |
| DASH-05 | Dashboard API | No `hourly` or `pending_dues` fields | Pending |
| NAV-01 | Every sidebar navigation button | Each route opens its correct screen | Pending |
| NAV-02 | New Bill button | Billing opens with an empty bill | Pending |
| BILL-01 | Optional customer name/mobile | Fields accept blank or manual values | Pending |
| BILL-02 | Product search | Matching products appear; no results message works | Pending |
| BILL-03 | Add product | Product enters cart once; repeated add increments quantity | Pending |
| BILL-04 | Quantity/unit/discount edits | Cart and total recalculate correctly | Pending |
| BILL-05 | Wholesale pricing | Wholesale rate is used; retail selector is absent | Pending |
| BILL-06 | GST-free total | No GST row; total equals taxable amount after discount | Pending |
| BILL-07 | Payment modal | Cash/UPI/Card/Credit/Other rows work | Pending |
| BILL-08 | Credit allocation | Mixed or all-Credit allocations complete the full sale; Credit is outstanding, not received | Pending |
| BILL-09 | Finalize invoice | Invoice, payment, stock deduction, and PDF with customer/seller copies open | Pending |
| BILL-10 | Hold Bill | Bill is saved and cart clears | Pending |
| BILL-11 | Held Bills/Resume | Held bill list opens and restores items | Pending |
| BILL-12 | Held Bills/Delete | Held bill is removed | Pending |
| SALES-01 | Invoice list | Finalized invoices load with customer, total, received | Pending |
| SALES-02 | Invoice PDF button | PDF opens with separately labeled customer and seller copies and no GST fields | Pending |
| SALES-03 | Return button | Valid return restores stock and records refund | Pending |
| SALES-04 | Invalid return | Invalid quantity is rejected with an error | Pending |
| PRODUCTS-01 | Product search prompt | Search filters products | Pending |
| PRODUCTS-02 | Add Product button | Valid wholesale product saves | Pending |
| PRODUCTS-03 | Add Product validation | Missing SKU/name is rejected | Pending |
| PRODUCTS-04 | Product Master Import | CSV/XLSX upload, preview, mapping, and confirmation work | Pending |
| PRODUCTS-05 | Product detail/View | Product, wholesale price, cost, stock, and ledger open | Pending |
| INVENTORY-01 | Current stock table | Stock, reorder, value, and status render | Pending |
| INVENTORY-02 | Add Stock/GRN | Purchase increases stock; no GST input/calculation | Pending |
| INVENTORY-03 | Stock Adjustment | Positive/negative adjustments update stock | Pending |
| INVENTORY-04 | Negative stock validation | Disallowed negative adjustment is rejected | Pending |
| CUSTOMERS-01 | Customer list | Existing customers render without credit/dues columns | Pending |
| CUSTOMERS-02 | Add Customer | Name/phone/address/notes save; name required | Pending |
| EXPENSES-01 | Expense list | YTD expenses and entries render | Pending |
| EXPENSES-02 | Add Expense | Valid expense saves | Pending |
| EXPENSES-03 | Expense validation | Zero/negative amount is rejected | Pending |
| EXPENSES-04 | Recurring button | Recurring workflow gives expected response | Pending |
| EXPENSES-05 | Edit expense | Changed fields save and the list updates | Pending |
| EXPENSES-06 | Delete expense | Confirm dialog, then the entry is removed | Pending |
| EXPENSES-07 | Own-only rule | Cashier cannot edit/delete another user's expense (403) | Pending |
| EXPENSES-08 | Recurring manage | Edit, pause/resume and delete a recurring template | Pending |
| PRICING-01 | Pricing list | Wholesale and cost columns render; retail absent | Pending |
| PRICING-02 | Change Product Price | Wholesale price version saves | Pending |
| PRICING-03 | Bulk Price Update | Wholesale percentage update saves | Pending |
| ANALYTICS-01 | Analytics presets | Today/yesterday/7d/month/season reload data | Pending |
| ANALYTICS-02 | Analytics tables | Top products, payments, customer/revenue data render | Pending |
| ANALYTICS-03 | Analytics tax/credit | No GST or credit-management metrics appear; Credit allocations count toward sales | Pending |
| SETTINGS-01 | Settings load | Business and target fields render | Pending |
| SETTINGS-02 | Save Settings | Business/target changes persist | Pending |
| SETTINGS-03 | Tax removal | GST fields are absent; saved tax values remain zero | Pending |
| SETTINGS-04 | Change password | Valid password change succeeds; short password rejected | Pending |
| BACKUP-01 | Full Backup link | JSON backup downloads | Pending |
| BACKUP-02 | Excel export link | XLSX downloads and opens | Pending |
| BACKUP-03 | PDF export link | PDF downloads and opens | Pending |
| API-01 | Auth endpoints | `/api/me`, login, logout return correct status | Pending |
| API-02 | Product/customer endpoints | List, search, create, and detail contracts work | Pending |
| API-03 | Sales contract | Wholesale, zero tax, payment allocations equal total, Credit excluded from received, stock deduction | Pending |
| API-04 | Inventory/purchase/return contracts | Transactions are atomic and validated | Pending |
| API-05 | Export contracts | XLSX/PDF/backup responses have valid content types | Pending |
| UI-01 | Browser console | No page errors on login or every route | Pending |
| UI-02 | Responsive layout | Desktop and mobile layouts have no overlap or clipped controls | Pending |
| UI-03 | Typography | Text is readable at the updated larger size | Pending |

## Pass Criteria

1. Every navigation route opens without a page error.
2. Every listed button either completes its action or shows an intentional validation/error message.
3. New sales are wholesale-only and tax-free; payment allocations equal the discounted invoice total, with Credit tracked as outstanding rather than received.
4. Customer selection is never required; manually entered name/mobile are optional.
5. No active screen exposes retail pricing, GST controls/calculations, or a credit-management module.
6. No API request returns an unexpected 5xx response during valid workflows.
7. Exports open successfully and match the visible no-tax rules.

## Automated Run Notes - 2026-09-18

- Backend compile and smoke test: **PASS** (`SMOKE TEST PASSED`).
- Authenticated read API batch: **PASS**; `/api/me`, settings, categories, products, customers, invoices, dashboard, analytics, held bills, purchases, expenses, and backup returned `200`.
- Browser login/dashboard load: **PASS** with no page errors after the mount-point fix.
- Browser route navigation: **PASS** for Dashboard, Billing, Sales, Inventory, Expenses, Reports, Analytics, Settings, and Backup & Export.
- Products route: **BLOCKED in integrated browser automation** because the implementation uses native `prompt()`, which that automation environment does not support. Test manually in a normal browser.
- Customer/Pricing route assertions were affected by the Products prompt failure during the rapid route sweep and require an isolated rerun after replacing the prompt with an in-page search control.
- Remaining mutation tests should run against a fresh database so demo records are not changed.

## Additional Findings From Feature Run

- **BILL-05: FAIL** - Billing visibly contains `RETAIL` and `WHOLESALE` pricing buttons.
- **BILL-06: FAIL** - Billing visibly contains a GST row and calculates GST in the browser total.
- **BILL-08: FAIL** - Payment modal visibly contains a `Credit` option.
- **PRODUCTS-01: BLOCKED** - Products uses native `prompt()`, unsupported by the integrated browser runner; replace with an in-page search control for automation and better usability.
- **DASH-03/DASH-04: FAIL in current frontend bundle** - The browser still renders Customer Dues, At Retail, Sales by hour, and credit language even though the backend dashboard response no longer returns dues/hourly fields.

## Retest Results - 2026-09-18

- **DASH-03/DASH-04: PASS** - Corrected dashboard renders low-stock refill attention with no dues, retail, GST, credit, or hourly content.
- **BILL-05/BILL-06/BILL-08: PASS (pre-Credit change)** - At the time of this historical retest, Billing had manual optional customer fields, wholesale pricing only, no GST row/calculation, and no credit payment option.
- **PRODUCTS-01: PASS** - Products uses an in-page search field; native `prompt()` is no longer used for product search.
- **Navigation sweep: PASS** - All 12 navigation targets rendered their expected headings with no browser page errors.
- **Screen language audit: PASS (pre-Credit change)** - At the time of this historical audit, Dashboard, Billing, Sales, Products, Inventory, Customers, Pricing, Analytics, and Settings contained no Retail, GST, Credit, Outstanding, or customer-dues text.
