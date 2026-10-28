// Small reusable view pieces.
import { html } from '../core/html.js';
import { money, num } from '../core/format.js';
import { state } from '../core/state.js';
import { icon } from './icons.js';

/** A friendly "nothing here" message with an optional next step (html button markup). */
export const emptyState = (title, text = '', action = '', iconName = 'empty') =>
  html`<div class="empty-state">${icon(iconName)}<strong>${title}</strong>${text ? html`<span class="small">${text}</span>` : ''}${action}</div>`;

export const kpi = (label, value, sub = '') =>
  html`<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div>${sub ? html`<div class="sub">${sub}</div>` : ''}</div>`;

const SEARCH_FROM = 10; // lists longer than this get a search box
const PAGE_SIZE = 50; // ...and longer than this show 50 rows at a time with "Show more" (ui/lists.js)

// opts.search=false when the page has its own search (Products).
export function table(headers, rows, emptyText = 'Nothing to show yet.', { search = true } = {}) {
  const body = html`<div class="table-wrap"><table class="table"><thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
    <tbody>${rows.length ? rows : html`<tr class="empty-row"><td colspan="${headers.length}">${emptyState(emptyText)}</td></tr>`}</tbody></table></div>`;
  if (rows.length <= SEARCH_FROM && rows.length <= PAGE_SIZE) return body;
  return html`<div class="list" data-list data-page-size="${PAGE_SIZE}">
    ${search && rows.length > SEARCH_FROM ? html`<div class="list-tools"><label class="list-search">${icon('search')}
      <input class="input" type="search" placeholder="Search this list" aria-label="Search this list" data-input="list.filter" autocomplete="off"></label>
      <span class="list-count small muted" aria-live="polite"></span></div>` : html`<div class="list-tools"><span class="list-count small muted"></span></div>`}
    ${body}<div class="list-footer"><span class="list-none muted small is-hidden">No matching rows.</span>
      <button type="button" class="button list-more is-hidden" data-action="list.more">Show more</button></div></div>`;
}

export function barChart(points, emptyText = 'No data in this period.') {
  if (!points.length) return html`<div class="muted small">${emptyText}</div>`;
  const max = Math.max(...points.map((p) => p.value), 1);
  return html`<div class="chart"><div class="bars">${points.map((p) =>
    html`<div class="bar" style="height:${Math.max(8, (p.value / max) * 88)}%" title="${p.label}: ${money(p.value)}"><b>${money(p.value)}</b><span>${p.label}</span></div>`)}</div></div>`;
}

// Products are shown with their brand / company everywhere: two companies can sell a same-named item at different prices.
export const brandTag = (brand) => (brand ? html` <span class="tag company">${brand}</span>` : '');
export const productTitle = (p) => html`<strong>${p.name}</strong>${brandTag(p.brand)}`;
export const productText = (p, brand = p.brand) => (brand ? `${p.name} (${brand})` : String(p.name));
export const productOptions = (products = state.products) =>
  products.map((p) => [p.id, `${p.sku} • ${productText(p)} (stock ${num(p.current_stock_base)})`]);

export const errorBox = (error) => html`<div class="notice bad">${error.message || String(error)}</div>`;
