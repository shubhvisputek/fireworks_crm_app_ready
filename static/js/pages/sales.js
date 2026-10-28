// Invoices: print, edit (re-issue), collect credit, return items, void.
import { api } from '../core/api.js';
import { $, $$, html, setHtml } from '../core/html.js';
import { registerActions, formValues } from '../core/actions.js';
import { dateTime, money, num, todayISO } from '../core/format.js';
import { can, findProduct, loadReferenceData, state } from '../core/state.js';
import { go, registerPage } from '../core/router.js';
import { closeModal, confirmDialog, field, openModal, toast } from '../ui/feedback.js';
import { brandTag, table } from '../ui/widgets.js';
import { loadInvoiceForEdit } from '../billing/bill.js';
import { WHATSAPP_ENABLED, billMessage, openWhatsapp } from '../ui/share.js';

let view = 'FINALIZED';

function history(x) {
  const lines = [];
  if (x.revised_from_number) {
    lines.push(html`Edited by <strong>${x.edited_by_name || '-'}</strong> on ${dateTime(x.edited_at)}`);
    lines.push(html`Revised from ${x.revised_from_number}${x.revision_reason ? html` — ${x.revision_reason}` : ''}`);
  }
  if (x.status === 'VOID') {
    lines.push(html`${x.revised_to_number ? html`Replaced by ${x.revised_to_number}` : 'Cancelled'} — ${x.voided_by_name || '-'} on ${dateTime(x.voided_at)}`);
  }
  return lines.length ? html`<div class="small muted">${lines.map((line, i) => html`${i ? html`<br>` : ''}${line}`)}</div>` : '';
}

// Only the actions this user is allowed to take are shown (the server enforces the same rules).
// The everyday actions stay visible; the rest sit in a "More" menu so the table fits the screen.
function actions(x) {
  const pdf = can('invoices.print') ? html`<button class="button" data-action="sales.pdf" data-id="${x.id}">PDF</button>` : '';
  const receipt = can('invoices.print') ? html`<button class="button" data-action="sales.receipt" data-id="${x.id}">Receipt (80 mm)</button>` : '';
  const share = WHATSAPP_ENABLED && x.customer_phone ? html`<button class="button" data-action="sales.whatsapp" data-id="${x.id}" title="Send bill on WhatsApp">WhatsApp</button>` : '';
  const finalized = x.status === 'FINALIZED';
  // A bill with returns can't be edited or deleted (the returned goods are already back in stock).
  const returned = x.returned_amount > 0;
  const fullyReturned = returned && x.returned_amount >= x.grand_total - 0.01;
  const more = [receipt, share,
    finalized && !fullyReturned && can('returns.create') ? html`<button class="button" data-action="sales.return" data-id="${x.id}">Return items</button>` : '',
    finalized && !returned && can('sales.void') ? html`<button class="button danger" data-action="sales.void" data-id="${x.id}" data-number="${x.invoice_number}">Delete</button>` : '',
  ].filter(Boolean);
  return html`${pdf}
    ${finalized && !returned && can('sales.edit') ? html`<button class="button" data-action="sales.edit" data-id="${x.id}">Edit</button>` : ''}
    ${finalized && x.outstanding > 0 && can('payments.collect') ? html`<button class="button" data-action="sales.collect" data-id="${x.id}">Collect</button>` : ''}
    ${more.length ? html`<details class="menu"><summary class="button" aria-label="More actions">More ▾</summary><div class="menu-items">${more}</div></details>` : ''}`;
}

async function render() {
  const invoices = await api.get('/api/invoices', { start: '1900-01-01', end: todayISO(), status: view });
  const rows = invoices.map((x) => html`<tr>
    <td><strong>${x.invoice_number}</strong>${history(x)}</td><td>${x.invoice_date}</td><td>${x.customer_name_snapshot}</td>
    <td>${x.billed_by_name || '-'}<div class="small muted">${dateTime(x.created_at)}</div></td>
    <td>${money(x.grand_total)}${x.returned_amount > 0 ? html`<div class="small"><span class="tag warn">Returned ${money(x.returned_amount)}</span></div>` : ''}</td>
    <td>${money(x.amount_received)}${x.outstanding > 0 ? html`<div class="small muted">Due ${money(x.outstanding)}</div>` : ''}</td>
    <td><div class="row">${actions(x)}</div></td></tr>`);
  setHtml($('#page'), html`<div class="card"><div class="between"><div><h3>Invoices</h3>
      <div class="small muted">${can('sales.view') ? 'All bills.' : 'Bills you made.'} Edit re-issues a bill with a new number and keeps the original as cancelled.</div></div>
      <select class="select" aria-label="Which bills" data-change="sales.view">
        <option value="FINALIZED" ${view === 'FINALIZED' ? html`selected` : ''}>Active bills</option>
        <option value="VOID" ${view === 'VOID' ? html`selected` : ''}>Cancelled / edited bills</option></select></div><br>
    ${table(['Invoice', 'Date', 'Customer', 'Billed by', 'Total', 'Received', 'Actions'], rows, 'No bills.')}</div>`);
}

