// Stock overview, purchases (GRN) and stock adjustments.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money, num, todayISO } from '../core/format.js';
import { loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, toast } from '../ui/feedback.js';
import { kpi, productOptions, table } from '../ui/widgets.js';
import { showProductDetail } from './products.js';

const ADJUSTMENT_TYPES = [['DAMAGE', 'Damage (reduce)'], ['BREAKAGE', 'Breakage (reduce)'], ['MOISTURE', 'Moisture (reduce)'],
  ['EXPIRED', 'Expired (reduce)'], ['MISSING', 'Missing (reduce)'], ['FOUND', 'Found (add)'], ['CORRECTION', 'Count correction (add)']];

const sorted = () => [...state.products].sort((a, b) => String(a.sku).localeCompare(String(b.sku), undefined, { numeric: true }));

function render() {
  const products = sorted();
  const status = (p) => (p.current_stock_base <= 0 ? 'bad' : p.current_stock_base <= p.reorder_level ? 'warn' : 'good');
  setHtml($('#page'), html`<div class="row wrap"><button class="button primary" data-action="inventory.purchase">+ Add Stock / GRN</button>
      <button class="button" data-action="inventory.adjust">Stock Adjustment</button></div><br>
    <div class="grid kpis">${kpi('Total Products', products.length)}${kpi('Low Stock', products.filter((p) => p.current_stock_base <= p.reorder_level).length)}
      ${kpi('Out of Stock', products.filter((p) => p.current_stock_base <= 0).length)}</div><br>
    <div class="card"><h3>Current Stock</h3>${table(['Product ID', 'Product', 'Unit', 'Available', 'Minimum', 'Default Price', ''], products.map((p) => html`<tr>
      <td>${p.sku}</td><td>${p.name}</td><td>${p.unit}</td><td><span class="tag ${status(p)}">${num(p.current_stock_base)}</span></td>
      <td>${num(p.reorder_level)}</td><td>${money(p.default_unit_price)}</td>
      <td><button class="button" data-action="inventory.view" data-id="${p.id}">View</button></td></tr>`), 'No products yet.')}</div>`);
}

registerActions({
  'inventory.view': (el) => showProductDetail(Number(el.dataset.id), render),
  'inventory.purchase': () => {
    if (!state.products.length) return toast('Add products first.');
    formModal('Add Stock / GRN', [
      { name: 'product_id', label: 'Product', type: 'select', options: productOptions(sorted()), required: true, full: true },
      { name: 'qty', label: 'Quantity', type: 'number', value: 1, required: true }, { name: 'cost_price', label: 'Cost per unit', type: 'number', value: 0 },
      { name: 'supplier_name', label: 'Supplier' }, { name: 'purchase_date', label: 'Purchase date', type: 'date', value: todayISO() },
      { name: 'invoice_number', label: 'Supplier invoice no.' }, { name: 'batch_number', label: 'Batch / lot' },
      { name: 'location', label: 'Location' }, { name: 'freight', label: 'Freight', type: 'number', value: 0 },
    ], 'inventory.savePurchase', { submitLabel: 'Add Stock' });
  },
  'inventory.savePurchase': async (form) => {
    const v = formValues(form);
    const result = await api.post('/api/purchases', {
      supplier_name: v.supplier_name, purchase_date: v.purchase_date, invoice_number: v.invoice_number, freight: Number(v.freight) || 0,
      items: [{ product_id: Number(v.product_id), qty: Number(v.qty), cost_price: Number(v.cost_price) || 0, batch_number: v.batch_number, location: v.location }],
    });
    await loadReferenceData();
    closeModal();
    render();
    toast(`Stock added (${result.purchase_number})`);
  },
  'inventory.adjust': () => {
    if (!state.products.length) return toast('Add products first.');
    formModal('Stock Adjustment', [
      { name: 'product_id', label: 'Product', type: 'select', options: productOptions(sorted()), required: true, full: true },
      { name: 'type', label: 'Type', type: 'select', value: 'DAMAGE', options: ADJUSTMENT_TYPES },
      { name: 'qty', label: 'Quantity', type: 'number', value: 1, required: true },
      { name: 'reason', label: 'Reason' }, { name: 'notes', label: 'Notes' },
    ], 'inventory.saveAdjustment');
  },
  'inventory.saveAdjustment': async (form) => {
    const v = formValues(form);
    await api.post('/api/inventory/adjust', { ...v, product_id: Number(v.product_id), qty: Number(v.qty) });
    await loadReferenceData();
    closeModal();
    render();
    toast('Stock adjusted');
  },
});

registerPage({ name: 'inventory', label: 'Inventory', permission: 'inventory.manage', render });
