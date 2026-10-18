// Charts drawn as inline SVG/HTML, with one shared hover/focus tooltip.
//
// Rules followed everywhere (see ARCHITECTURE.md, "Charts"):
// - categorical colours are assigned in a fixed order and follow the entity, never its rank;
// - one y-axis per chart; thin marks, 4px rounded bar ends, 2px gaps between touching fills;
// - text uses ink colours, never the series colour; a legend for two or more series;
// - every chart has a table view, so the tooltip never is the only way to read a value.
import { html, raw } from '../core/html.js';
import { money, num } from '../core/format.js';

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
export const OTHER = '#b4b2a9';
const PREVIOUS = '#898781';
const RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];
const ORDINAL = ['#86b6ef', '#3987e5', '#1c5cab', '#0d366b'];
const EMPTY_CELL = '#f0efec';

// Indian short form (K, L, Cr). Browsers disagree on Intl's compact en-IN output, so it is done here.
export function compact(value) {
  const n = Number(value || 0);
  const abs = Math.abs(n);
  const short = (div, unit) => `${Math.round((n / div) * 10) / 10}${unit}`;
  if (abs >= 1e7) return short(1e7, 'Cr');
  if (abs >= 1e5) return short(1e5, 'L');
  if (abs >= 1e3) return short(1e3, 'K');
  return String(Math.round(n * 100) / 100);
}
export const compactMoney = (value) => `₹${compact(value)}`;
export const pct = (value) => `${num(value)}%`;

const empty = (text) => html`<div class="chart-empty muted small">${text}</div>`;

// ---- shared tooltip ----------------------------------------------------------

const crosshairCharts = new Map();
let chartCounter = 0;
let tipElement;

/** Forget crosshair data from charts that are no longer on screen. */
export function resetCharts() {
  crosshairCharts.clear();
}

function tooltip() {
  if (!tipElement) {
    tipElement = document.createElement('div');
    tipElement.className = 'chart-tip';
    tipElement.setAttribute('role', 'status');
    tipElement.hidden = true;
    document.body.append(tipElement);
  }
  return tipElement;
}

// rows: [{ value, name?, color? }]. Text goes in with textContent: labels are data.
function showTip(title, rows, x, y) {
  const tip = tooltip();
  tip.replaceChildren();
  const head = document.createElement('div');
  head.className = 'chart-tip-title';
  head.textContent = title;
  tip.append(head);
  for (const row of rows) {
    const line = document.createElement('div');
    line.className = 'chart-tip-row';
    if (row.color) {
      const key = document.createElement('i');
      key.style.background = row.color;
      line.append(key);
    }
    const value = document.createElement('strong');
    value.textContent = row.value;
    line.append(value);
    if (row.name) {
      const name = document.createElement('span');
      name.textContent = row.name;
      line.append(name);
    }
    tip.append(line);
  }
  tip.hidden = false;
  const box = tip.getBoundingClientRect();
  const left = Math.min(x + 14, window.innerWidth - box.width - 8);
  const top = y + 14 + box.height > window.innerHeight ? y - box.height - 10 : y + 14;
  tip.style.left = `${Math.max(8, left)}px`;
  tip.style.top = `${Math.max(8, top)}px`;
}

function hideTip() {
  if (tipElement) tipElement.hidden = true;
  document.querySelectorAll('.xhair').forEach((line) => line.setAttribute('visibility', 'hidden'));
}

function markTip(element, x, y) {
  const rows = [{ value: element.dataset.tipValue, name: element.dataset.tipName, color: element.dataset.tipColor }];
  if (element.dataset.tipExtra) rows.push({ value: element.dataset.tipExtra });
  showTip(element.dataset.tipTitle, rows, x, y);
}

