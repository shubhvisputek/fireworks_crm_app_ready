import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { registerActions } from '../core/actions.js';
import { money, num } from '../core/format.js';
import { registerPage } from '../core/router.js';
import { barChart, kpi, table } from '../ui/widgets.js';

const PRESETS = [['today', 'Today'], ['yesterday', 'Yesterday'], ['7d', 'Last 7 Days'], ['month', 'This Month'], ['season', 'Season']];
let preset = 'today';

async function render() {
  const d = await api.get('/api/analytics', { preset });
  const k = d.kpi;
  setHtml($('#page'), html`<div class="pill-nav">${PRESETS.map(([value, label]) =>
      html`<button class="${value === preset ? 'active' : ''}" data-action="analytics.preset" data-preset="${value}">${label}</button>`)}</div>
    <div class="small muted" style="margin:8px 0">${d.period.start} to ${d.period.end}</div>
    <div class="grid kpis">${kpi('Total Sales', money(k.sales))}${kpi('Bills', k.bills)}${kpi('Avg Bill', money(k.avg_bill))}
      ${'gross_profit' in k ? kpi('Gross Profit', money(k.gross_profit), `${num(k.gross_margin)}% margin • Net ${money(d.net_profit)} after expenses`) : ''}</div><br>
    <div class="card"><h3>Sales by hour</h3>${barChart(d.hourly.map((h) => ({ label: `${h.hr}:00`, value: h.sales })), 'No sales in this period.')}</div><br>
    <div class="grid two">
      <div class="card"><h3>Top 10 Products</h3>${table(['Product', 'Revenue', 'Qty'], d.top_products.slice(0, 10).map((x) =>
        html`<tr><td>${x.name}</td><td>${money(x.revenue)}</td><td>${num(x.qty)}</td></tr>`), 'No sales in this period.')}</div>
      <div class="card"><h3>Bottom 10 Products</h3>${table(['Product', 'Sold', 'Stock'], d.bottom_products.map((x) =>
        html`<tr><td>${x.name}</td><td>${num(x.qty_sold)}</td><td>${num(x.stock)}</td></tr>`))}</div>
    </div><br>
    <div class="card"><h3>Payment analytics</h3>${d.payments.length ? d.payments.map((x) =>
      html`<div class="between notice"><span>${x.mode}</span><strong>${money(x.amount)}</strong></div>`) : html`<div class="muted small">No payments in this period.</div>`}</div>`);
}

registerActions({
  'analytics.preset': (el) => {
    preset = el.dataset.preset;
    render();
  },
});

registerPage({ name: 'analytics', label: 'Analytics', title: 'Sales Analytics', permission: 'analytics.view', render });
