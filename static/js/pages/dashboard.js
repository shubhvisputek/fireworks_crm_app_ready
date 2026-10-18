// Dashboard: one period (with the period before it for comparison) seen from
// several angles. Each tab appears only when the server sent its section, so a
// user never sees a view their permissions don't cover.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { registerActions } from '../core/actions.js';
import { money, num, todayISO } from '../core/format.js';
import { registerPage } from '../core/router.js';
import { can } from '../core/state.js';
import { errorBox, table } from '../ui/widgets.js';
import {
  OTHER, SERIES, barList, previousColor, columnChart, heatmap, legend, lineChart, meter, ordinalColor, pct, resetCharts,
  stackedBar, statTile, waterfall, withTable,
} from '../ui/charts.js';

const PRESETS = [['today', 'Today'], ['yesterday', 'Yesterday'], ['7d', 'Last 7 days'], ['30d', 'Last 30 days'],
  ['month', 'This month'], ['last_month', 'Last month'], ['season', 'Season']];
const TABS = [['overview', 'Overview'], ['sales', 'Sales'], ['products', 'Products'], ['customers', 'Customers & credit'],
  ['team', 'Team'], ['stock', 'Stock'], ['finance', 'Finance']];
const PAYMENT_ORDER = ['Cash', 'UPI', 'Card', 'Credit', 'Bank Transfer', 'Cheque'];
const CUSTOMER_TYPES = { RETAIL: 'Retail', WHOLESALE: 'Wholesale' };

const view = { preset: '7d', tab: 'overview', start: '', end: '', data: null, today: null };
// Chart widths in pixels, so SVG text renders at its real size. Two-column grids collapse at 1050px (styles.css).
const size = { full: 640, half: 640 };

function measure() {
  const page = $('#page');
  const style = getComputedStyle(page);
  const inner = page.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const cardPadding = window.innerWidth <= 560 ? 30 : 34;
  size.page = page.clientWidth;
  size.full = inner - cardPadding;
  size.half = window.innerWidth > 1050 ? (inner - 14) / 2 - cardPadding : size.full;
}

const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
const longDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
const hourName = (h) => `${h % 12 || 12} ${h < 12 ? 'am' : 'pm'}`;
const has = (obj, key) => obj && key in obj;
const card = (title, body, sub = '') => html`<div class="card chart-card"><h3>${title}</h3>${sub ? html`<div class="small muted chart-sub">${sub}</div>` : ''}${body}</div>`;

// Colours follow the entity: payment modes and categories always get the same slot.
function paymentColor(mode) {
  const i = PAYMENT_ORDER.indexOf(mode);
  return i >= 0 ? SERIES[i] : OTHER;
}

function categoryColors(d) {
  const names = [...new Set([...(d.stock?.categories || []), ...d.products.categories].map((c) => c.category))].sort();
  return (name) => (names.indexOf(name) >= 0 && names.indexOf(name) < SERIES.length ? SERIES[names.indexOf(name)] : OTHER);
}

function compareLabel(period) {
  if (period.preset === 'today') return 'yesterday';
  if (period.preset === 'yesterday') return 'day before';
  return `previous ${period.days} days`;
}

// ---- tabs --------------------------------------------------------------------