registerActions({
  'sales.view': (el) => {
    view = el.value;
    render();
  },
  'sales.pdf': (el) => window.open(`/api/invoice-pdf/${el.dataset.id}`, '_blank'),
  'sales.receipt': (el) => window.open(`/api/invoice-receipt/${el.dataset.id}`, '_blank'),
  'sales.whatsapp': async (el) => {
    const { invoice, items } = await api.get(`/api/invoices/${el.dataset.id}`);
    openWhatsapp(invoice.customer_phone, billMessage(invoice, items));
  },
  'sales.edit': async (el) => {
    const detail = await api.get(`/api/invoices/${el.dataset.id}`);
    const missing = detail.items.filter((item) => !findProduct(item.product_id));
    if (missing.length) return toast(`Cannot edit: these products are no longer active: ${missing.map((m) => m.product_name_snapshot).join(', ')}`, 'error');
    loadInvoiceForEdit(detail, state.settings?.walk_in_name || 'Walk-in Customer');
    go('billing');
  },
  'sales.void': async (el) => {
    const number = el.dataset.number;
    const ok = await confirmDialog({ title: `Delete bill ${number}?`, danger: true, confirmLabel: 'Delete bill',
      message: 'The sale is cancelled and its items go back into stock. The bill stays in the history marked as cancelled, with who deleted it and when.' });
    if (!ok) return;
    await api.post(`/api/invoices/${el.dataset.id}/void`);
    await loadReferenceData();
    toast(`${number} voided and stock restored`);
    render();
  },
  'sales.collect': async (el) => {
    const { invoice } = await api.get(`/api/invoices/${el.dataset.id}`);
    openModal('Collect Payment', html`<p>${invoice.invoice_number} • Outstanding <strong>${money(invoice.outstanding)}</strong></p>
      <form data-submit="sales.saveCollection"><input type="hidden" name="invoice_id" value="${invoice.id}"><div class="formgrid">
        ${field({ name: 'mode', label: 'Mode', type: 'select', value: 'Cash', options: ['Cash', 'UPI', 'Card', 'Other'].map((m) => [m, m]) })}
        ${field({ name: 'amount', label: 'Amount', type: 'number', value: invoice.outstanding, required: true })}
        ${field({ name: 'reference', label: 'Reference', full: true })}</div><br>
        <button class="button primary">Save Payment</button></form>`);
  },
  'sales.saveCollection': async (form) => {
    const values = formValues(form);
    await api.post('/api/payments', { ...values, invoice_id: Number(values.invoice_id), amount: Number(values.amount) });
    closeModal();
    toast('Payment collected');
    render();
  },
  'sales.return': async (el) => {
    const { invoice, items } = await api.get(`/api/invoices/${el.dataset.id}`);
    openModal('Sales Return', html`<p>${invoice.invoice_number} • ${invoice.customer_name_snapshot}</p>
      <form data-submit="sales.saveReturn"><input type="hidden" name="invoice_id" value="${invoice.id}">
        ${invoice.outstanding > 0 ? html`<p class="notice warn small">The customer still owes ${money(invoice.outstanding)} on this bill:
          returned goods come off that first, and only the rest is paid back.</p>` : ''}
        ${items.map((item) => {
          const left = Math.max(0, item.qty_input - (item.returned_qty || 0));
          return html`<div class="between notice" style="margin-bottom:6px"><span>${item.product_name_snapshot}${brandTag(item.brand_snapshot)}
          <div class="small muted">Sold ${num(item.qty_input)} ${item.sell_unit}${item.returned_qty ? ` • already returned ${num(item.returned_qty)} • ${num(left)} left` : ''}</div></span>
          <input class="input return-qty" aria-label="Return quantity for ${item.brand_snapshot ? `${item.product_name_snapshot} (${item.brand_snapshot})` : item.product_name_snapshot}" data-item="${item.id}" style="width:100px"
            type="number" min="0" max="${left}" step="0.01" value="0" ${left ? '' : html`disabled`}></div>`;
        })}
        <label>Reason<textarea class="textarea" name="reason"></textarea></label><br>
        <button class="button primary">Process Return</button></form>`);
  },
  'sales.saveReturn': async (form) => {
    const items = $$('.return-qty', form).map((input) => ({ invoice_item_id: Number(input.dataset.item), qty: Number(input.value) })).filter((x) => x.qty > 0);
    const result = await api.post('/api/returns', { invoice_id: Number(form.elements.invoice_id.value), reason: form.elements.reason.value, items });
    closeModal();
    await loadReferenceData();
    const settled = result.credit_adjusted
      ? `${money(result.credit_adjusted)} taken off what the customer owes${result.paid_back ? `, pay back ${money(result.paid_back)}` : ''}`
      : `pay back ${money(result.paid_back)}`;
    toast(`Return ${result.return_number} posted (${money(result.refund)}): ${settled}`);
    render();
  },
});

registerPage({ name: 'sales', icon: 'sales', group: 'Sell', label: 'Sales', permission: ['sales.view', 'sales.view_own'], render });
