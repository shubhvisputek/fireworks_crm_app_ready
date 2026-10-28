// Stock overview, purchases (GRN) with suppliers, stock adjustments, licence storage gauge and the seasonal reorder plan.
import { api } from '../core/api.js';
import { $, $$, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money, num, todayISO } from '../core/format.js';
import { can, loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, field, formModal, openModal, toast } from '../ui/feedback.js';
import { withStorageConfirm } from '../ui/share.js';
import { brandTag, kpi, productOptions, table } from '../ui/widgets.js';
import { showProductDetail } from './products.js';

const ADJUSTMENT_TYPES = [['DAMAGE', 'Damage (reduce)'], ['BREAKAGE', 'Breakage (reduce)'], ['MOISTURE', 'Moisture (reduce)'],
  ['EXPIRED', 'Expired (reduce)'], ['MISSING', 'Missing (reduce)'], ['FOUND', 'Found (add)'], ['CORRECTION', 'Count correction (add)']];

const sorted = () => [...state.products].sort((a, b) => String(a.sku).localeCompare(String(b.sku), undefined, { numeric: true }));

function storageCard(storage) {
  if (!storage?.limit_kg) return '';
  const pct = Math.min(100, storage.pct);
  return html`<div class="card ${storage.over ? 'hero' : ''}"><div class="between"><h3>Licence storage</h3>
      <span class="tag ${storage.over ? 'bad' : pct > 85 ? 'warn' : 'good'}">${num(storage.current_kg)} / ${num(storage.limit_kg)} kg</span></div>
    <div class="progress"><div style="width:${pct}%"></div></div>
    ${storage.over ? html`<div class="notice bad" style="margin-top:8px">Stored explosive content is above the licence limit.</div>` : ''}</div><br>`;
}

async function render() {
  const products = sorted();
  const storage = can(['inventory.manage', 'purchases.manage']) ? await api.get('/api/inventory/storage') : null;
  const status = (p) => (p.current_stock_base <= 0 ? 'bad' : p.current_stock_base <= p.reorder_level ? 'warn' : 'good');
  setHtml($('#page'), html`<div class="row wrap">
      ${can('purchases.manage') ? html`<button class="button primary" data-action="inventory.purchase">+ Add Stock / GRN</button>` : ''}
      ${can('inventory.manage') ? html`<button class="button" data-action="inventory.adjust">Stock Adjustment</button>
        <button class="button" data-action="inventory.reorder">Seasonal Reorder Plan</button>` : ''}</div><br>
    ${storageCard(storage)}
    <div class="grid kpis">${kpi('Total Products', products.length)}${kpi('Low Stock', products.filter((p) => p.current_stock_base <= p.reorder_level).length)}
      ${kpi('Out of Stock', products.filter((p) => p.current_stock_base <= 0).length)}</div><br>
    <div class="card"><h3>Current Stock</h3>${table(['Product ID', 'Product', 'Unit', 'Available', 'Minimum', 'Default Price', ''], products.map((p) => html`<tr>
      <td>${p.sku}</td><td>${p.name}${brandTag(p.brand)}</td><td>${p.unit}</td><td><span class="tag ${status(p)}">${num(p.current_stock_base)}</span></td>
      <td>${num(p.reorder_level)}</td><td>${money(p.default_unit_price)}</td>
      <td>${can('catalog.manage') ? html`<button class="button" data-action="inventory.view" data-id="${p.id}">View</button>` : ''}</td></tr>`), 'No products yet.')}</div>`);
}

const itemRow = (index) => html`<div class="formgrid grn-row" style="margin-bottom:6px">
  <label class="full">Product ${index + 1}<select class="select grn-product">${productOptions(sorted()).map(([value, label]) => html`<option value="${value}">${label}</option>`)}</select></label>
  <label>Quantity<input class="input grn-qty" type="number" min="0.01" step="0.01" value="1"></label>
  <label>Cost per unit<input class="input grn-cost" type="number" min="0" step="0.01" value="0"></label>
  <label>Batch / lot<input class="input grn-batch"></label></div>`;