function trendChart(d, { withProfit = false, width = size.full } = {}) {
  const s = d.sales;
  if (d.period.days === 1) {
    return card('Sales by hour', withTable(
      columnChart({ points: s.hourly.slice(8, 24).map((h) => ({ label: hourName(h.hour), tick: h.hour % 12 || 12, value: h.sales, extra: `${h.bills} bills` })), name: 'Sales', width }),
      ['Hour', 'Sales', 'Bills'], s.hourly.filter((h) => h.bills).map((h) => [hourName(h.hour), money(h.sales), h.bills]),
    ), longDate(d.period.start));
  }
  const series = [{ name: withProfit ? 'Sales' : 'This period', values: s.trend.map((t) => t.sales), area: true },
    { name: `Previous (${shortDate(d.period.prev_start)} – ${shortDate(d.period.prev_end)})`, values: s.trend.map((t) => t.prev_sales), color: previousColor(), dashed: true }];
  if (withProfit && has(s.trend[0], 'profit')) series.splice(1, 1, { name: 'Gross profit', values: s.trend.map((t) => t.profit), color: SERIES[2] });
  return card(withProfit ? 'Sales and gross profit by day' : 'Sales by day', withTable(
    lineChart({ labels: s.trend.map((t) => longDate(t.day)), ticks: s.trend.map((t) => shortDate(t.day)), series, width }),
    ['Day', 'Sales', 'Bills', ...(withProfit && has(s.trend[0], 'profit') ? ['Gross profit'] : ['Previous period'])],
    s.trend.map((t) => [longDate(t.day), money(t.sales), t.bills, withProfit && has(t, 'profit') ? money(t.profit) : money(t.prev_sales)]),
  ));
}

function kpiRow(d) {
  const k = d.sales.kpi;
  const p = d.sales.previous;
  const compare = compareLabel(d.period);
  const spark = d.period.days > 1 ? d.sales.trend.map((t) => t.sales) : null;
  return html`<div class="grid kpis">
    ${statTile({ label: 'Sales', value: money(k.sales), current: k.sales, previous: p.sales, compare, spark })}
    ${statTile({ label: 'Bills', value: num(k.bills), current: k.bills, previous: p.bills, compare, sub: `${num(k.items)} items sold` })}
    ${statTile({ label: 'Average bill', value: money(k.avg_bill), current: k.avg_bill, previous: p.avg_bill, compare })}
    ${has(k, 'gross_profit')
      ? statTile({ label: 'Gross profit', value: money(k.gross_profit), current: k.gross_profit, previous: p.gross_profit, compare, sub: `${pct(k.gross_margin)} margin` })
      : statTile({ label: 'Customers', value: num(k.customers), current: k.customers, previous: p.customers, compare })}
  </div>`;
}

function attention(d) {
  const t = view.today;
  const items = [];
  if (t?.storage?.over) items.push(html`<div class="notice bad">⚠ <strong>Licence storage exceeded:</strong> ${num(t.storage.current_kg)} kg stored, limit ${num(t.storage.limit_kg)} kg.</div>`);
  for (const x of t?.attention || []) {
    items.push(html`<div class="between notice ${x.stock <= 0 ? 'bad' : 'warn'}"><span>${x.stock <= 0 ? '⛔' : '⚠'} <strong>${x.name}</strong><br>
      <span class="small muted">${x.sku} • Refill at ${num(x.reorder_level)} units</span></span><strong>${num(x.stock)} left</strong></div>`);
  }
  for (const x of d.stock?.running_out?.slice(0, 3) || []) {
    items.push(html`<div class="between notice warn"><span>⏳ <strong>${x.name}</strong><br><span class="small muted">Selling ${num(x.per_day)} a day</span></span>
      <strong>~${num(Math.floor(x.days_left))} days left</strong></div>`);
  }
  const ex = d.sales.exceptions;
  if (ex.voids.count) items.push(html`<div class="notice warn">⚠ ${ex.voids.count} bill(s) deleted in this period (${money(ex.voids.amount)}).</div>`);
  if (d.customers?.dues_aging?.[3]?.amount) items.push(html`<div class="notice bad">⛔ ${money(d.customers.dues_aging[3].amount)} of credit is over 60 days old.</div>`);
  return card('Needs attention', html`<div class="grid">${items.length ? items : html`<div class="notice good">✓ Nothing needs attention.</div>`}</div>`);
}

