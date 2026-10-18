// Counter billing: search, cart, discount, hold/resume, payment, and editing a finalized bill.
import { api } from '../core/api.js';
import { $, $$, html, setHtml } from '../core/html.js';
import { registerActions } from '../core/actions.js';
import { money, num, dateTime } from '../core/format.js';
import { can, loadReferenceData, state } from '../core/state.js';
import { go, registerPage } from '../core/router.js';
import { closeModal, openModal, toast } from '../ui/feedback.js';
import { addProduct, bill, billPayload, billTotals, loadHeldBill, resetBill } from '../billing/bill.js';

const PAYMENT_MODES = ['Cash', 'UPI', 'Card', 'Credit', 'Other'];
const DISCOUNT_PRESETS = [5, 10, 15];

function view() {
  const editing = bill.editing;
  return html`
    <div class="row wrap billing-actions" style="margin-bottom:12px">
      <button class="button primary" data-action="billing.new">New Bill</button>
      ${editing ? '' : html`<button class="button" id="holdBill" data-action="billing.hold">Hold Bill</button>
        <button class="button" data-action="billing.showHeld">Held Bills</button>`}
    </div>
    ${editing ? html`<div class="notice warn" style="margin-bottom:12px">Editing bill <strong>${editing.number}</strong>.
      Add, remove or change quantities, then save. The original bill is kept as cancelled.
      <button class="button" data-action="billing.cancelEdit">Cancel edit</button></div>` : ''}
    <div class="bill-layout"><div>
      <div class="card"><div class="formgrid">
        <label>Customer name (optional)<input class="input" id="billName" value="${bill.customerName}" data-input="billing.name" autocomplete="off"></label>
        <label>Mobile (optional)<input class="input" id="billPhone" type="tel" inputmode="numeric" maxlength="10" value="${bill.customerPhone}" data-input="billing.phone" autocomplete="off"></label>
        <label>Product search<div class="searchbox"><input class="input" id="productSearch" placeholder="Name / Product ID — Enter adds the first match"
          data-input="billing.search" data-keydown="billing.searchKey" autocomplete="off"><div id="searchResults" class="search-results hide"></div></div></label>
      </div></div><br>
      <div class="card"><h3>Items</h3><div class="small muted" style="margin-bottom:8px">Quantity × Selling Unit Price</div><div id="cart"></div></div>
    </div><div>
      <div class="card bill-summary-card"><h3>Bill total</h3><div id="summary"></div><br>
        <button class="button primary bill-payment-button" style="width:100%" data-action="billing.pay">${editing ? 'Save edited bill' : 'Payment & Complete'}</button></div>
    </div></div>`;
}

function renderCart() {
  const totals = billTotals();
  const cart = $('#cart');
  if (!cart) return;
  setHtml(cart, totals.lines.length ? html`<div class="cart-grid">
      <div class="cart-header"><span>Product</span><span>Qty</span><span>Unit</span><span>Price</span><span>Amount</span><span></span></div>
      ${totals.lines.map((line, index) => html`<div class="cart-row">
        <div class="cart-product"><strong>${line.product?.name || 'Unknown product'}</strong>
          <div class="small muted">${line.product?.sku} • Available ${num(line.product?.current_stock_base)} • Discount ${money(line.discount)}</div></div>
        <div class="cart-field cart-quantity"><span class="cart-field-label">Qty</span>
          <input class="input" aria-label="Quantity" type="number" min="0.01" step="0.01" value="${line.qty}" data-change="billing.qty" data-index="${index}"></div>
        <div class="cart-field cart-unit"><span class="cart-field-label">Unit</span><span class="cart-field-value">${line.product?.unit}</span></div>
        <div class="cart-field cart-price"><span class="cart-field-label">Price</span><span class="right">${money(line.price)}</span></div>
        <div class="cart-line-total"><span class="cart-field-label">Amount</span><strong class="right">${money(line.net)}</strong></div>
        <button class="button cart-remove" aria-label="Remove ${line.product?.name}" data-action="billing.remove" data-index="${index}">×</button>
      </div>`)}</div>` : html`<div class="muted small">No products selected.</div>`);
  setHtml($('#summary'), html`
    <div class="between"><span>Total before discount</span><strong>${money(totals.subtotal)}</strong></div>
    <div class="row wrap" style="margin:10px 0">${DISCOUNT_PRESETS.map((pct) => html`<button class="button" data-action="billing.discountPct" data-pct="${pct}">${pct}%</button>`)}
      <button class="button" data-action="billing.discountPct" data-pct="0">Clear</button></div>
    <label>Discount amount<input class="input" aria-label="Discount amount" type="number" min="0" max="${totals.subtotal}" step="0.01" value="${totals.discount}" data-change="billing.discount"></label>
    <div class="between"><span>Discount</span><strong>${money(totals.discount)}</strong></div><hr>
    <div class="between"><span>Total after discount</span><strong style="font-size:24px">${money(totals.total)}</strong></div>`);
  const hold = $('#holdBill');
  if (hold) hold.disabled = !bill.items.length;
}