registerActions({
  'inventory.view': (el) => showProductDetail(Number(el.dataset.id), render),
  'inventory.purchase': async () => {
    if (!state.products.length) return toast('Add products first.', 'error');
    const suppliers = await api.get('/api/suppliers');
    openModal('Add Stock / GRN', html`<form data-submit="inventory.savePurchase"><div class="formgrid">
        ${field({ name: 'supplier_id', label: 'Supplier', type: 'select', value: '', options: [['', '— New / no supplier —'], ...suppliers.map((s) => [s.id, s.name])] })}
        ${field({ name: 'supplier_name', label: 'New supplier name (if not in the list)' })}
        ${field({ name: 'purchase_date', label: 'Purchase date', type: 'date', value: todayISO() })}
        ${field({ name: 'invoice_number', label: 'Supplier invoice no.' })}
        ${field({ name: 'freight', label: 'Freight', type: 'number', value: 0 })}
        ${field({ name: 'location', label: 'Location' })}</div><br>
      <div id="grnItems">${itemRow(0)}</div>
      <button type="button" class="button" data-action="inventory.addItem">+ Another product</button><br><br>
      <div class="row" style="justify-content:flex-end"><button type="button" class="button" data-action="modal.close">Cancel</button>
        <button class="button primary">Add Stock</button></div></form>`);
  },
  'inventory.addItem': () => $('#grnItems').insertAdjacentHTML('beforeend', String(itemRow($$('.grn-row').length))),
  'inventory.savePurchase': async (form) => {
    const v = formValues(form);
    const items = $$('.grn-row', form).map((row) => ({
      product_id: Number($('.grn-product', row).value), qty: Number($('.grn-qty', row).value),
      cost_price: Number($('.grn-cost', row).value) || 0, batch_number: $('.grn-batch', row).value, location: v.location,
    })).filter((item) => item.qty > 0);
    const payload = { supplier_id: v.supplier_id ? Number(v.supplier_id) : null, supplier_name: v.supplier_name, purchase_date: v.purchase_date,
      invoice_number: v.invoice_number, freight: Number(v.freight) || 0, items };
    const result = await withStorageConfirm((allow) => api.post('/api/purchases', { ...payload, allow_over_limit: allow }));
    if (!result) return;
    await loadReferenceData();
    closeModal();
    await render();
    toast(`Stock added (${result.purchase_number}, ${money(result.total)})`);
  },
  'inventory.adjust': () => {
    if (!state.products.length) return toast('Add products first.', 'error');
    formModal('Stock Adjustment', [
      { name: 'product_id', label: 'Product', type: 'select', options: productOptions(sorted()), required: true, full: true },
      { name: 'type', label: 'Type', type: 'select', value: 'DAMAGE', options: ADJUSTMENT_TYPES },
      { name: 'qty', label: 'Quantity', type: 'number', value: 1, required: true },
      { name: 'reason', label: 'Reason' }, { name: 'notes', label: 'Notes' },
    ], 'inventory.saveAdjustment');
  },
  'inventory.saveAdjustment': async (form) => {
    const v = formValues(form);
    const payload = { ...v, product_id: Number(v.product_id), qty: Number(v.qty) };
    if (!(await withStorageConfirm((allow) => api.post('/api/inventory/adjust', { ...payload, allow_over_limit: allow })))) return;
    await loadReferenceData();
    closeModal();
    await render();
    toast('Stock adjusted');
  },
  'inventory.reorder': () => showReorderPlan({}),
  'inventory.reorderFilter': (form) => showReorderPlan(formValues(form)),
});

async function showReorderPlan(filters) {
  const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
  const plan = await api.get('/api/reorder-plan', params);
  const withCost = 'total_cost' in plan;
  const rows = plan.rows.filter((row) => row.suggested > 0 || row.sold_last_season > 0);
  openModal('Seasonal Reorder Plan', html`<p class="small muted">Last season's sales plus growth, minus stock in hand. Defaults to last year's season dates from Settings.</p>
    <form data-submit="inventory.reorderFilter"><div class="formgrid">
      ${field({ name: 'start', label: 'Compare season from', type: 'date', value: plan.season.start })}
      ${field({ name: 'end', label: 'to', type: 'date', value: plan.season.end })}
      ${field({ name: 'growth', label: 'Expected growth %', type: 'number', value: plan.growth_pct, min: -100, step: 1 })}</div><br>
      <button class="button">Recalculate</button></form><br>
    ${withCost ? html`<div class="notice">Estimated purchase cost: <strong>${money(plan.total_cost)}</strong></div><br>` : ''}
    ${table(['Product', 'Sold last season', 'In stock', 'Target', 'Suggested order', ...(withCost ? ['Est. cost'] : [])], rows.map((row) => html`<tr>
      <td>${row.sku} • ${row.name}${brandTag(row.brand)}</td><td>${num(row.sold_last_season)}</td><td>${num(row.stock)}</td><td>${num(row.target)}</td>
      <td><strong>${num(row.suggested)} ${row.unit}</strong></td>${withCost ? html`<td>${money(row.cost)}</td>` : ''}</tr>`), 'No sales in that season to plan from.')}`);
}

registerPage({ name: 'inventory', icon: 'inventory', group: 'Stock', label: 'Inventory', permission: ['inventory.manage', 'purchases.manage'], render });
