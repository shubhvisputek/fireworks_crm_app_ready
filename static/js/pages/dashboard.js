import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { money, num, todayISO } from '../core/format.js';
import { registerPage } from '../core/router.js';
import { errorBox, kpi } from '../ui/widgets.js';

async function render() {
  const page = $('#page');
  try {
    const d = await api.get('/api/dashboard', { date: todayISO() });
    const progress = d.target ? Math.min(100, (d.today.sales / d.target) * 100) : 0;
    const trend = d.today.sales >= d.yesterday.sales ? '▲' : '▼';
    setHtml(page, html`
      <div class="grid kpis">
        ${kpi("Today's Sales", money(d.today.sales), `${d.today.bills} bills • avg ${money(d.today.avg_bill)}`)}
        ${'gross_profit' in d.today ? kpi('Gross Profit', money(d.today.gross_profit), `${num(d.today.gross_margin)}% margin`) : ''}
        ${kpi("Today's Expenses", money(d.expenses), 'gross_profit' in d.today ? `Net ${money(d.today.gross_profit - d.expenses)}` : '')}
        ${kpi('Low Stock', d.low_stock, 'Products needing refill')}
      </div><br>
      <div class="grid two">
        <div class="card hero"><div class="between"><div><div class="small muted">TODAY'S SALES PROGRESS</div><div class="value">${money(d.today.sales)}</div>
          <div class="small">Target ${money(d.target)} • Remaining ${money(Math.max(0, d.target - d.today.sales))}</div></div><span class="tag">${num(progress)}%</span></div><br>
          <div class="progress"><div style="width:${progress}%"></div></div><br>
          <div class="small muted">vs yesterday: ${trend} ${money(Math.abs(d.today.sales - d.yesterday.sales))}</div></div>
        <div class="card"><h3>Inventory snapshot</h3><div class="grid two">
          ${'inventory_cost' in d ? html`<div><div class="small muted">At cost</div><strong>${money(d.inventory_cost)}</strong></div>` : ''}
          ${d.storage?.limit_kg ? html`<div><div class="small muted">Licence storage</div><strong>${num(d.storage.current_kg)} / ${num(d.storage.limit_kg)} kg</strong></div>` : ''}
          <div><div class="small muted">Low stock</div><strong>${d.low_stock}</strong></div>
          <div><div class="small muted">Bills today</div><strong>${d.today.bills}</strong></div></div></div>
      </div><br>
      <div class="card"><h3>Needs attention</h3><div class="grid">
        ${d.storage?.over ? html`<div class="notice bad"><strong>Licence storage exceeded:</strong> ${num(d.storage.current_kg)} kg stored, limit ${num(d.storage.limit_kg)} kg.</div>` : ''}
        ${d.attention.length ? d.attention.map((x) => html`
        <div class="between notice ${x.stock <= 0 ? 'bad' : 'warn'}"><span><strong>${x.name}</strong><br>
          <span class="small muted">${x.sku} • Refill at ${num(x.reorder_level)} units</span></span><strong>${num(x.stock)} left</strong></div>`)
        : html`<div class="notice good">All products have sufficient stock.</div>`}</div></div>`);
  } catch (error) {
    setHtml(page, errorBox(error));
  }
}

registerPage({ name: 'dashboard', label: 'Dashboard', permission: 'dashboard.view', render });
