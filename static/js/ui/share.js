// WhatsApp share links and the "over storage limit — continue?" confirmation.
import { money } from '../core/format.js';
import { state } from '../core/state.js';
import { confirmDialog } from './feedback.js';

// WhatsApp sharing is switched off for now; set this to true to bring back the bill and dues-reminder buttons.
export const WHATSAPP_ENABLED = false;

// wa.me needs the international number; 10-digit Indian mobiles get the 91 prefix.
export function whatsappUrl(phone, message) {
  const digits = String(phone || '').replace(/\D/g, '');
  const number = digits.length === 10 ? `91${digits}` : digits;
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}

export function openWhatsapp(phone, message) {
  window.open(whatsappUrl(phone, message), '_blank', 'noopener');
}

const shopName = () => state.limits?.business_name || 'our shop';

export function billMessage(invoice, items = []) {
  const lines = items.map((item) => `• ${item.brand_snapshot ? `${item.product_name_snapshot} (${item.brand_snapshot})` : item.product_name_snapshot} × ${item.qty_input} = ${money(item.unit_price * item.qty_input)}`);
  return [`Thank you for shopping at ${shopName()}!`, `Bill ${invoice.invoice_number} (${invoice.invoice_date})`, ...lines,
    invoice.discount > 0 ? `Discount: ${money(invoice.discount)}` : '', `Total: ${money(invoice.grand_total)}`,
    invoice.outstanding > 0 ? `Balance due: ${money(invoice.outstanding)}` : ''].filter(Boolean).join('\n');
}

export function duesMessage(customer) {
  const bills = customer.bills.map((bill) => `• ${bill.invoice_number} (${bill.invoice_date}): ${money(bill.outstanding)}`);
  return [`Namaste ${customer.name},`, `This is a reminder from ${shopName()} about your pending balance of ${money(customer.total_due)}:`,
    ...bills, 'Please clear it at your convenience. Thank you!'].join('\n');
}

// Run a request; if the server refuses because of the licence storage limit, ask and retry with permission.
export async function withStorageConfirm(send) {
  try {
    return await send(false);
  } catch (error) {
    if (error.code !== 'STORAGE_LIMIT') throw error;
    const ok = await confirmDialog({ title: 'Over the licence storage limit', message: `${error.message} Record it anyway? This will be noted in the audit log.`,
      confirmLabel: 'Record anyway', danger: true });
    if (!ok) return null;
    return send(true);
  }
}
