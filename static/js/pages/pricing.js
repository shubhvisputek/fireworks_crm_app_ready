import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money } from '../core/format.js';
import { loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

const sorted = () => [...state.products].sort((a, b) => String(a.sku).localeCompare(String(b.sku), undefined, { numeric: true }));

function render() {
  setHtml($('#page'), html`<div class="row"><button class="button primary" data-action="pricing.change">Change Default Unit Price</button></div><br>
    <div class="card">${table(['Product ID', 'Product', 'Default Unit Price', ''], sorted().map((p) => html`<tr><td>${p.sku}</td><td>${p.name}</td>
      <td>${money(p.default_unit_price)}</td><td><button class="button" data-action="pricing.change" data-id="${p.id}">Change</button></td></tr>`), 'No products yet.')}</div>`);
}

registerActions({
  'pricing.change': (el) => {
    const selected = state.products.find((p) => p.id === Number(el.dataset.id)) || sorted()[0];
    if (!selected) return toast('Add products first.', 'error');
    formModal('Change Default Unit Price', [
      { name: 'product_id', label: 'Product', type: 'select', value: selected.id, options: sorted().map((p) => [p.id, `${p.sku} • ${p.name} (${money(p.default_unit_price)})`]), full: true },
      { name: 'unit_price', label: 'Default Unit Selling Price', type: 'number', value: selected.default_unit_price, required: true },
    ], 'pricing.save');
  },
  'pricing.save': async (form) => {
    const v = formValues(form);
    await api.post('/api/pricing', { product_id: Number(v.product_id), unit_price: Number(v.unit_price) });
    await loadReferenceData();
    closeModal();
    render();
    toast('Default unit price saved');
  },
});

registerPage({ name: 'pricing', icon: 'pricing', group: 'Stock', label: 'Pricing', title: 'Product Prices', permission: 'pricing.manage', render });