// Re-render after the current event finishes, so a focused input is not replaced mid-event.
const scheduleCartRender = () => setTimeout(renderCart, 0);

// Best matches first, so Enter (or a barcode scanner) picks the exact product ID.
function searchMatches(query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const rank = (p) => {
    const sku = String(p.sku).toLowerCase();
    const name = String(p.name).toLowerCase();
    if (sku === q || String(p.barcode || '').toLowerCase() === q) return 0;
    if (sku.startsWith(q)) return 1;
    if (name.startsWith(q)) return 2;
    return sku.includes(q) || name.includes(q) ? 3 : -1;
  };
  return state.products
    .map((p) => ({ p, r: rank(p) }))
    .filter(({ r }) => r >= 0)
    .sort((a, b) => a.r - b.r || String(a.p.sku).localeCompare(String(b.p.sku), undefined, { numeric: true, sensitivity: 'base' }))
    .slice(0, 12)
    .map(({ p }) => p);
}

function hideSearch() {
  $('#searchResults')?.classList.add('hide');
}

function add(productId) {
  addProduct(productId);
  hideSearch();
  $('#productSearch').value = '';
  renderCart();
  const qty = $('#cart input[aria-label="Quantity"]');
  qty?.focus();
  qty?.select();
}

function paymentRow(amount = 0, mode = 'Cash') {
  return html`<div class="formgrid pay-row" style="margin-bottom:8px">
    <label>Mode<select class="select pay-mode">${PAYMENT_MODES.map((m) => html`<option ${m === mode ? html`selected` : ''}>${m}</option>`)}</select></label>
    <label>Amount<input class="input pay-amount" type="number" min="0" step="0.01" value="${amount}"></label></div>`;
}

// Discounts above the shop limit need a manager's username and password, unless this user may approve them.
function needsApproval(totals) {
  if (!totals.discount || !totals.subtotal || can('discount.approve')) return false;
  return (totals.discount / totals.subtotal) * 100 > Number(state.limits.max_discount_pct ?? 100) + 1e-9;
}

const approvalFields = () => html`<div class="notice warn" id="approvalBox">Discount above ${state.limits.max_discount_pct}% needs a manager's approval.
  <div class="formgrid" style="margin-top:8px"><label>Approver username<input class="input" name="approver" autocomplete="off" required></label>
  <label>Approver password<input class="input" name="approver_password" type="password" autocomplete="off" required></label></div></div><br>`;

function openPayment() {
  if (!bill.items.length) return toast('Add products first');
  const totals = billTotals();
  const previous = (bill.editing?.payments || []).filter((p) => p.amount > 0);
  const previousTotal = previous.reduce((sum, p) => sum + p.amount, 0);
  const rows = bill.editing && previous.length && Math.abs(previousTotal - totals.total) <= 0.01 ? previous.map((p) => paymentRow(p.amount, p.mode)) : [paymentRow(totals.total, 'Cash')];
  openModal(bill.editing ? `Edit ${bill.editing.number}` : 'Complete payment', html`<form data-submit="billing.finalize">
    <div class="payment-totals"><div class="between"><span>Subtotal</span><strong>${money(totals.subtotal)}</strong></div>
      <div class="between"><span>Discount</span><strong>−${money(totals.discount)}</strong></div>
      <div class="between payment-due"><span>Amount due</span><strong>${money(totals.total)}</strong></div></div>
    <div id="payRows">${rows}</div>
    <button type="button" class="button" data-action="billing.addPayment">+ Payment</button><br><br>
    <label>Notes<textarea class="textarea" name="notes">${bill.editing?.notes || ''}</textarea></label><br>
    ${bill.editing ? html`<label>Reason for edit (required)<input class="input" name="reason" required minlength="3" placeholder="e.g. customer added 2 boxes"></label><br>` : ''}
    <div id="approvalSlot">${needsApproval(totals) ? approvalFields() : ''}</div>
    <div class="row" style="justify-content:flex-end"><button type="button" class="button" data-action="modal.close">Cancel</button>
      <button class="button primary">${bill.editing ? 'Save edited bill' : 'Finalize Invoice'}</button></div></form>`);
}

