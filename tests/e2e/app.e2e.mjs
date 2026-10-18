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
    assert.equal(await page.innerText('.topbar h1'), 'Owner Dashboard');
    const navItems = await page.locator('.nav button').allInnerTexts();
    assert.deepEqual(navItems, ['Dashboard', 'Billing', 'Sales', 'Products', 'Inventory', 'Customers', 'Expenses', 'Pricing', 'Analytics', 'Settings', 'Users', 'Backup & Export']);
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
    const sparkler = await page.locator('#modal select[name=product_id] option:has-text("Sparkler")').getAttribute('value');
    await submitModal(page, { product_id: sparkler, qty: 5, cost_price: 62, supplier_name: 'Sivakasi Co' }, 'Add Stock');
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
    await page.click('#modal button:has-text("+ Payment")');
    await page.locator('#modal .pay-mode').nth(1).selectOption('Credit');
    await page.locator('#modal .pay-amount').nth(1).fill('195');
    // Headless Chromium has no PDF viewer, so check that the popup requested the invoice PDF.
    const pdfRequest = context.waitForEvent('request', (r) => /\/api\/invoice-pdf\/\d+$/.test(r.url()));
    const popup = context.waitForEvent('page');
    await page.click('#modal button:has-text("Finalize Invoice")');
    const pdfResponse = await (await pdfRequest).response();
    assert.equal(pdfResponse.headers()['content-type'], 'application/pdf');
    (await popup).close();
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
    await page.click(`tr:has-text("${editedBill}") button:has-text("Return")`);
    await page.fill('#modal .return-qty', '1');
    await page.click('#modal button:has-text("Process Return")');
    assert.match(await toastText(page), /Return RET-.* posted/);
    await page.click(`tr:has-text("${editedBill}") button:has-text("Delete")`);
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

  await step('analytics presets and profit from cost price', async () => {
    await nav(page, 'Analytics');
    await page.waitForSelector('.kpi');
    for (const label of ['Yesterday', 'Last 7 Days', 'This Month', 'Season', 'Today']) await page.click(`.pill-nav button:has-text("${label}")`);
    await page.waitForSelector('.pill-nav button.active:has-text("Today")');
    const kpis = await page.innerText('.grid.kpis');
    assert.match(kpis, /Gross Profit/);
    assert.doesNotMatch(kpis, /Gross Profit\s*₹270\.00/, 'profit must subtract cost of goods');
  });

  await step('settings', async () => {
    await nav(page, 'Settings');
    await page.fill('input[name=business_name]', 'Diwali Depot');
    await page.click('button:has-text("Save Settings")');
    assert.match(await toastText(page), /Settings saved/);
  });

  await step('backup page links', async () => {
    await nav(page, 'Backup & Export');
    await page.waitForSelector('#page a');
    const links = await page.locator('#page a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
    assert.deepEqual(links, ['/api/backup', '/api/export/sales.xlsx', '/api/export/sales-detailed.xlsx', '/api/export/sales.pdf']);
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

  await step('users: create staff', async () => {
    await nav(page, 'Users');
    await page.fill('input[name=username]', 'rohan');
    await page.fill('input[name=password]', 'rohanpass1');
    await page.click('button:has-text("Create staff account")');
    assert.match(await toastText(page), /Staff account created/);
  });

  await step('staff sees only their pages and can bill and change password', async () => {
    const staffContext = await browser.newContext();
    const staff = await staffContext.newPage();
    watch(staff, 'staff');
    await login(staff, server.url, 'rohan', 'rohanpass1');
    assert.deepEqual(await staff.locator('.nav button').allInnerTexts(), ['Dashboard', 'Billing', 'Expenses', 'Analytics', 'Backup & Export']);
    await staff.goto(server.url + '/#sales');
    await staff.waitForSelector('.topbar h1');
    assert.equal(await staff.innerText('.topbar h1'), 'Owner Dashboard');
    await staff.click('.nav button:has-text("Billing")');
    await staff.fill('#productSearch', 'P-1');
    await staff.press('#productSearch', 'Enter');
    await staff.click('button:has-text("Payment & Complete")');
    const popup = staffContext.waitForEvent('page');
    await staff.click('#modal button:has-text("Finalize Invoice")');
    (await popup).close();
    assert.match(await toastText(staff), /completed/);
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

  await step('admin sees the staff bill with Billed by', async () => {
    await nav(page, 'Sales');
    await page.waitForSelector('th:has-text("Billed by")');
    assert.match(await page.innerText('tbody tr:first-child'), /rohan/);
  });

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