function crosshairAt(overlay, index, x, y) {
  const chart = crosshairCharts.get(overlay.dataset.xhair);
  if (!chart) return;
  const i = Math.max(0, Math.min(chart.labels.length - 1, index));
  overlay.dataset.index = i;
  const line = overlay.parentNode.querySelector('.xhair');
  line.setAttribute('x1', chart.xs[i]);
  line.setAttribute('x2', chart.xs[i]);
  line.setAttribute('visibility', 'visible');
  showTip(chart.labels[i], chart.series.map((s) => ({ value: chart.format(s.values[i]), name: s.name, color: s.color })), x, y);
}

function nearestIndex(overlay, clientX) {
  const chart = crosshairCharts.get(overlay.dataset.xhair);
  const svg = overlay.ownerSVGElement;
  const box = svg.getBoundingClientRect();
  const x = ((clientX - box.left) / box.width) * svg.viewBox.baseVal.width;
  let best = 0;
  chart.xs.forEach((value, i) => {
    if (Math.abs(value - x) < Math.abs(chart.xs[best] - x)) best = i;
  });
  return best;
}

function installTooltips() {
  document.addEventListener('pointermove', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const overlay = target?.closest('[data-xhair]');
    if (overlay) return crosshairAt(overlay, nearestIndex(overlay, event.clientX), event.clientX, event.clientY);
    const mark = target?.closest('[data-tip-title]');
    if (mark) return markTip(mark, event.clientX, event.clientY);
    if (tipElement && !tipElement.hidden) hideTip();
  });
  document.addEventListener('focusin', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const box = target?.getBoundingClientRect();
    if (target?.matches('[data-tip-title]')) markTip(target, box.left + box.width / 2, box.bottom);
    else if (target?.matches('[data-xhair]')) crosshairAt(target, Number(target.dataset.index || 0), box.left + box.width / 2, box.top + 20);
  });
  document.addEventListener('focusout', hideTip);
  document.addEventListener('keydown', (event) => {
    const overlay = event.target instanceof Element ? event.target.closest('[data-xhair]') : null;
    if (!overlay || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const box = overlay.getBoundingClientRect();
    crosshairAt(overlay, Number(overlay.dataset.index || 0) + (event.key === 'ArrowRight' ? 1 : -1), box.left + box.width / 2, box.top + 20);
  });
  window.addEventListener('scroll', hideTip, { passive: true });
}

if (typeof document !== 'undefined') installTooltips();

// ---- pieces ------------------------------------------------------------------

function niceMax(value) {
  if (value <= 0) return 1;
  const step = 10 ** Math.floor(Math.log10(value));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * step >= value) return m * step;
  return 10 * step;
}

function everyNth(count, maxLabels) {
  return Math.max(1, Math.ceil(count / maxLabels));
}

export function legend(items) {
  return html`<div class="chart-legend">${items.map((item) =>
    html`<span><i class="${item.line ? 'line' : ''} ${item.dashed ? 'dashed' : ''}" style="--key:${item.color}"></i>${item.name}</span>`)}</div>`;
}

/** A chart plus a collapsible table with the same numbers. */
export function withTable(chart, headers, rows) {
  if (!rows.length) return chart;
  return html`${chart}<details class="chart-table"><summary>Show as table</summary>
    <div class="table-wrap"><table class="table"><thead><tr>${headers.map((h) => html`<th>${h}</th>`)}</tr></thead>
    <tbody>${rows.map((row) => html`<tr>${row.map((cell) => html`<td>${cell}</td>`)}</tr>`)}</tbody></table></div></details>`;
}

// Bar path with a 4px rounded data end and a square base.
function columnPath(x, y, width, height) {
  const r = Math.min(4, width / 2, height);
  return `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height}Z`;
}

// ---- charts ------------------------------------------------------------------

/**
 * Line chart over one x axis. series: [{ name, values, color?, dashed?, area? }].
 * labels: x labels (full text for the tooltip); tick: short text for the axis.
 */