function overview(d) {
  const t = view.today;
  const targets = d.finance?.targets;
  return html`${kpiRow(d)}
    <div class="grid two">${trendChart(d, { width: size.half })}
      ${targets ? card('Sales targets', html`<div class="grid">${targets.map((x) => meter({ label: x.label, value: x.actual, limit: x.target }))}</div>`)
        : t ? card("Today's sales", html`<div class="value hero-figure">${money(t.today.sales)}</div><div class="small muted">${t.today.bills} bills today</div>`) : ''}
    </div>
    <div class="grid two">
      ${card('How customers paid', stackedBar(d.sales.payments.map((x) => ({ label: x.mode, value: x.amount, color: paymentColor(x.mode) }))))}
      ${card('Top products', barList(d.products.top.slice(0, 5).map((x) => ({ label: x.name, value: x.revenue, sub: `${num(x.qty)} sold` })), { name: 'Revenue' }))}
    </div>
    ${attention(d)}`;
}

function sales(d) {
  const k = d.sales.kpi;
  const p = d.sales.previous;
  const compare = compareLabel(d.period);
  const ex = d.sales.exceptions;
  return html`${kpiRow(d)}
    <div class="grid kpis">
      ${statTile({ label: 'Discounts given', value: money(k.discounts), current: k.discounts, previous: p.discounts, upIsGood: false, compare, sub: `${pct(k.discount_pct)} of gross sales` })}
      ${statTile({ label: 'Sold on credit', value: money(k.credit), current: k.credit, previous: p.credit, upIsGood: false, compare, sub: 'Still outstanding on these bills' })}
      ${statTile({ label: 'Customers billed', value: num(k.customers), current: k.customers, previous: p.customers, compare })}
      ${statTile({ label: 'Deleted / edited / returned', value: `${ex.voids.count} / ${ex.edits} / ${ex.returns.count}`, sub: `Refunds ${money(ex.returns.amount)} • Deleted ${money(ex.voids.amount)}` })}
    </div>
    ${trendChart(d)}
    <div class="grid two">
      ${card('Sales by hour of day', withTable(
        columnChart({ points: d.sales.hourly.slice(8, 24).map((h) => ({ label: hourName(h.hour), tick: h.hour % 12 || 12, value: h.sales, extra: `${h.bills} bills` })), name: 'Sales', width: size.half }),
        ['Hour', 'Sales', 'Bills'], d.sales.hourly.filter((h) => h.bills).map((h) => [hourName(h.hour), money(h.sales), h.bills])), 'All days in the period combined')}
      ${card('Busiest days and hours', heatmap(d.sales.heatmap), 'Darker = more sales')}
    </div>
    <div class="grid two">
      ${card('Bill size', withTable(
        columnChart({ points: d.sales.bill_sizes.map((b) => ({ label: b.label, value: b.bills, extra: money(b.sales) })), format: (v) => `${num(v)} bills`, axisFormat: (v) => num(Math.round(v)), name: 'Bills', width: size.half }),
        ['Bill size', 'Bills', 'Sales'], d.sales.bill_sizes.map((b) => [b.label, b.bills, money(b.sales)])), 'Number of bills by bill amount')}
      ${card('Payment modes', withTable(
        stackedBar(d.sales.payments.map((x) => ({ label: x.mode, value: x.amount, color: paymentColor(x.mode) }))),
        ['Mode', 'Amount', 'Bills'], d.sales.payments.map((x) => [x.mode, money(x.amount), x.bills])))}
    </div>`;
}

