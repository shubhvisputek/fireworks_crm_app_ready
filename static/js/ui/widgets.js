// Small reusable view pieces.
import { html } from '../core/html.js';
import { money, num } from '../core/format.js';
import { state } from '../core/state.js';

export const kpi = (label, value, sub = '') =>
  html`<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div>${sub ? html`<div class="sub">${sub}</div>` : ''}</div>`;

export function table(headers, rows, emptyText = 'Nothing to show yet.') {
  return html`<div class="table-wrap"><table class="table"><thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
    <tbody>${rows.length ? rows : html`<tr><td colspan="${headers.length}" class="muted">${emptyText}</td></tr>`}</tbody></table></div>`;
}

export function barChart(points, emptyText = 'No data in this period.') {
  if (!points.length) return html`<div class="muted small">${emptyText}</div>`;
  const max = Math.max(...points.map((p) => p.value), 1);
  return html`<div class="chart"><div class="bars">${points.map((p) =>
    html`<div class="bar" style="height:${Math.max(8, (p.value / max) * 88)}%" title="${p.label}: ${money(p.value)}"><b>${money(p.value)}</b><span>${p.label}</span></div>`)}</div></div>`;
}

export const productOptions = (products = state.products) =>
  products.map((p) => [p.id, `${p.sku} • ${p.name} (stock ${num(p.current_stock_base)})`]);

export const errorBox = (error) => html`<div class="notice bad">${error.message || String(error)}</div>`;
