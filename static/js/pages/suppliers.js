// Suppliers: what is owed to each, their purchase history, and payments made to them.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money, todayISO } from '../core/format.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, openModal, toast } from '../ui/feedback.js';
import { kpi, table } from '../ui/widgets.js';

const MODES = ['Cash', 'UPI', 'Bank transfer', 'Cheque', 'Other'].map((m) => [m, m]);

async function render() {
  const suppliers = await api.get('/api/suppliers');
  const owed = suppliers.reduce((sum, s) => sum + Math.max(0, s.balance), 0);
  setHtml($('#page'), html`<div class="grid kpis">${kpi('Suppliers', suppliers.length)}${kpi('Total owed to suppliers', money(owed))}</div><br>
    <div class="row"><button class="button primary" data-action="suppliers.add">+ Supplier</button></div><br>
    <div class="card">${table(['Supplier', 'Phone', 'Purchased', 'Paid', 'Balance owed', ''], suppliers.map((s) => html`<tr>
      <td><strong>${s.name}</strong></td><td>${s.phone || ''}</td><td>${money(s.purchased)}</td><td>${money(s.paid)}</td>
      <td><span class="tag ${s.balance > 0 ? 'warn' : 'good'}">${money(s.balance)}</span></td>
      <td><div class="row"><button class="button" data-action="suppliers.ledger" data-id="${s.id}">Ledger</button>
        <button class="button" data-action="suppliers.pay" data-id="${s.id}" data-name="${s.name}">Record payment</button></div></td></tr>`),
      'No suppliers yet. They are also added automatically when you record a purchase with a new supplier name.')}</div>`);
}

registerActions({
  'suppliers.add': () => formModal('New Supplier', [
    { name: 'name', label: 'Name', required: true }, { name: 'phone', label: 'Phone', type: 'tel' }, { name: 'gstin', label: 'GSTIN' },
    { name: 'address', label: 'Address' }, { name: 'notes', label: 'Notes', type: 'textarea', full: true },
  ], 'suppliers.save'),
  'suppliers.save': async (form) => {
    await api.post('/api/suppliers', formValues(form));
    closeModal();
    await render();
    toast('Supplier added');
  },
  'suppliers.pay': (el) => formModal(`Payment to ${el.dataset.name}`, [
    { name: 'amount', label: 'Amount', type: 'number', value: '', min: 0.01, required: true },
    { name: 'mode', label: 'Mode', type: 'select', value: 'Cash', options: MODES },
    { name: 'payment_date', label: 'Date', type: 'date', value: todayISO() }, { name: 'reference', label: 'Reference' },
    { name: 'notes', label: 'Notes', full: true },
  ], 'suppliers.savePayment', { hidden: { supplier_id: el.dataset.id } }),
  'suppliers.savePayment': async (form) => {
    const { supplier_id: id, ...values } = formValues(form);
    const result = await api.post(`/api/suppliers/${id}/payments`, values);
    closeModal();
    await render();
    toast(`Payment saved. Balance now ${money(result.balance)}`);
  },
  'suppliers.ledger': async (el) => {
    const { supplier, purchases, payments } = await api.get(`/api/suppliers/${el.dataset.id}`);
    openModal(`${supplier.name} — ledger`, html`<div class="notice">Balance owed: <strong>${money(supplier.balance)}</strong></div><br>
      <h3>Purchases</h3>${table(['Date', 'Purchase no.', 'Supplier invoice', 'Total'], purchases.map((p) =>
        html`<tr><td>${p.purchase_date}</td><td>${p.purchase_number}</td><td>${p.invoice_number || ''}</td><td>${money(p.total)}</td></tr>`), 'No purchases.')}<br>
      <h3>Payments</h3>${table(['Date', 'Mode', 'Reference', 'Amount'], payments.map((p) =>
        html`<tr><td>${p.payment_date}</td><td>${p.mode}</td><td>${p.reference || ''}</td><td>${money(p.amount)}</td></tr>`), 'No payments.')}`);
  },
});

registerPage({ name: 'suppliers', label: 'Suppliers', permission: 'suppliers.manage', render });