function products(d) {
  const pr = d.products;
  const color = categoryColors(d);
  const profit = has(pr.top[0], 'profit');
  const productRows = (rows) => rows.map((x) => html`<tr><td>${x.name}<div class="small muted">${x.sku}</div></td><td>${num(x.qty)}</td>
    <td>${money(x.revenue)}</td>${profit ? html`<td>${pct(x.gross_margin)}</td>` : ''}<td>${pct(x.share)}</td></tr>`);
  const headers = ['Product', 'Qty', 'Revenue', ...(profit ? ['Margin'] : []), 'Share'];
  const moverRows = (rows) => rows.map((x) => html`<tr><td>${x.name}</td><td>${money(x.prev_revenue)}</td><td>${money(x.revenue)}</td>
    <td class="${x.change > 0 ? 'up' : 'down'}">${x.change > 0 ? '▲' : '▼'} ${money(Math.abs(x.change))}</td></tr>`);
  return html`<div class="grid kpis">
      ${statTile({ label: 'Products sold', value: num(pr.sold_count), sub: 'Different products on bills' })}
      ${statTile({ label: 'Sales concentration', value: pct(pr.concentration.share), sub: `of revenue from the top ${pr.concentration.top_products} products` })}
      ${statTile({ label: 'Best category', value: pr.categories[0]?.category || '—', sub: pr.categories[0] ? `${money(pr.categories[0].revenue)} • ${pct(pr.categories[0].share)}` : '' })}
      ${statTile({ label: 'Best seller', value: pr.top[0]?.name || '—', sub: pr.top[0] ? `${num(pr.top[0].qty)} sold • ${money(pr.top[0].revenue)}` : '' })}
    </div>
    <div class="grid two">
      ${card('Revenue by category', withTable(
        html`${stackedBar(pr.categories.map((c) => ({ label: c.category, value: c.revenue, color: color(c.category) })), { maxParts: 8 })}<br>
          ${barList(pr.categories.map((c) => ({ label: c.category, value: c.revenue, color: color(c.category), sub: `${num(c.qty)} sold${has(c, 'gross_margin') ? ` • ${pct(c.gross_margin)} margin` : ''}` })), { name: 'Revenue' })}`,
        ['Category', 'Revenue', 'Qty', ...(profit ? ['Gross profit', 'Margin'] : []), 'Share'],
        pr.categories.map((c) => [c.category, money(c.revenue), num(c.qty), ...(profit ? [money(c.profit), pct(c.gross_margin)] : []), pct(c.share)])))}
      ${card('Top 10 products by revenue', barList(pr.top.map((x) => ({ label: x.name, value: x.revenue, color: color(x.category), sub: `${num(x.qty)} sold • ${pct(x.share)}` })), { name: 'Revenue' }),
        'Bar colour = category')}
    </div>
    <div class="grid two">
    ${profit ? card('Most profitable products', barList([...pr.top].sort((a, b) => b.profit - a.profit).map((x) => ({ label: x.name, value: x.profit, color: color(x.category), sub: `${pct(x.gross_margin)} margin` })), { name: 'Gross profit' }),
      'Among the top 10 by revenue') : ''}
      <div class="grid">
        ${card('Rising vs previous period', table(['Product', 'Before', 'Now', 'Change'], moverRows(pr.rising), 'No product sold more than last period.'))}
        ${card('Falling vs previous period', table(['Product', 'Before', 'Now', 'Change'], moverRows(pr.falling), 'No product sold less than last period.'))}
      </div>
    </div>
    <div class="grid two">
      ${card('Top sellers', table(headers, productRows(pr.top), 'No sales in this period.'))}
      ${card('Slowest sellers', table(headers, productRows(pr.bottom), 'Fewer than 10 products sold in this period.'), 'Sold at least once, lowest revenue first')}
    </div>`;
}