async function finalize(form) {
  const phone = bill.customerPhone.trim();
  if (phone && !/^\d{10}$/.test(phone)) return toast('Mobile number must be exactly 10 digits.');
  const totals = billTotals();
  const payments = $$('.pay-row', form)
    .map((row) => ({ mode: $('.pay-mode', row).value, amount: Number($('.pay-amount', row).value) }))
    .filter((p) => p.amount > 0);
  const paid = payments.reduce((sum, p) => sum + p.amount, 0);
  if (Math.abs(paid - totals.total) > 0.01) return toast('Payment total must match the amount after discount.');
  const editing = bill.editing;
  const reason = form.elements.reason?.value.trim();
  if (editing && (!reason || reason.length < 3)) return toast('Enter a reason for editing this bill.');
  const pdfWindow = window.open('about:blank', '_blank'); // opened now so popup blockers allow it
  try {
    const payload = billPayload(payments, form.elements.notes.value);
    if (form.elements.approver) payload.approval = { username: form.elements.approver.value, password: form.elements.approver_password.value };
    const result = editing ? await api.post(`/api/invoices/${editing.id}/edit`, { ...payload, reason }) : await api.post('/api/sales', payload);
    const printPath = state.limits.receipt_format === '80mm' ? 'invoice-receipt' : 'invoice-pdf';
    if (pdfWindow) pdfWindow.location = `/api/${printPath}/${result.invoice_id}`;
    closeModal();
    resetBill();
    await loadReferenceData();
    toast(editing ? `${result.previous_invoice_number} edited — new bill ${result.invoice_number}` : `Bill ${result.invoice_number} completed`);
    go(editing ? 'sales' : 'billing');
  } catch (error) {
    pdfWindow?.close();
    if (error.code === 'DISCOUNT_APPROVAL_REQUIRED' && !form.elements.approver) {
      setHtml($('#approvalSlot'), approvalFields());
      form.elements.approver.focus();
    }
    throw error;
  }
}

async function showHeld() {
  const bills = await api.get('/api/held-bills');
  openModal('Held Bills', bills.length ? html`${bills.map((held) => html`<div class="between notice" style="margin-bottom:8px">
      <div><strong>${held.ref}</strong><div class="small muted">${held.customer_name || 'Walk-in Customer'} • ${held.items.length} items •
        ${money(held.discount)} discount • ${dateTime(held.created_at)}</div></div>
      <div class="row"><button class="button primary" data-action="billing.resume" data-id="${held.id}">Resume</button>
        ${can('held_bills.delete') ? html`<button class="button" data-action="billing.deleteHeld" data-id="${held.id}">Delete</button>` : ''}</div></div>`)}`
    : html`<div class="muted small">No held bills.</div>`);
}

registerActions({
  'billing.newFromAnywhere': () => {
    resetBill();
    go('billing');
  },
  'billing.new': () => {
    resetBill();
    renderBilling();
  },
  'billing.cancelEdit': () => {
    resetBill();
    toast('Edit cancelled');
    go('sales');
  },
  'billing.name': (el) => (bill.customerName = el.value),
  'billing.phone': (el) => {
    el.value = el.value.replace(/\D/g, '').slice(0, 10);
    bill.customerPhone = el.value;
  },
  'billing.search': (el) => {
    const box = $('#searchResults');
    const matches = searchMatches(el.value);
    if (!el.value.trim()) return hideSearch();
    setHtml(box, matches.length ? matches.map((p) => html`<div class="product-result" data-action="billing.add" data-id="${p.id}">
        <div><strong>${p.name}</strong><div class="small muted">${p.sku} • Stock ${num(p.current_stock_base)}</div></div>
        <div class="right">${money(p.default_unit_price)}<div class="small muted">per ${p.unit}</div></div></div>`) : html`<div class="small muted">No product found</div>`);
    box.classList.remove('hide');
  },
  'billing.searchKey': (el, event) => {
    if (event.key === 'Escape') hideSearch();
    if (event.key === 'Enter') {
      event.preventDefault();
      const [first] = searchMatches(el.value);
      if (first) add(first.id);
    }
  },
  'billing.add': (el) => add(Number(el.dataset.id)),
  'billing.qty': (el) => {
    const qty = Number(el.value);
    bill.items[Number(el.dataset.index)].qty = qty > 0 ? qty : 1;
    scheduleCartRender();
  },
  'billing.remove': (el) => {
    bill.items.splice(Number(el.dataset.index), 1);
    renderCart();
  },
  'billing.discountPct': (el) => {
    bill.discount = Math.round(billTotals().subtotal * Number(el.dataset.pct)) / 100;
    renderCart();
  },
  'billing.discount': (el) => {
    bill.discount = Number(el.value) || 0;
    scheduleCartRender();
  },
  'billing.hold': async () => {
    if (!bill.items.length) return toast('Add products before holding a bill.');
    await api.post('/api/held-bills', { customer_name: bill.customerName.trim() || 'Walk-in Customer', customer_phone: bill.customerPhone.trim(),
      items: bill.items, discount: billTotals().discount });
    resetBill();
    renderBilling();
    toast('Bill held. Start another bill or resume it from Held Bills.');
  },
  'billing.showHeld': showHeld,
  'billing.resume': async (el) => {
    loadHeldBill(await api.post(`/api/held-bills/resume/${el.dataset.id}`));
    closeModal();
    renderBilling();
    toast('Held bill resumed');
  },
  'billing.deleteHeld': async (el) => {
    await api.post(`/api/held-bills/delete/${el.dataset.id}`);
    await showHeld();
  },
  'billing.pay': openPayment,
  'billing.addPayment': () => $('#payRows').insertAdjacentHTML('beforeend', String(paymentRow())),
  'billing.finalize': finalize,
});

export function renderBilling() {
  setHtml($('#page'), view());
  renderCart();
}

document.addEventListener('click', (event) => {
  if (!event.target.closest('.searchbox')) hideSearch();
});

registerPage({ name: 'billing', label: 'Billing', permission: 'billing.create', render: renderBilling });
