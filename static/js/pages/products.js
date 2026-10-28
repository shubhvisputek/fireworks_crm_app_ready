// Product master: list, add, product master import, product detail with stock actions.
import { api } from '../core/api.js';
import { $, $$, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { dateTime, money, num } from '../core/format.js';
import { can, findProduct, loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, confirmDialog, formModal, openModal, toast } from '../ui/feedback.js';
import { withStorageConfirm } from '../ui/share.js';
import { table } from '../ui/widgets.js';

const IMPORT_FIELDS = [
  ['sku', 'Product ID / Serial Number'], ['name', 'Product Name'], ['category', 'Category'], ['subcategory', 'Subcategory'],
  ['brand', 'Brand / Manufacturer'], ['unit', 'Unit'], ['unit_price', 'Default Unit Selling Price'], ['cost_price', 'Cost Price'],
  ['opening_stock', 'Opening Stock'], ['reorder_level', 'Minimum Stock'], ['status', 'Product Status'],
  ['barcode', 'Barcode'], ['explosive_kg', 'Explosive content per unit (kg)'],
];
const STATUS_OPTIONS = [['ACTIVE', 'Active'], ['INACTIVE', 'Inactive']];
let query = '';
let importFile = null;

const bySku = (a, b) => String(a.sku).localeCompare(String(b.sku), undefined, { numeric: true, sensitivity: 'base' }) || a.id - b.id;

function productRows() {
  const q = query.trim().toLowerCase();
  const rows = state.products
    .filter((p) => !q || [p.sku, p.name, p.category, p.brand].some((value) => String(value || '').toLowerCase().includes(q)))
    .sort(bySku);
  return rows.map((p) => html`<tr><td>${p.sku}${p.barcode ? html`<div class="small muted">${p.barcode}</div>` : ''}</td><td><strong>${p.name}</strong>${p.brand ? html`<div class="small muted">${p.brand}</div>` : ''}</td><td>${p.category || ''}</td><td>${p.unit}</td>
    <td>${money(p.default_unit_price)}</td><td>${num(p.current_stock_base)}</td><td>${p.status}</td>
    <td><button class="button" data-action="products.view" data-id="${p.id}">View</button></td></tr>`);
}

function renderTable() {
  setHtml($('#productTable'), table(['Product ID', 'Product', 'Category', 'Unit', 'Default Unit Price', 'Stock', 'Status', ''], productRows(), 'No products found.', { search: false }));
}

function render() {
  setHtml($('#page'), html`<div class="row wrap">
      <input class="input" id="productQuery" placeholder="Search products" aria-label="Search products" value="${query}" data-input="products.search">
      <button class="button primary" data-action="products.add">+ Product</button>
      <button class="button" data-action="products.import">Upload Product Master</button></div><br>
    <div class="card" id="productTable"></div>`);
  renderTable();
}

export async function showProductDetail(productId, onChange) {
  const d = await api.get(`/api/products/${productId}`);
  const p = d.product;
  openModal(p.brand ? `${p.name} — ${p.brand}` : p.name, html`<div class="grid two">
      <div class="notice">Product ID <strong>${p.sku}</strong></div><div class="notice">Available Stock <strong>${num(d.stock)} ${p.unit}</strong></div>
      <div class="notice">Default Unit Price <strong>${money(p.default_unit_price)}</strong></div>
      ${'cost_price' in p ? html`<div class="notice">Cost Price <strong>${money(p.cost_price)}</strong></div>` : ''}
      <div class="notice">Barcode <strong>${p.barcode || '—'}</strong></div><div class="notice">Explosive content <strong>${num(p.explosive_kg)} kg/unit</strong></div>
      <div class="notice">Status <strong>${p.status}</strong></div><div class="notice">Last sale <strong>${d.last_sale || 'Never'}</strong></div></div><br>
    <div class="row"><button class="button primary" data-action="products.edit" data-id="${p.id}">Edit</button>
      ${can('inventory.manage') ? html`<button class="button" data-action="products.removeStock" data-id="${p.id}">Remove Stock</button>` : ''}
      <button class="button" data-action="products.ledger" data-id="${p.id}">Stock Ledger</button>
      <button class="button danger" data-action="products.remove" data-id="${p.id}">Remove Product</button></div>`);
  editing = p;
  detailChanged = onChange;
}
let detailChanged = render;
let editing = null;

async function refresh() {
  await loadReferenceData();
  closeModal();
  (detailChanged || render)();
}

registerActions({
  'products.search': (el) => {
    query = el.value;
    renderTable();
  },
  'products.add': () => formModal('New Product', [
    { name: 'sku', label: 'Product ID / Serial Number', required: true }, { name: 'name', label: 'Product Name', required: true },
    { name: 'category', label: 'Category' }, { name: 'subcategory', label: 'Subcategory' }, { name: 'brand', label: 'Brand / Manufacturer' },
    { name: 'unit', label: 'Unit', value: 'Box' }, { name: 'unit_price', label: 'Default Unit Selling Price', type: 'number', value: 0, required: true },
    ...(can('profit.view') ? [{ name: 'cost_price', label: 'Cost Price (for profit reports)', type: 'number', value: 0 }] : []),
    { name: 'opening_stock', label: 'Opening Stock', type: 'number', value: 0 }, { name: 'reorder_level', label: 'Minimum Stock', type: 'number', value: 0 },
    { name: 'barcode', label: 'Barcode (scan or type)' }, { name: 'explosive_kg', label: 'Explosive content per unit (kg)', type: 'number', value: 0, step: '0.001' },
    { name: 'status', label: 'Product Status', type: 'select', value: 'ACTIVE', options: STATUS_OPTIONS },
  ], 'products.create'),
  'products.create': async (form) => {
    const values = formValues(form);
    if (!(await withStorageConfirm((allow) => api.post('/api/products', { ...values, allow_over_limit: allow })))) return;
    detailChanged = render;
    await refresh();
    toast('Product added');
  },
  'products.view': (el) => showProductDetail(Number(el.dataset.id), render),
  'products.edit': () => {
    const p = editing;
    formModal(`Edit ${p.name}`, [
      { name: 'name', label: 'Product Name', value: p.name, required: true }, { name: 'category', label: 'Category', value: p.category || '' },
      { name: 'subcategory', label: 'Subcategory', value: p.subcategory || '' }, { name: 'brand', label: 'Brand / Manufacturer', value: p.brand || '' },
      { name: 'unit', label: 'Unit', value: p.unit }, { name: 'reorder_level', label: 'Minimum Stock', type: 'number', value: p.reorder_level },
      { name: 'barcode', label: 'Barcode', value: p.barcode || '' },
      { name: 'explosive_kg', label: 'Explosive content per unit (kg)', type: 'number', value: p.explosive_kg || 0, step: '0.001' },
      ...('cost_price' in p ? [{ name: 'cost_price', label: 'Cost Price', type: 'number', value: p.cost_price }] : []),
      { name: 'status', label: 'Product Status', type: 'select', value: p.status, options: STATUS_OPTIONS },
    ], 'products.saveEdit', { hidden: { product_id: p.id }, note: 'Selling price is changed on the Pricing page.' });
  },
  'products.saveEdit': async (form) => {
    const { product_id: id, ...values } = formValues(form);
    await api.post(`/api/products/${id}`, values);
    await refresh();
    toast('Product updated');
  },
  'products.removeStock': (el) => {
    const product = findProduct(el.dataset.id);
    formModal('Remove Stock', [
      { name: 'qty', label: `Quantity (${product?.unit || 'units'})`, type: 'number', value: 1, required: true },
      { name: 'reason', label: 'Reason', value: 'Damage' }, { name: 'notes', label: 'Notes', full: true },
    ], 'products.saveRemoveStock', { hidden: { product_id: el.dataset.id }, submitLabel: 'Remove Stock' });
  },
  'products.saveRemoveStock': async (form) => {
    const values = formValues(form);
    await api.post('/api/inventory/remove', { ...values, product_id: Number(values.product_id), qty: Number(values.qty) });
    await refresh();
    toast('Stock removed');
  },
  'products.ledger': async (el) => {
    const rows = await api.get('/api/inventory/ledger', { product_id: el.dataset.id });
    openModal('Stock Ledger', table(['Date', 'Type', 'Qty', 'Reason'], rows.map((m) =>
      html`<tr><td>${dateTime(m.created_at)}</td><td>${m.movement_type}</td><td>${num(m.qty_base)}</td><td>${m.reason || ''}</td></tr>`)));
  },
  'products.remove': async (el) => {
    const ok = await confirmDialog({ title: 'Remove this product?', danger: true, confirmLabel: 'Remove product',
      message: 'It disappears from billing and the product list. If it was ever used in a bill or purchase, it is archived as inactive instead, so old bills stay correct.' });
    if (!ok) return;
    const result = await api.post(`/api/products/${el.dataset.id}/remove`);
    await refresh();
    toast(result.action === 'product removed' ? 'Product removed' : 'Product archived as inactive');
  },
  'products.import': () => {
    importFile = null;
    openModal('Product Master Upload', html`<p class="small muted">Upload the one-time product master (Excel or CSV). Existing Product IDs are rejected as duplicates.</p>
      <form data-submit="products.preview"><input class="input" type="file" name="file" accept=".xlsx,.csv" required><br><br>
      <button class="button primary">Validate & Preview</button></form>`);
  },
  'products.preview': async (form) => {
    importFile = form.elements.file.files[0];
    if (!importFile) return toast('Choose the Product Master file', 'error');
    const data = new FormData();
    data.append('file', importFile);
    data.append('mode', 'preview');
    const preview = await api.upload('/api/import/products', data);
    openModal('Preview & Mapping', html`<div class="notice ${preview.errors.length ? 'warn' : ''}">Total rows: ${preview.count}. Preview errors: ${preview.errors.length}</div>
      ${preview.errors.length ? table(['Row', 'Problem'], preview.errors.slice(0, 20).map((e) => html`<tr><td>${e.row}</td><td>${e.error}</td></tr>`)) : ''}<br>
      <form data-submit="products.confirmImport"><div class="formgrid">${IMPORT_FIELDS.map(([key, label]) => html`<label>${label}
        <select class="select import-map" data-key="${key}"><option value="">Not mapped</option>${preview.headers.map((h) =>
          html`<option value="${h}" ${preview.mapping[key] === h ? html`selected` : ''}>${h}</option>`)}</select></label>`)}</div><br>
      <button class="button primary">Confirm Import</button></form>`);
  },
  'products.confirmImport': async (form) => {
    const mapping = Object.fromEntries($$('.import-map', form).map((select) => [select.dataset.key, select.value || null]));
    if (!mapping.sku || !mapping.name || !mapping.unit_price) return toast('Product ID, Product Name, and Unit Price are mandatory', 'error');
    const upload = (allow) => {
      const data = new FormData();
      data.append('file', importFile);
      data.append('mapping', JSON.stringify(mapping));
      if (allow) data.append('allow_over_limit', '1');
      return api.upload('/api/import/products', data);
    };
    try {
      const result = await withStorageConfirm(upload);
      if (!result) return;
      detailChanged = render;
      await refresh();
      toast(`Imported ${result.imported} of ${result.total_rows} products`);
    } catch (error) {
      if (!error.validation_errors) throw error;
      openModal('Product Master Import Errors', html`<div class="notice bad">Total rows: ${error.total_rows} • Failed: ${error.failed_rows} • Duplicates: ${error.duplicate_rows}.
        Nothing was imported; fix these rows and upload again.</div><br>
        ${table(['Row', 'Error'], error.validation_errors.map((e) => html`<tr><td>${e.row}</td><td>${e.error}</td></tr>`))}`);
    }
  },
});

registerPage({ name: 'products', icon: 'products', group: 'Stock', label: 'Products', permission: 'catalog.manage', render });