function customers(d) {
  const c = d.customers;
  const nvr = c.new_vs_repeat;
  return html`<div class="grid two">
      ${card('Retail vs wholesale', withTable(
        stackedBar(c.types.map((t, i) => ({ label: CUSTOMER_TYPES[t.customer_type] || t.customer_type, value: t.revenue, color: SERIES[Object.keys(CUSTOMER_TYPES).indexOf(t.customer_type)] || SERIES[i + 2] }))),
        ['Type', 'Revenue', 'Bills', 'Customers'], c.types.map((t) => [CUSTOMER_TYPES[t.customer_type] || t.customer_type, money(t.revenue), t.bills, t.customers])))}
      ${card('New and repeat customers', stackedBar([{ label: 'New (first bill in this period)', value: nvr.new, color: SERIES[2] },
        { label: 'Repeat (bought before)', value: nvr.repeat, color: SERIES[0] }], { format: (v) => `${num(v)} customers` }), 'Named customers only; walk-ins are not counted')}
    </div>
    ${c.dues_aging ? card('Credit outstanding by age', withTable(
      html`<div class="value hero-figure">${money(c.dues_total)}</div>
        ${stackedBar(c.dues_aging.map((b, i) => ({ label: b.label, value: b.amount, color: ordinalColor(i, c.dues_aging.length) })), { emptyText: '✓ No credit outstanding.' })}`,
      ['Age', 'Outstanding', 'Bills'], c.dues_aging.map((b) => [b.label, money(b.amount), b.bills])), 'All unpaid credit today, by how old the bill is') : ''}
    ${card('Top customers', html`${barList(c.top.map((x) => ({ label: x.name, value: x.revenue, color: SERIES[Object.keys(CUSTOMER_TYPES).indexOf(x.customer_type)] || SERIES[0],
      sub: `${x.bills} bills • last ${shortDate(x.last_visit)}${x.outstanding > 0 ? ` • owes ${money(x.outstanding)}` : ''}` })), { name: 'Revenue' })}
      ${c.top.length ? legend([{ name: 'Retail', color: SERIES[0] }, { name: 'Wholesale', color: SERIES[1] }]) : ''}`, 'Named customers in this period')}`;
}

function team(d) {
  const staff = d.team.staff;
  return html`${card('Sales by person', withTable(
      barList(staff.map((x) => ({ label: x.name, value: x.sales, sub: `${x.bills} bills • ${pct(x.share)}` })), { name: 'Sales', emptyText: 'No bills in this period.' }),
      ['Person', 'Sales', 'Bills', 'Share'], staff.map((x) => [x.name, money(x.sales), x.bills, pct(x.share)])), 'Who made the bills')}
    ${card('Team details', table(['Person', 'Bills', 'Sales', 'Average bill', 'Discounts given', 'Deleted', 'Edited', 'Refunds'],
      staff.map((x) => html`<tr><td>${x.name}</td><td>${x.bills}</td><td>${money(x.sales)}</td><td>${money(x.avg_bill)}</td>
        <td>${money(x.discounts)}</td><td>${x.voids}</td><td>${x.edits}</td><td>${money(x.refunds)}</td></tr>`), 'No activity in this period.'),
      'Deleted and edited count the bills each person deleted or edited')}`;
}

