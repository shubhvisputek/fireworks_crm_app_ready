// The bill being built at the counter (new, resumed from hold, or an edit of a finalized bill).
import { findProduct } from '../core/state.js';
import { calculate } from './cart.js';

export const bill = {
  items: [], // [{product_id, qty}]
  discount: 0,
  customerName: '',
  customerPhone: '',
  editing: null, // {id, number, customerId, customerName, customerPhone, payments, notes} when re-issuing a bill
  heldRef: null, // the held bill this one was resumed from
};

export function resetBill() {
  Object.assign(bill, { items: [], discount: 0, customerName: '', customerPhone: '', editing: null, heldRef: null });
}

export const billTotals = () => calculate(bill.items, bill.discount, findProduct);

export function addProduct(productId) {
  const index = bill.items.findIndex((item) => item.product_id === productId);
  const item = index >= 0 ? bill.items.splice(index, 1)[0] : { product_id: productId, qty: 0 };
  item.qty = Number(item.qty) + 1;
  bill.items.unshift(item); // newest at the top, next to the search box
}

// The held bill stays saved while it is on the counter, and is removed when this bill is finished or held again,
// so closing the browser or signing out never loses it.
export function loadHeldBill(held) {
  resetBill();
  bill.heldRef = held.bill?.ref || null;
  bill.items = (held.items || []).map((item) => ({ product_id: Number(item.product_id), qty: Number(item.qty) }));
  bill.discount = Number(held.discount || 0);
  bill.customerName = held.bill?.customer_name || '';
  bill.customerPhone = held.customer_phone || '';
}

export function loadInvoiceForEdit({ invoice, items, payments }, walkInName) {
  resetBill();
  const name = invoice.customer_id && invoice.customer_name_snapshot !== walkInName ? invoice.customer_name_snapshot : '';
  bill.items = items.map((item) => ({ product_id: item.product_id, qty: item.qty_input }));
  bill.discount = Number(invoice.discount || 0);
  bill.customerName = name;
  bill.customerPhone = invoice.customer_phone || '';
  bill.editing = {
    id: invoice.id, number: invoice.invoice_number, customerId: invoice.customer_id, customerName: name,
    customerPhone: bill.customerPhone, payments: payments.map((p) => ({ mode: p.mode, amount: p.amount })), notes: invoice.notes || '',
  };
}

// Payload for /api/sales and /api/invoices/:id/edit.
export function billPayload(payments, notes) {
  const name = bill.customerName.trim();
  const phone = bill.customerPhone.trim();
  const sameCustomer = bill.editing && name === bill.editing.customerName && phone === bill.editing.customerPhone;
  return {
    customer_id: sameCustomer ? bill.editing.customerId : null,
    customer_name: name,
    customer_phone: phone,
    items: bill.items.map(({ product_id, qty }) => ({ product_id, qty })),
    discount: billTotals().discount,
    payments,
    notes,
    held_ref: bill.heldRef || undefined,
  };
}
