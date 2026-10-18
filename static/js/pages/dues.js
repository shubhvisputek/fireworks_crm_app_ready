// Who owes what: outstanding credit by customer, with collection and WhatsApp reminders.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money } from '../core/format.js';
import { can } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, toast } from '../ui/feedback.js';
import { kpi, table } from '../ui/widgets.js';
import { duesMessage, openWhatsapp } from '../ui/share.js';

let customers = [];

async function render() {
  const data = await api.get('/api/dues');
  customers = data.customers;
  const bills = customers.flatMap((c) => c.bills.map((bill) => ({ ...bill, customerIndex: customers.indexOf(c) })));
  setHtml($('#page'), html`<div class="grid kpis">${kpi('Total credit due', money(data.total_due))}${kpi('Customers owing', customers.length)}
      ${kpi('Unpaid bills', bills.length)}</div><br>
    <div class="card"><h3>By customer</h3>${table(['Customer', 'Phone', 'Owes', 'Oldest bill', ''], customers.map((c, index) => html`<tr>
      <td><strong>${c.name}</strong></td><td>${c.phone || ''}</td><td><strong>${money(c.total_due)}</strong></td><td>${c.oldest}</td>
      <td>${c.phone ? html`<button class="button" data-action="dues.remind" data-index="${index}">WhatsApp reminder</button>` : html`<span class="small muted">No mobile number</span>`}</td></tr>`),
      'No outstanding credit. 🎉')}</div><br>
    <div class="card"><h3>Unpaid bills</h3>${table(['Bill', 'Date', 'Customer', 'Total', 'Paid', 'Due', ''], bills.map((b) => html`<tr>
      <td>${b.invoice_number}</td><td>${b.invoice_date}</td><td>${b.customer_name_snapshot}</td><td>${money(b.grand_total)}</td>
      <td>${money(b.amount_received)}</td><td><strong>${money(b.outstanding)}</strong></td>
      <td>${can('payments.collect') ? html`<button class="button primary" data-action="dues.collect" data-id="${b.id}" data-due="${b.outstanding}" data-number="${b.invoice_number}">Collect</button>` : ''}</td></tr>`))}</div>`);
}

registerActions({
  'dues.remind': (el) => {
    const customer = customers[Number(el.dataset.index)];
    openWhatsapp(customer.phone, duesMessage(customer));
  },
  'dues.collect': (el) => formModal(`Collect for ${el.dataset.number}`, [
    { name: 'amount', label: `Amount (due ${money(el.dataset.due)})`, type: 'number', value: el.dataset.due, required: true },
    { name: 'mode', label: 'Mode', type: 'select', value: 'Cash', options: ['Cash', 'UPI', 'Card', 'Other'].map((m) => [m, m]) },
    { name: 'reference', label: 'Reference', full: true },
  ], 'dues.save', { hidden: { invoice_id: el.dataset.id }, submitLabel: 'Save Payment' }),
  'dues.save': async (form) => {
    const v = formValues(form);
    await api.post('/api/payments', { ...v, invoice_id: Number(v.invoice_id), amount: Number(v.amount) });
    closeModal();
    await render();
    toast('Payment collected');
  },
});

registerPage({ name: 'dues', icon: 'dues', group: 'Sell', label: 'Credit Dues', permission: 'dues.view', render });