function stock(d) {
  const s = d.stock;
  const color = categoryColors(d);
  const atCost = has(s.totals, 'inventory_cost');
  return html`<div class="grid kpis">
      ${statTile({ label: 'Stock value (selling price)', value: money(s.totals.retail_value), sub: `${num(s.totals.units)} units • ${s.totals.products} products` })}
      ${atCost ? statTile({ label: 'Stock value (cost)', value: money(s.totals.inventory_cost), sub: 'What the stock cost you' }) : ''}
      ${statTile({ label: 'Out of stock', value: num(s.totals.out_of_stock), sub: s.totals.out_of_stock ? '⛔ Cannot be billed' : '✓ None' })}
      ${statTile({ label: 'Low stock', value: num(s.totals.low), sub: 'At or below the refill level' })}
    </div>
    ${s.storage?.limit_kg ? card('Licence storage', meter({ label: 'Explosive content stored', value: s.storage.current_kg, limit: s.storage.limit_kg, format: (v) => `${num(v)} kg`,
      sub: s.storage.over ? '⚠ Over the licence limit' : 'Within the licence limit' })) : ''}
    ${card('Stock value by category', withTable(
      barList(s.categories.map((c) => ({ label: c.category, value: c.retail_value, color: color(c.category),
        sub: `${num(c.units)} units${c.out_of_stock ? ` • ${c.out_of_stock} out of stock` : ''}${c.low ? ` • ${c.low} low` : ''}` })), { name: 'Stock value' }),
      ['Category', 'Products', 'Units', 'At selling price', ...(atCost ? ['At cost'] : []), 'Out of stock', 'Low'],
      s.categories.map((c) => [c.category, c.products, num(c.units), money(c.retail_value), ...(atCost ? [money(c.inventory_cost)] : []), c.out_of_stock, c.low])),
      'At selling price; current stock, not limited to the period')}
    <div class="grid two">
      ${card('Running out soon', table(['Product', 'Stock', 'Sells per day', 'Days left'], s.running_out.map((x) => html`<tr><td>${x.name}<div class="small muted">${x.sku}</div></td>
        <td>${num(x.stock)}</td><td>${num(x.per_day)}</td><td><span class="tag ${x.days_left <= 3 ? 'bad' : 'warn'}">${x.days_left <= 3 ? '⛔' : '⚠'} ${num(Math.floor(x.days_left))}</span></td></tr>`),
        '✓ Nothing runs out in the next 14 days at the current pace.'), 'At the last 30 days’ pace')}
      ${card('Not selling', table(['Product', 'Stock', 'Value', 'Last sold'], s.dead_stock.map((x) => html`<tr><td>${x.name}<div class="small muted">${x.sku}</div></td>
        <td>${num(x.stock)}</td><td>${money(x.retail_value)}</td><td>${x.last_sale ? shortDate(x.last_sale) : 'Never'}</td></tr>`),
        `✓ Every product in stock sold in the last ${s.dead_stock_days} days.`), `In stock, no sale in ${s.dead_stock_days} days`)}
    </div>`;
}

function finance(d) {
  const f = d.finance;
  const pnl = f.pnl;
  const profit = has(pnl, 'gross_profit');
  return html`<div class="grid kpis">
      ${statTile({ label: 'Sales', value: money(pnl.sales) })}
      ${profit ? statTile({ label: 'Gross profit', value: money(pnl.gross_profit), sub: `${pct(d.sales.kpi.gross_margin)} margin` }) : ''}
      ${statTile({ label: 'Expenses', value: money(pnl.expenses), sub: pnl.sales ? `${pct(Math.round((pnl.expenses / pnl.sales) * 1000) / 10)} of sales` : '' })}
      ${profit ? statTile({ label: 'Net profit', value: money(pnl.net_profit), sub: pnl.net_profit < 0 ? '⛔ Loss after expenses' : '✓ After cost of goods and expenses' }) : ''}
    </div>
    ${profit ? card('From sales to net profit', withTable(
      waterfall([{ label: 'Sales', value: pnl.sales, kind: 'total' }, { label: 'Cost of goods', value: pnl.cogs, kind: 'minus' },
        { label: 'Gross profit', value: pnl.gross_profit, kind: 'total' }, { label: 'Expenses', value: pnl.expenses, kind: 'minus' },
        { label: 'Net profit', value: pnl.net_profit, kind: 'total' }], { width: size.full }),
      ['Line', 'Amount'], [['Sales', money(pnl.sales)], ['Cost of goods', `−${money(pnl.cogs)}`], ['Gross profit', money(pnl.gross_profit)],
        ['Expenses', `−${money(pnl.expenses)}`], ['Net profit', money(pnl.net_profit)]])) : ''}
    ${profit && d.period.days > 1 ? trendChart(d, { withProfit: true }) : ''}
    <div class="grid two">
      ${f.expense_categories ? card('Expenses by category', withTable(
        barList(f.expense_categories.map((x) => ({ label: x.category, value: x.amount, sub: `${x.entries} ${x.entries === 1 ? 'entry' : 'entries'}` })), { name: 'Expenses', emptyText: 'No expenses in this period.' }),
        ['Category', 'Amount', 'Entries'], f.expense_categories.map((x) => [x.category, money(x.amount), x.entries]))) : ''}
      ${f.expense_trend && d.period.days > 1 ? card('Expenses by day', columnChart({ points: f.expense_trend.map((x) => ({ label: longDate(x.day), tick: shortDate(x.day), value: x.amount })), name: 'Expenses', emptyText: 'No expenses in this period.', width: size.half })) : ''}
    </div>
    ${card('Sales targets', html`<div class="grid two">${f.targets.map((x) => meter({ label: x.label, value: x.actual, limit: x.target, sub: x.start === x.end ? shortDate(x.start) : `${shortDate(x.start)} – ${shortDate(x.end)}` }))}</div>`,
      'Set targets in Settings')}`;
}

