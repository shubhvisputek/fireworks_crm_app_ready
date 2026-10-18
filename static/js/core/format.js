// Display formatting (Indian locale, shop timezone).

const TIMEZONE = 'Asia/Kolkata';
const currency = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const money = (value) => currency.format(Number(value || 0));
export const num = (value) => Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100;

export function todayISO(date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE }).format(date);
}

export function yearStartISO() {
  return `${todayISO().slice(0, 4)}-01-01`;
}

export function dateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('en-IN', { timeZone: TIMEZONE, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
