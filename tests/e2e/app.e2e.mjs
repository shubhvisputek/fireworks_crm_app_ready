// Browser end-to-end test of every screen. Run: node tests/e2e/app.e2e.mjs
// Needs Playwright (resolved from the local or global node_modules) and python3.
import { spawn, execSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  try {
    return require('playwright');
  } catch {
    return require(path.join(execSync('npm root -g').toString().trim(), 'playwright'));
  }
}
const { chromium } = loadPlaywright();
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');

const freePort = () => new Promise((resolve) => {
  const srv = net.createServer().listen(0, '127.0.0.1', () => {
    const { port } = srv.address();
    srv.close(() => resolve(port));
  });
});

async function startServer() {
  const tmp = mkdtempSync(path.join(os.tmpdir(), 'fwcrm-e2e-'));
  const port = await freePort();
  const proc = spawn('python3', ['server.py'], {
    cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', FIREWORKS_DATA_DIR: tmp },
  });
  let log = '';
  proc.stdout.on('data', (d) => (log += d));
  proc.stderr.on('data', (d) => (log += d));
  for (let i = 0; i < 100; i++) {
    if (log.includes('running at')) return { url: `http://127.0.0.1:${port}`, proc, tmp, log: () => log };
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('server did not start:\n' + log);
}

const problems = [];
function watch(page, label) {
  page.on('pageerror', (e) => problems.push(`${label} pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('Failed to load resource')) problems.push(`${label} console: ${m.text()}`);
  });
  page.on('dialog', (d) => d.accept());
}

const step = async (name, fn) => {
  process.stdout.write(`• ${name} … `);
  await fn();
  console.log('ok');
};

async function login(page, url, username, password) {
  await page.goto(url);
  await page.fill('input[name=username]', username);
  await page.fill('input[name=password]', password);
  await page.click('button:has-text("Sign in")');
  await page.waitForSelector('.topbar h1');
}

// Press the confirm button in the "are you sure?" dialog, after checking what it says.
async function confirmDialog(page, pattern) {
  await page.waitForSelector('#confirm.show [data-confirm="yes"]');
  if (pattern) assert.match(await page.innerText('#confirm .modalbox'), pattern);
  await page.click('#confirm [data-confirm="yes"]');
}

// Secondary row actions (Return, Delete, Receipt, WhatsApp) sit in the row's "More" menu.
async function moreAction(page, row, label) {
  await page.click(`${row} summary:has-text("More")`);
  await page.click(`${row} .menu-items button:has-text("${label}")`);
}

async function nav(page, label) {
  await clearToast(page);
  await page.click(`.nav button:has-text("${label}")`);
}
// Wait for the next toast message (the toast is cleared before each user action).
async function toastText(page) {
  await page.waitForFunction(() => document.querySelector('#toast.show')?.textContent);
  const text = await page.innerText('#toast');
  await clearToast(page);
  return text;
}
const clearToast = (page) => page.evaluate(() => {
  const t = document.querySelector('#toast');
  t.classList.remove('show');
  t.textContent = '';
});
async function submitModal(page, values, button) {
  for (const [name, value] of Object.entries(values)) {
    const el = page.locator(`#modal [name="${name}"]`);
    if ((await el.evaluate((n) => n.tagName)) === 'SELECT') await el.selectOption(String(value));
    else await el.fill(String(value));
  }
  await page.click(`#modal button.primary${button ? `:has-text("${button}")` : ''}`);
}

const server = await startServer();
const browser = await chromium.launch();
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  watch(page, 'admin');

  await step('admin login and dashboard', async () => {
    await login(page, server.url, 'admin', 'admin123');
    assert.equal(await page.innerText('.topbar h1'), 'Dashboard');
    const navItems = await page.locator('.nav button').allInnerTexts();
    assert.deepEqual(navItems, ['Dashboard', 'Billing', 'Sales', 'Cash Closing', 'Credit Dues', 'Products', 'Inventory', 'Suppliers', 'Pricing',
      'Customers', 'Expenses', 'Settings', 'Users', 'Audit Log', 'Backup & Export']);
  });

  await step('add products', async () => {
    await nav(page, 'Products');
    for (const [sku, name, price, cost, stock] of [['P-1', 'Sparkler Box', 100, 60, 20], ['P-2', 'Rocket Pack', 250, 150, 10]]) {
      await page.click('button:has-text("+ Product")');
      await submitModal(page, { sku, name, unit_price: price, cost_price: cost, opening_stock: stock });
      assert.match(await toastText(page), /Product added/);
    }
    assert.equal(await page.locator('#productTable tbody tr').count(), 2);
  });

  await step('product search keeps focus while typing', async () => {
    await page.click('#productQuery');
    await page.keyboard.type('rock', { delay: 30 });
    assert.equal(await page.evaluate(() => document.activeElement.id), 'productQuery');
    assert.equal(await page.locator('#productTable tbody tr').count(), 1);
    await page.fill('#productQuery', '');
  });

  await step('product master import', async () => {
    const csv = path.join(server.tmp, 'master.csv');
    writeFileSync(csv, 'Product ID,Product Name,Unit Price,Opening Stock,Cost Price\nIMP-1,Flower Pot,40,30,25\n');
    await page.click('button:has-text("Upload Product Master")');
    await page.setInputFiles('#modal input[type=file]', csv);
    await page.click('#modal button:has-text("Validate & Preview")');
    await page.waitForSelector('#modal h3:has-text("Preview & Mapping")');
    await page.click('#modal button:has-text("Confirm Import")');
    assert.match(await toastText(page), /Imported 1 of 1/);
    assert.equal(await page.locator('#productTable tbody tr').count(), 3);
  });

  await step('product detail, ledger and remove stock', async () => {
    await page.click('#productTable tr:has-text("Flower Pot") button:has-text("View")');
    await page.click('#modal button:has-text("Stock Ledger")');
    await page.waitForSelector('#modal td:has-text("OPENING")');
    await page.keyboard.press('Escape');
    await page.click('#productTable tr:has-text("Flower Pot") button:has-text("View")');
    await page.click('#modal button:has-text("Remove Stock")');
    await submitModal(page, { qty: 5 }, 'Remove Stock');
    assert.match(await toastText(page), /Stock removed/);
  });

  await step('inventory: purchase and adjustment', async () => {
    await nav(page, 'Inventory');
    await page.click('button:has-text("+ Add Stock / GRN")');
    const sparkler = await page.locator('#modal .grn-product option:has-text("Sparkler")').getAttribute('value');
    await page.locator('#modal .grn-product').selectOption(sparkler);
    await page.fill('#modal .grn-qty', '5');
    await page.fill('#modal .grn-cost', '62');
    await submitModal(page, { supplier_name: 'Sivakasi Co' }, 'Add Stock');
    assert.match(await toastText(page), /Stock added \(PUR-/);
    await page.click('button:has-text("Stock Adjustment")');
    await submitModal(page, { product_id: sparkler, type: 'DAMAGE', qty: 1, reason: 'wet' });
    assert.match(await toastText(page), /Stock adjusted/);
    assert.match(await page.innerText('tr:has-text("Sparkler Box")'), /24/);
  });

  await step('customers', async () => {
    await nav(page, 'Customers');
    await page.click('button:has-text("+ Customer")');
    await submitModal(page, { name: 'Aarav Traders', phone: '9876500011' });
    assert.match(await toastText(page), /Customer added/);
    assert.match(await page.innerText('#page'), /Aarav Traders/);
  });

  await step('billing: search with Enter, quantities, discount, hold and resume', async () => {
    await nav(page, 'Billing');
    await page.fill('#productSearch', 'P-1');
    await page.press('#productSearch', 'Enter');
    await page.fill('#cart input[aria-label=Quantity]', '3');
    await page.press('#cart input[aria-label=Quantity]', 'Tab');
    await page.fill('#productSearch', 'rocket');
    await page.click('.product-result:has-text("Rocket Pack")');
    assert.equal(await page.locator('#cart .cart-row').count(), 2);
    await page.click('button[data-pct="10"]');
    assert.match(await page.innerText('#summary'), /495\.00/); // (300 + 250) - 10%
    await page.fill('#billName', 'Sneha');
    await page.click('#billPhone');
    await page.keyboard.type('98765abc43210');
    assert.equal(await page.inputValue('#billPhone'), '9876543210');
    await page.click('#holdBill');
    assert.match(await toastText(page), /Bill held/);
    assert.equal(await page.locator('#cart .cart-row').count(), 0);
    await page.click('button:has-text("Held Bills")');
    await page.click('#modal button:has-text("Resume")');
    assert.match(await toastText(page), /Held bill resumed/);
    assert.equal(await page.locator('#cart .cart-row').count(), 2);
    assert.equal(await page.inputValue('#billName'), 'Sneha');
  });

  let firstBill;
  await step('billing: pay with cash + credit and open the PDF', async () => {
    await page.click('button:has-text("Payment & Complete")');
    await page.fill('#modal .pay-amount', '300');
    await page.click('#modal button:has-text("+ Split payment")');
    await page.locator('#modal .pay-mode').nth(1).selectOption('Credit');
    await page.locator('#modal .pay-amount').nth(1).fill('195');
    // Headless Chromium has no PDF viewer, so check that the popup requested the invoice PDF.
    const pdfRequest = context.waitForEvent('request', (r) => /\/api\/invoice-pdf\/\d+$/.test(r.url()));
    const popup = context.waitForEvent('page');
    await page.click('#modal button:has-text("Finalize Invoice")');
    const pdfResponse = await (await pdfRequest).response();
    assert.equal(pdfResponse.headers()['content-type'], 'application/pdf');
    // The print page frames the PDF and opens the print dialog; only our own pages may frame it.
    assert.equal(pdfResponse.headers()['x-frame-options'], 'SAMEORIGIN');
    const printPage = await popup;
    await printPage.waitForURL(/\/static\/print\.html\?/);
    assert.match(await printPage.innerText('#title'), /A4 invoice/);
    await printPage.close();
    firstBill = (await toastText(page)).match(/Bill (\S+) completed/)[1];
  });

  await step('sales: collect credit', async () => {
    await nav(page, 'Sales');
    const row = page.locator(`tr:has-text("${firstBill}")`);
    assert.match(await row.innerText(), /Due ₹195\.00/);
    await row.locator('button:has-text("Collect")').click();
    await submitModal(page, { amount: 195 }, 'Save Payment');
    assert.match(await toastText(page), /Payment collected/);
    assert.equal(await page.locator(`tr:has-text("${firstBill}") button:has-text("Collect")`).count(), 0);
  });

  let editedBill;
  await step('sales: edit a bill (remove an item, reason required)', async () => {
    await page.click(`tr:has-text("${firstBill}") button:has-text("Edit")`);
    await page.waitForSelector('.notice.warn:has-text("Editing bill")');
    await page.click('#cart .cart-row:has-text("Rocket Pack") button.cart-remove');
    await page.click('button:has-text("Save edited bill")');
    // The bill total changed, so payment is pre-filled as one Cash row for the new amount (300 - ₹55 discount).
    assert.equal(await page.inputValue('#modal .pay-amount'), '245');
    const popup = context.waitForEvent('page');
    await page.fill('#modal input[name=reason]', 'Customer returned the rocket pack');
    await page.click('#modal button:has-text("Save edited bill")');
    (await popup).close();
    editedBill = (await toastText(page)).match(/new bill (\S+)/)[1];
    const row = await page.innerText(`tr:has-text("${editedBill}")`);
    assert.match(row, /Edited by admin/);
    assert.match(row, new RegExp(`Revised from ${firstBill}`));
    await page.selectOption('select[aria-label="Which bills"]', 'VOID');
    await page.waitForSelector(`td:has-text("Replaced by ${editedBill}")`);
    assert.match(await page.innerText('tbody tr:first-child'), new RegExp(`${firstBill}[\\s\\S]*Replaced by ${editedBill}`));
    await page.selectOption('select[aria-label="Which bills"]', 'FINALIZED');
    await page.waitForSelector(`td:has-text("Revised from ${firstBill}")`);
  });

  await step('sales: return an item, then void blocked', async () => {
    await moreAction(page, `tr:has-text("${editedBill}")`, 'Return');
    await page.fill('#modal .return-qty', '1');
    await page.click('#modal button:has-text("Process Return")');
    assert.match(await toastText(page), /Return RET-.* posted/);
    await moreAction(page, `tr:has-text("${editedBill}")`, 'Delete');
    await confirmDialog(page, /items go back into stock/);
    assert.match(await toastText(page), /posted return/);
  });

  await step('expenses and recurring expense', async () => {
    await nav(page, 'Expenses');
    await page.click('button:has-text("+ Add Expense")');
    await submitModal(page, { category: 'Rent', amount: 2500, payment_mode: 'UPI' });
    assert.match(await toastText(page), /Expense saved/);
    assert.match(await page.innerText('#page'), /Rent/);
    await page.click('button:has-text("+ Recurring")');
    await submitModal(page, { category: 'Electricity', amount: 900, frequency: 'Monthly' });
    assert.match(await toastText(page), /Recurring expense saved/);
  });

  await step('pricing', async () => {
    await nav(page, 'Pricing');
    await page.click('tr:has-text("Rocket Pack") button:has-text("Change")');
    await submitModal(page, { unit_price: 275 });
    assert.match(await toastText(page), /Default unit price saved/);
    assert.match(await page.innerText('tr:has-text("Rocket Pack")'), /275\.00/);
  });

  await step('dashboard periods, every tab and profit from cost price', async () => {
    await nav(page, 'Dashboard');
    await page.waitForSelector('.dashboard .tabs');
    for (const label of ['Yesterday', 'Last 7 days', 'Last 30 days', 'This month', 'Last month', 'Season', 'Today']) {
      await page.click(`.pill-nav button:has-text("${label}")`);
      await page.waitForSelector(`.pill-nav button.active:has-text("${label}")`);
    }
    const kpis = await page.innerText('.grid.kpis');
    assert.match(kpis, /Gross profit/);
    assert.doesNotMatch(kpis, /Gross profit\s*₹270\.00/, 'profit must subtract cost of goods');
    const tabs = await page.locator('.tabs button').allInnerTexts();
    assert.deepEqual(tabs, ['Overview', 'Sales', 'Products', 'Customers & credit', 'Team', 'Stock', 'Finance']);
    for (const [tab, title] of [['Sales', 'Busiest days and hours'], ['Products', 'Revenue by category'], ['Customers & credit', 'Credit outstanding by age'],
      ['Team', 'Sales by person'], ['Stock', 'Stock value by category'], ['Finance', 'From sales to net profit'], ['Overview', 'Needs attention']]) {
      await page.click(`.tabs button:has-text("${tab}")`);
      await page.waitForSelector(`.chart-card h3:has-text("${title}")`);
    }
    // Hovering the hour chart shows a tooltip; the table view carries the same numbers.
    await page.click('.tabs button:has-text("Sales")');
    await page.hover('.chart-svg .mark[tabindex="0"]');
    assert.match(await page.innerText('.chart-tip'), /₹/);
    await page.fill('.dash-range input[name=start]', '2020-01-01');
    await page.fill('.dash-range input[name=end]', '2020-01-31');
    await page.click('.dash-range button');
    await page.waitForSelector('.dash-period:has-text("1 Jan, 2020")');
  });

  await step('settings and theme: preview, save, applies on next sign-in', async () => {
    await nav(page, 'Settings');
    await page.fill('input[name=business_name]', 'Diwali Depot');
    await page.check('input[name=theme][value=festive]');
    assert.equal(await page.getAttribute('html', 'data-theme'), 'festive', 'clicking a theme previews it');
    await page.click('button:has-text("Save Settings")');
    assert.match(await toastText(page), /Settings saved/);
    await nav(page, 'Dashboard');
    assert.equal(await page.getAttribute('html', 'data-theme'), 'festive');
    await page.reload();
    await page.waitForSelector('.topbar h1');
    assert.equal(await page.getAttribute('html', 'data-theme'), 'festive');
  });

  await step('dark mode switch is personal and remembered', async () => {
    const before = await page.getAttribute('html', 'data-mode');
    await page.click('.mode-toggle');
    const after = await page.getAttribute('html', 'data-mode');
    assert.notEqual(after, before);
    await page.reload();
    await page.waitForSelector('.topbar h1');
    assert.equal(await page.getAttribute('html', 'data-mode'), after);
    await page.click('.mode-toggle');
    assert.equal(await page.getAttribute('html', 'data-mode'), before);
  });

  await step('billing counter: F2 search, arrow keys, F9 pay, change to give, no print', async () => {
    await nav(page, 'Billing');
    await page.waitForSelector('#productSearch');
    await page.keyboard.press('F2');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'productSearch');
    await page.keyboard.type('P-');
    await page.keyboard.press('ArrowDown');
    const picked = await page.innerText('.product-result.active strong');
    await page.keyboard.press('Enter');
    assert.match(await page.innerText('#cart'), new RegExp(picked));
    await page.keyboard.press('F9');
    await page.waitForSelector('#modal.show #cashGiven');
    const due = Number(await page.inputValue('#modal .pay-amount'));
    await page.fill('#cashGiven', String(Math.ceil(due) + 100));
    assert.match(await page.innerText('#changeDue'), /Give back ₹/);
    await page.check('#modal input[name=print][value=none]');
    let popups = 0;
    const count = () => popups++;
    context.on('page', count);
    await page.keyboard.press('F9');
    assert.match(await toastText(page), /Bill .* completed/);
    context.off('page', count);
    assert.equal(popups, 0, "Don't print opens no print window");
    // The choice is remembered on this device; later steps print again.
    assert.equal(await page.evaluate(() => localStorage.getItem('fw-print')), 'none');
    await page.evaluate(() => localStorage.setItem('fw-print', 'A4'));
  });


  await step('backup page links', async () => {
    await nav(page, 'Backup & Export');
    await page.waitForSelector('#page a[href="/api/backup"]');
    const links = await page.locator('#page a').evaluateAll((as) => as.map((a) => a.getAttribute('href')).filter((h) => !h.startsWith('/api/backups/')));
    assert.deepEqual(links, ['/api/backup', '/api/export/sales.xlsx', '/api/export/sales-detailed.xlsx', '/api/export/sales.pdf']);
  });

  await step('backups: automatic daily backup listed, Backup now adds one', async () => {
    await page.waitForSelector('td:has-text("Automatic (daily)")');
    await page.click('button:has-text("Backup now")');
    assert.match(await toastText(page), /Backup saved: fireworks-.*-manual\.sqlite/);
    await page.waitForSelector('td:has-text("Manual")');
  });

  await step('suppliers: purchase from a new supplier, ledger and payment', async () => {
    await nav(page, 'Inventory');
    await page.click('button:has-text("+ Add Stock / GRN")');
    await page.fill('#modal input[name=supplier_name]', 'Sivakasi Traders');
    const rocket = await page.locator('#modal .grn-product option:has-text("Rocket")').getAttribute('value');
    await page.locator('#modal .grn-product').selectOption(rocket);
    await page.fill('#modal .grn-qty', '4');
    await page.fill('#modal .grn-cost', '150');
    await page.click('#modal button:has-text("+ Another product")');
    await page.locator('#modal .grn-qty').nth(1).fill('2');
    await page.locator('#modal .grn-cost').nth(1).fill('50');
    await page.click('#modal button:has-text("Add Stock")');
    assert.match(await toastText(page), /Stock added \(PUR-.*₹700\.00\)/);
    await nav(page, 'Suppliers');
    const row = page.locator('tr:has-text("Sivakasi Traders")');
    assert.match(await row.innerText(), /₹700\.00/);
    await row.locator('button:has-text("Record payment")').click();
    await submitModal(page, { amount: 300, mode: 'UPI' });
    assert.match(await toastText(page), /Balance now ₹400\.00/);
    await page.click('tr:has-text("Sivakasi Traders") button:has-text("Ledger")');
    await page.waitForSelector('#modal td:has-text("UPI")');
    await page.keyboard.press('Escape');
  });

  await step('inventory: seasonal reorder plan', async () => {
    await nav(page, 'Inventory');
    await page.click('button:has-text("Seasonal Reorder Plan")');
    await page.fill('#modal input[name=start]', '2000-01-01');
    await page.fill('#modal input[name=end]', '2999-12-31');
    await page.click('#modal button:has-text("Recalculate")');
    await page.waitForSelector('#modal td:has-text("Sparkler Box")');
    assert.match(await page.innerText('#modal'), /Estimated purchase cost/);
    await page.keyboard.press('Escape');
  });

  await step('barcode on a product, then billing by scanning it', async () => {
    await nav(page, 'Products');
    await page.click('#productTable tr:has-text("Sparkler Box") button:has-text("View")');
    await page.click('#modal button:has-text("Edit")');
    await submitModal(page, { barcode: '8901234567890' });
    assert.match(await toastText(page), /Product updated/);
    await nav(page, 'Billing');
    await page.fill('#productSearch', '8901234567890');
    await page.press('#productSearch', 'Enter');
    assert.match(await page.innerText('#cart'), /Sparkler Box/);
    await page.click('button:has-text("New Bill")');
  });

  await step('credit dues (WhatsApp switched off); receipt printing', async () => {
    await nav(page, 'Billing');
    await page.fill('#billName', 'Mahesh Credit');
    await page.click('#billPhone');
    await page.keyboard.type('9811122233');
    await page.fill('#productSearch', 'P-1');
    await page.press('#productSearch', 'Enter');
    await page.click('button:has-text("Payment & Complete")');
    await page.locator('#modal .pay-mode').selectOption('Credit');
    const popup = context.waitForEvent('page');
    await page.click('#modal button:has-text("Finalize Invoice")');
    (await popup).close();
    await nav(page, 'Credit Dues');
    const row = page.locator('tr:has-text("Mahesh Credit")').first();
    assert.match(await row.innerText(), /₹100\.00/);
    assert.equal(await page.locator('button:has-text("WhatsApp")').count(), 0);
    await nav(page, 'Sales');
    assert.equal(await page.locator('tbody button:has-text("WhatsApp")').count(), 0);
    const receipt = context.waitForEvent('request', (r) => /\/api\/invoice-receipt\/\d+$/.test(r.url()));
    const receiptPopup = context.waitForEvent('page');
    await moreAction(page, 'tbody tr:first-child', 'Receipt');
    assert.equal((await (await receipt).response()).headers()['content-type'], 'application/pdf');
    (await receiptPopup).close();
  });

  await step('audit log shows who did what', async () => {
    await nav(page, 'Audit Log');
    await page.waitForSelector('td:has-text("Invoice finalized")');
    await page.selectOption('#page select[name=entity]', 'SUPPLIER');
    await page.click('#page button:has-text("Show")');
    await page.waitForFunction(() => !document.querySelector('#page tbody').innerText.includes('Invoice finalized'));
    assert.match(await page.innerText('#page tbody'), /Supplier payment/);
  });

  await step('stored XSS payload is shown as text, never run', async () => {
    await nav(page, 'Billing');
    await page.fill('#billName', '<img src=x onerror="window.__pwned=1">');
    await page.fill('#productSearch', 'P-1');
    await page.press('#productSearch', 'Enter');
    await page.click('button:has-text("Payment & Complete")');
    const popup = context.waitForEvent('page');
    await page.click('#modal button:has-text("Finalize Invoice")');
    (await popup).close();
    await nav(page, 'Sales');
    await page.waitForSelector('td:has-text("<img src=x")');
    assert.equal(await page.evaluate(() => window.__pwned), undefined);
  });

  await step('users: add a cashier with a display name; permission editor', async () => {
    await nav(page, 'Users');
    await page.fill('#page input[name=username]', 'rohan');
    await page.fill('#page input[name=display_name]', 'Rohan');
    await page.fill('#page input[name=password]', 'rohanpass1');
    assert.equal(await page.inputValue('#page select[name=role]'), 'CASHIER');
    await page.click('button:has-text("Add user")');
    assert.match(await toastText(page), /User added/);
    await page.click('tr:has-text("Rohan") button:has-text("Edit")');
    assert.equal(await page.locator('#modal input[name=perm]:disabled').count() > 0, true);
    assert.equal(await page.isChecked('#modal input[value="billing.create"]'), true);
    assert.equal(await page.isChecked('#modal input[value="sales.void"]'), false);
    await page.check('#modal input[name=custom]');
    assert.equal(await page.locator('#modal input[name=perm]:disabled').count(), 0);
    await page.keyboard.press('Escape');
  });

  await step('staff sees only their pages and can bill and change password', async () => {
    const staffContext = await browser.newContext();
    const staff = await staffContext.newPage();
    watch(staff, 'staff');
    await login(staff, server.url, 'rohan', 'rohanpass1');
    assert.deepEqual(await staff.locator('.nav button').allInnerTexts(), ['Dashboard', 'Billing', 'Sales', 'Cash Closing', 'Customers', 'Expenses']);
    await staff.waitForSelector('.dashboard .tabs');
    assert.match(await staff.innerText('.dash-period'), /Showing only your own bills/);
    assert.deepEqual(await staff.locator('.tabs button').allInnerTexts(), ['Overview', 'Sales', 'Products']);
    assert.doesNotMatch(await staff.innerText('#page'), /gross profit|at cost|margin/i);
    await staff.goto(server.url + '/#users');
    await staff.waitForSelector('.topbar h1');
    assert.equal(await staff.innerText('.topbar h1'), 'Dashboard');
    await staff.click('.nav button:has-text("Billing")');
    await staff.fill('#productSearch', 'P-1');
    await staff.press('#productSearch', 'Enter');
    await staff.click('button:has-text("Payment & Complete")');
    const popup = staffContext.waitForEvent('page');
    await staff.click('#modal button:has-text("Finalize Invoice")');
    (await popup).close();
    assert.match(await toastText(staff), /completed/);
    // A 15% discount is above the 10% limit: a manager must approve it.
    await staff.fill('#productSearch', 'P-1');
    await staff.press('#productSearch', 'Enter');
    await staff.click('button[data-pct="15"]');
    await staff.click('button:has-text("Payment & Complete")');
    await staff.waitForSelector('#approvalBox');
    await staff.fill('#modal input[name=approver]', 'admin');
    await staff.fill('#modal input[name=approver_password]', 'admin123');
    const approvedPopup = staffContext.waitForEvent('page');
    await staff.click('#modal button:has-text("Finalize Invoice")');
    (await approvedPopup).close();
    assert.match(await toastText(staff), /completed/);
    // Sales shows only this cashier's bills, without edit/void buttons.
    await staff.click('.nav button:has-text("Sales")');
    await staff.waitForSelector('th:has-text("Billed by")');
    const billers = await staff.locator('tbody tr td:nth-child(4)').allInnerTexts();
    assert.ok(billers.length === 2 && billers.every((b) => b.startsWith('Rohan')), billers.join('|'));
    assert.equal(await staff.locator('button:has-text("Delete"), button:has-text("Edit")').count(), 0);
    // Close the drawer: 100 + 85 cash taken.
    await staff.click('.nav button:has-text("Cash Closing")');
    await staff.waitForSelector('text=Cash expected in drawer');
    assert.match(await staff.innerText('#page'), /₹185\.00/);
    await staff.fill('input[name=counted_cash]', '180');
    await staff.click('button:has-text("Close drawer")');
    assert.match(await toastText(staff), /Difference -₹5\.00|Difference −₹5\.00/);
    await staff.click('.nav button:has-text("Billing")');
    await staff.click('button:has-text("Held Bills")');
    assert.equal(await staff.locator('#modal button:has-text("Delete")').count(), 0);
    await staff.click('#modal button[data-action="modal.close"]');
    await staff.click('.topbar button:has-text("Password")');
    await submitModal(staff, { current_password: 'rohanpass1', new_password: 'rohanpass2' }, 'Change Password');
    assert.match(await toastText(staff), /Password changed/);
    await staff.click('button:has-text("Logout")');
    await staff.waitForSelector('button:has-text("Sign in")');
    await staffContext.close();
  });

  await step('admin unlocks a user locked out by wrong passwords', async () => {
    // Another browser (like an incognito window) types the wrong password for rohan until it is paused.
    const other = await browser.newContext();
    const guess = await other.newPage();
    await guess.goto(server.url);
    for (let i = 0; i < 10; i += 1) {
      await guess.fill('input[name=username]', 'rohan');
      await guess.fill('input[name=password]', `wrong-${i}`);
      await guess.click('button:has-text("Sign in")');
      await guess.waitForResponse((r) => r.url().endsWith('/api/login'));
    }
    await guess.fill('input[name=password]', 'rohanpass2');
    await guess.click('button:has-text("Sign in")');
    await guess.waitForSelector('text=Too many wrong passwords');
    await nav(page, 'Users');
    const row = page.locator('tr:has-text("Rohan")');
    await row.locator('.tag:has-text("Locked")').waitFor();
    await row.locator('button:has-text("Unlock")').click();
    assert.match(await toastText(page), /can sign in again/);
    assert.equal(await row.locator('.tag:has-text("Locked")').count(), 0);
    await guess.click('button:has-text("Sign in")');
    await guess.waitForSelector('.topbar h1');
    await other.close();
  });

  await step('owner can switch the wrong-password lockout off', async () => {
    await nav(page, 'Settings');
    assert.equal(await page.inputValue('#page select[name=login_lockout]'), '1');
    await page.selectOption('#page select[name=login_lockout]', '0');
    await page.click('button:has-text("Save Settings")');
    assert.match(await toastText(page), /Settings saved/);
    const other = await browser.newContext();
    const guess = await other.newPage();
    await guess.goto(server.url);
    for (let i = 0; i < 12; i += 1) {
      const res = await guess.request.post(server.url + '/api/login', { data: { username: 'rohan', password: `nope-${i}` } });
      assert.equal(res.status(), 401);
    }
    await login(guess, server.url, 'rohan', 'rohanpass2');
    await other.close();
    await nav(page, 'Settings');
    await page.selectOption('#page select[name=login_lockout]', '1');
    await page.click('button:has-text("Save Settings")');
    assert.match(await toastText(page), /Settings saved/);
  });

  await step('admin sees the staff bill with Billed by', async () => {
    await nav(page, 'Sales');
    await page.waitForSelector('th:has-text("Billed by")');
    assert.match(await page.innerText('tbody tr:first-child'), /Rohan/);
    await nav(page, 'Cash Closing');
    await page.waitForSelector('td:has-text("Rohan")');
  });

  // Every screen at phone, tablet and desktop widths: nothing wider than the screen,
  // drawer navigation below 1024px, tables as labelled cards on phones.
  for (const [width, height] of [[320, 640], [390, 844], [768, 1024], [1024, 768], [1440, 900]]) {
    await step(`responsive layout at ${width}px`, async () => {
      const context = await browser.newContext({ viewport: { width, height } });
      const small = await context.newPage();
      watch(small, `${width}px`);
      await login(small, server.url, 'admin', 'admin123');
      await small.waitForSelector('.dashboard .tabs');
      const pages = await small.$$eval('.nav button', (buttons) => buttons.map((b) => b.dataset.page));
      for (const name of pages) {
        await small.evaluate((n) => { location.hash = n; }, name);
        await small.waitForFunction((n) => document.querySelector('.nav button.active')?.dataset.page === n, name);
        await small.waitForTimeout(150);
        const overflow = await small.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        assert.ok(overflow <= 0, `${name} is ${overflow}px wider than a ${width}px screen`);
      }
      const sidebarOnScreen = await small.$eval('.sidebar', (el) => el.getBoundingClientRect().right > 0);
      assert.equal(sidebarOnScreen, width > 1024, 'sidebar is a hidden drawer below 1024px');
      if (width <= 1024) {
        await small.click('.menu-toggle');
        await small.waitForSelector('.mobile-menu-open .sidebar .nav button:has-text("Sales")');
        await small.click('.sidebar .nav button:has-text("Sales")');
        await small.waitForSelector('.topbar h1:has-text("Sales")');
      } else {
        await small.click('.nav button:has-text("Sales")');
      }
      await small.waitForSelector('tbody td[data-label="Customer"]');
      const display = await small.$eval('.table thead', (el) => getComputedStyle(el).display);
      assert.equal(display === 'none', width <= 640, 'tables show as cards only on phones');
      await context.close();
    });
  }

  assert.deepEqual(problems, [], 'browser errors:\n' + problems.join('\n'));
  console.log('\nE2E PASSED');
} catch (error) {
  console.error('\nE2E FAILED:', error.message);
  if (problems.length) console.error('Browser problems:\n' + problems.join('\n'));
  console.error('Server log:\n' + server.log().slice(-3000));
  process.exitCode = 1;
} finally {
  await browser.close();
  server.proc.kill();
  rmSync(server.tmp, { recursive: true, force: true });
}