const RENDERERS = { overview, sales, products, customers, team, stock, finance };
const available = (d) => TABS.filter(([key]) => key === 'overview' || key === 'sales' || key === 'products' || d[key]);

// ---- page --------------------------------------------------------------------

function filters(d) {
  return html`<div class="dash-filters">
    <div class="pill-nav">${PRESETS.map(([value, label]) =>
      html`<button class="${value === view.preset ? 'active' : ''}" data-action="dash.preset" data-preset="${value}">${label}</button>`)}</div>
    <form class="row wrap dash-range" data-submit="dash.range">
      <input class="input" type="date" name="start" value="${d?.period.start || ''}" aria-label="From" required>
      <span class="muted small">to</span>
      <input class="input" type="date" name="end" value="${d?.period.end || ''}" max="${todayISO()}" aria-label="To" required>
      <button class="button">Apply</button></form>
  </div>`;
}

function draw() {
  const d = view.data;
  const tabs = available(d);
  if (!tabs.some(([key]) => key === view.tab)) view.tab = 'overview';
  resetCharts();
  measure();
  const period = d.period.start === d.period.end ? longDate(d.period.start) : `${longDate(d.period.start)} – ${longDate(d.period.end)}`;
  setHtml($('#page'), html`<div class="dashboard">${filters(d)}
    <div class="between dash-period"><span class="small muted">${period} • compared with ${shortDate(d.period.prev_start)}${d.period.days > 1 ? ` – ${shortDate(d.period.prev_end)}` : ''}</span>
      ${d.scope === 'own' ? html`<span class="tag">Showing only your own bills</span>` : ''}</div>
    <div class="tabs" role="tablist">${tabs.map(([key, label]) =>
      html`<button role="tab" aria-selected="${key === view.tab}" class="${key === view.tab ? 'active' : ''}" data-action="dash.tab" data-tab="${key}">${label}</button>`)}</div>
    <div class="dash-body grid">${RENDERERS[view.tab](d)}</div></div>`);
}

async function load() {
  const page = $('#page');
  page.querySelector('.dashboard')?.classList.add('refreshing');
  const query = view.preset === 'custom' ? { start: view.start, end: view.end } : { preset: view.preset };
  const [data, today] = await Promise.all([
    api.get('/api/insights', query),
    can('dashboard.view') ? api.get('/api/dashboard', { date: todayISO() }) : Promise.resolve(null),
  ]);
  view.data = data;
  view.today = today;
  draw();
}

async function render() {
  try {
    await load();
  } catch (error) {
    setHtml($('#page'), html`${filters(view.data)}${errorBox(error)}`);
  }
}

// Redraw at the new size after the window is resized (charts are drawn at pixel widths).
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (view.data && $('.dashboard') && Math.abs($('#page').clientWidth - (size.page || 0)) > 40) draw();
  }, 200);
});

registerActions({
  'dash.preset': (el) => {
    view.preset = el.dataset.preset;
    return render();
  },
  'dash.range': (form) => {
    view.preset = 'custom';
    view.start = form.elements.start.value;
    view.end = form.elements.end.value;
    return render();
  },
  'dash.tab': (el) => {
    view.tab = el.dataset.tab;
    draw();
  },
});

registerPage({ name: 'dashboard', icon: 'dashboard', group: 'Overview', label: 'Dashboard', permission: ['dashboard.view', 'analytics.view'], render });