export function lineChart({ labels, ticks = labels, series, format = money, axisFormat = compactMoney, height = 220, width = 640, emptyText = 'No data in this period.' }) {
  const all = series.flatMap((s) => s.values);
  if (!labels.length || !all.some((value) => value)) return empty(emptyText);
  const W = Math.max(280, Math.round(width));
  const H = height;
  const m = { l: 46, r: 18, t: 14, b: 26 };
  const max = niceMax(Math.max(...all));
  const innerW = W - m.l - m.r;
  const innerH = H - m.t - m.b;
  const xs = labels.map((_, i) => m.l + (labels.length === 1 ? innerW / 2 : (i / (labels.length - 1)) * innerW));
  const y = (value) => m.t + innerH - (Number(value || 0) / max) * innerH;
  const id = `c${++chartCounter}`;
  crosshairCharts.set(id, { labels, xs, format, series: series.map((s, i) => ({ ...s, color: s.color || SERIES[i] })) });
  const nth = everyNth(labels.length, Math.min(7, Math.floor(W / 56)));
  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const paths = series.map((s, i) => {
    const color = s.color || SERIES[i];
    const points = s.values.map((value, n) => `${xs[n].toFixed(1)},${y(value).toFixed(1)}`);
    const last = s.values.length - 1;
    return html`${s.area ? raw(`<path d="M${xs[0]},${y(0)}L${points.join('L')}L${xs[last]},${y(0)}Z" fill="${color}" opacity="0.1"/>`) : ''}
      ${raw(`<path d="M${points.join('L')}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"${s.dashed ? ' stroke-dasharray="5 4"' : ''}/>`)}
      ${i === 0 ? raw(`<circle cx="${xs[last]}" cy="${y(s.values[last])}" r="4" fill="${color}" stroke="#fff" stroke-width="2"/>`) : ''}`;
  });
  const lastValue = series[0].values[series[0].values.length - 1];
  return html`${series.length > 1 ? legend(series.map((s, i) => ({ name: s.name, color: s.color || SERIES[i], line: true, dashed: s.dashed }))) : ''}
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${series.map((s) => s.name).join(', ')}">
      ${gridValues.map((value) => raw(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(value)}" y2="${y(value)}" class="${value ? 'grid' : 'baseline'}"/>`))}
      ${gridValues.map((value) => html`<text x="${m.l - 6}" y="${y(value) + 4}" class="tick" text-anchor="end">${axisFormat(value)}</text>`)}
      ${labels.map((_, i) => (i % nth === 0 || i === labels.length - 1) && (i === labels.length - 1 || labels.length - 1 - i >= nth / 2)
        ? html`<text x="${xs[i]}" y="${H - 6}" class="tick" text-anchor="middle">${ticks[i]}</text>` : '')}
      ${paths}
      <text x="${Math.min(xs[xs.length - 1], W - m.r)}" y="${Math.max(y(lastValue) - 10, 10)}" class="end-label" text-anchor="end">${axisFormat(lastValue)}</text>
      ${raw(`<line class="xhair" x1="0" x2="0" y1="${m.t}" y2="${m.t + innerH}" visibility="hidden"/>`)}
      <rect class="hit" x="${m.l - 10}" y="0" width="${innerW + 20}" height="${H}" data-xhair="${id}" tabindex="0" aria-label="Move with arrow keys to read values"></rect>
    </svg>`;
}

/** Vertical columns for one series, e.g. sales by hour. points: [{ label, tick?, value, extra? }]. */
export function columnChart({ points, format = money, axisFormat = compactMoney, height = 200, width = 640, name = '', color = SERIES[0], emptyText = 'No data in this period.' }) {
  if (!points.some((p) => p.value)) return empty(emptyText);
  const W = Math.max(280, Math.round(width));
  const H = height;
  const m = { l: 46, r: 10, t: 18, b: 26 };
  const max = niceMax(Math.max(...points.map((p) => p.value)));
  const innerW = W - m.l - m.r;
  const innerH = H - m.t - m.b;
  const band = innerW / points.length;
  const barW = Math.min(24, band - 2);
  const y = (value) => m.t + innerH - (value / max) * innerH;
  const peak = points.reduce((best, p, i) => (p.value > points[best].value ? i : best), 0);
  const nth = everyNth(points.length, Math.min(12, Math.floor(W / 64)));
  return html`<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${name}">
    ${[0, 0.5, 1].map((f) => raw(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(f * max)}" y2="${y(f * max)}" class="${f ? 'grid' : 'baseline'}"/>`))}
    ${[0, 0.5, 1].map((f) => html`<text x="${m.l - 6}" y="${y(f * max) + 4}" class="tick" text-anchor="end">${axisFormat(f * max)}</text>`)}
    ${points.map((p, i) => {
      const x = m.l + band * i + (band - barW) / 2;
      const h = Math.max(0, y(0) - y(p.value));
      return html`<g class="mark" data-tip-title="${p.label}" data-tip-value="${format(p.value)}" data-tip-name="${name}" data-tip-color="${color}"
          data-tip-extra="${p.extra || ''}" tabindex="${p.value ? 0 : -1}">
        <rect x="${m.l + band * i}" y="${m.t}" width="${band}" height="${innerH}" fill="transparent"></rect>
        ${p.value ? raw(`<path d="${columnPath(x, y(p.value), barW, h)}" fill="${color}"/>`) : ''}
        ${i % nth === 0 ? html`<text x="${x + barW / 2}" y="${H - 6}" class="tick" text-anchor="middle">${p.tick ?? p.label}</text>` : ''}
        ${i === peak ? html`<text x="${x + barW / 2}" y="${y(p.value) - 5}" class="end-label" text-anchor="middle">${axisFormat(p.value)}</text>` : ''}
      </g>`;
    })}
  </svg>`;
}

/** Horizontal bars with the value at the tip. rows: [{ label, value, sub?, color? }]. */
export function barList(rows, { format = money, name = '', emptyText = 'Nothing in this period.', color = SERIES[0] } = {}) {
  if (!rows.length) return empty(emptyText);
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return html`<div class="bar-list">${rows.map((r) => html`
    <div class="bar-row" data-tip-title="${r.label}" data-tip-value="${format(r.value)}" data-tip-name="${name}"
        data-tip-color="${r.color || color}" data-tip-extra="${r.sub || ''}" tabindex="0">
      <div class="bar-label"><span>${r.label}</span>${r.sub ? html`<small>${r.sub}</small>` : ''}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(1, (Math.abs(r.value) / max) * 100)}%;background:${r.color || color}"></div></div>
      <div class="bar-value">${format(r.value)}</div>
    </div>`)}</div>`;
}

/**
 * One 100% bar for part-to-whole (<= 6 parts; the rest fold into "Other").
 * parts: [{ label, value, color }]. Colours come from the caller so they follow the entity.
 */
export function stackedBar(parts, { format = money, emptyText = 'Nothing in this period.', maxParts = 6 } = {}) {
  let list = parts.filter((p) => p.value > 0);
  const total = list.reduce((sum, p) => sum + p.value, 0);
  if (!total) return empty(emptyText);
  if (list.length > maxParts) {
    const rest = list.slice(maxParts - 1);
    list = [...list.slice(0, maxParts - 1), { label: 'Other', value: rest.reduce((s, p) => s + p.value, 0), color: OTHER }];
  }
  return html`<div class="stack">${list.map((p) => html`<div class="stack-part" style="flex:${p.value} 1 0;background:${p.color}"
      data-tip-title="${p.label}" data-tip-value="${format(p.value)}" data-tip-extra="${pct((p.value / total) * 100)} of total"
      data-tip-color="${p.color}" tabindex="0"></div>`)}</div>
    <div class="stack-legend">${list.map((p) => html`<div><i style="background:${p.color}"></i><span>${p.label}</span>
      <strong>${format(p.value)}</strong><small class="muted">${pct((p.value / total) * 100)}</small></div>`)}</div>`;
}

/** Ordered buckets (e.g. dues age) take the ordinal blue ramp, lightest first. */
export const ordinalColor = (index, count) => ORDINAL[Math.round((index / Math.max(1, count - 1)) * (ORDINAL.length - 1))];

/** Weekday x hour grid on the sequential blue ramp. cells: [{ weekday 0=Sun, hour, sales, bills }]. */
export function heatmap(cells, { format = money, emptyText = 'No sales in this period.' } = {}) {
  if (!cells.length) return empty(emptyText);
  const hours = cells.map((c) => c.hour);
  const first = Math.min(9, ...hours);
  const last = Math.max(21, ...hours);
  const max = Math.max(...cells.map((c) => c.sales), 1);
  const at = new Map(cells.map((c) => [`${c.weekday}-${c.hour}`, c]));
  const days = [[1, 'Mon'], [2, 'Tue'], [3, 'Wed'], [4, 'Thu'], [5, 'Fri'], [6, 'Sat'], [0, 'Sun']];
  const range = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  const hourLabel = (h) => `${h % 12 || 12}${h < 12 ? 'am' : 'pm'}`;
  return html`<div class="heatmap" style="--cols:${range.length}">
    <span></span>${range.map((h) => html`<span class="hm-hour">${h % 3 === 0 ? hourLabel(h) : ''}</span>`)}
    ${days.map(([day, name]) => html`<span class="hm-day">${name}</span>${range.map((h) => {
      const cell = at.get(`${day}-${h}`);
      const color = cell ? RAMP[Math.min(RAMP.length - 1, Math.floor((cell.sales / max) * RAMP.length))] : EMPTY_CELL;
      return html`<span class="hm-cell" style="background:${color}" tabindex="${cell ? 0 : -1}"
        data-tip-title="${name} ${hourLabel(h)}–${hourLabel(h + 1)}" data-tip-value="${format(cell?.sales || 0)}"
        data-tip-extra="${cell ? `${cell.bills} bills` : 'No bills'}"></span>`;
    })}`)}
  </div>
  <div class="hm-scale small muted"><span>Less</span>${RAMP.map((c) => html`<i style="background:${c}"></i>`)}<span>More</span>
    <span class="hm-max">Busiest hour ${format(max)}</span></div>`;
}

/**
 * Waterfall from a starting total through deductions to a result.
 * steps: [{ label, value, kind: 'total' | 'minus' }]; totals are drawn from zero.
 */
export function waterfall(steps, { format = money, axisFormat = compactMoney, height = 230, width = 640 } = {}) {
  if (!steps.length || !steps[0].value) return empty('No sales in this period.');
  const W = Math.max(280, Math.round(width));
  const H = height;
  const m = { l: 46, r: 10, t: 22, b: 30 };
  const lowest = Math.min(0, ...steps.map((s) => s.value));
  const max = niceMax(Math.max(...steps.map((s) => s.value)));
  const innerH = H - m.t - m.b;
  const span = max - lowest;
  const y = (value) => m.t + ((max - value) / span) * innerH;
  const band = (W - m.l - m.r) / steps.length;
  const barW = Math.min(64, band * 0.6);
  let running = 0;
  const bars = steps.map((step, i) => {
    let top;
    let bottom;
    if (step.kind === 'total') {
      running = step.value;
      [top, bottom] = [Math.max(0, step.value), Math.min(0, step.value)];
    } else {
      top = running;
      running -= step.value;
      bottom = running;
    }
    const x = m.l + band * i + (band - barW) / 2;
    const negative = step.kind === 'total' && step.value < 0;
    const color = step.kind === 'total' ? (negative ? '#d03b3b' : SERIES[0]) : OTHER;
    const h = Math.max(1, y(bottom) - y(top));
    return html`<g class="mark" data-tip-title="${step.label}" data-tip-value="${step.kind === 'minus' ? '−' : ''}${format(step.value)}"
        data-tip-color="${color}" tabindex="0">
      <rect x="${m.l + band * i}" y="${m.t}" width="${band}" height="${innerH}" fill="transparent"></rect>
      ${raw(`<rect x="${x}" y="${y(top)}" width="${barW}" height="${h}" rx="3" fill="${color}"/>`)}
      <text x="${x + barW / 2}" y="${y(top) - 6}" class="end-label" text-anchor="middle">${step.kind === 'minus' ? '−' : ''}${axisFormat(step.value)}</text>
      <text x="${x + barW / 2}" y="${H - 8}" class="tick" text-anchor="middle">${step.label}</text>
    </g>`;
  });
  return html`${legend([{ name: 'Total', color: SERIES[0] }, { name: 'Deducted', color: OTHER }])}
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Profit and loss">
      ${raw(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}" class="baseline"/>`)}
      ${bars}
    </svg>`;
}

/** A ratio against a limit, e.g. sales vs target. */
export function meter({ label, value, limit, format = money, sub = '' }) {
  const ratio = limit ? value / limit : 0;
  const done = ratio >= 1;
  return html`<div class="meter">
    <div class="between"><span class="small">${label}</span>
      <span class="small"><strong>${pct(Math.round(ratio * 1000) / 10)}</strong>${done ? html` <span class="tag good">✓ Reached</span>` : ''}</span></div>
    <div class="meter-track" role="meter" aria-valuemin="0" aria-valuemax="${limit}" aria-valuenow="${value}" aria-label="${label}">
      <div style="width:${Math.min(100, ratio * 100)}%"></div></div>
    <div class="small muted">${format(value)} of ${format(limit)}${sub ? html` • ${sub}` : ''}</div>
  </div>`;
}

/** Tiny trend line for a stat tile: de-emphasised, with the latest point in the accent. */
export function sparkline(values) {
  if (values.length < 2 || !values.some((v) => v)) return '';
  const W = 120;
  const H = 32;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (W - 6) + 3, H - 3 - (v / max) * (H - 6)]);
  const [lx, ly] = pts[pts.length - 1];
  return raw(`<svg class="spark" viewBox="0 0 ${W} ${H}" aria-hidden="true"><path d="M${pts.map((p) => p.map((n) => n.toFixed(1)).join(',')).join('L')}"
    fill="none" stroke="${PREVIOUS}" stroke-width="1.5" stroke-linejoin="round"/><circle cx="${lx}" cy="${ly}" r="3" fill="${SERIES[0]}"/></svg>`);
}

/**
 * Stat tile: label, value, optional change vs the previous period, optional sparkline.
 * upIsGood=false flips the colour (e.g. discounts, voids).
 */
export function statTile({ label, value, current, previous, upIsGood = true, sub = '', spark = null, compare = 'previous period' }) {
  let delta = '';
  if (previous !== undefined && previous !== null) {
    if (!previous && !current) delta = html`<span class="delta flat">No change</span>`;
    else if (!previous) delta = html`<span class="delta ${upIsGood ? 'up' : 'down'}">▲ New vs ${compare}</span>`;
    else {
      const change = ((current - previous) / Math.abs(previous)) * 100;
      const good = change === 0 ? null : (change > 0) === upIsGood;
      delta = html`<span class="delta ${good === null ? 'flat' : good ? 'up' : 'down'}">${change > 0 ? '▲' : change < 0 ? '▼' : '■'} ${num(Math.abs(Math.round(change * 10) / 10))}% vs ${compare}</span>`;
    }
  }
  return html`<div class="card kpi stat"><div class="label">${label}</div>
    <div class="stat-row"><div class="value">${value}</div>${spark ? sparkline(spark) : ''}</div>
    ${delta}${sub ? html`<div class="sub">${sub}</div>` : ''}</div>`;
}
