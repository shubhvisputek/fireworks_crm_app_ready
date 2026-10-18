// Pure bill arithmetic, mirroring the server (crm/domain/money.py).
// The server recalculates everything; this only drives what the cashier sees.

export const toPaise = (value) => Math.round((Number(value) || 0) * 100);
export const fromPaise = (paise) => paise / 100;

// Split a bill discount across lines in proportion to their totals (largest remainder, whole paise).
export function allocateDiscount(amount, lineTotals) {
  const total = toPaise(amount);
  const weights = lineTotals.map((value) => Math.max(0, toPaise(value)));
  const weightTotal = weights.reduce((sum, w) => sum + w, 0);
  if (!total || !weightTotal) return weights.map(() => 0);
  const shares = weights.map((w) => Math.floor((total * w) / weightTotal));
  const remainder = total - shares.reduce((sum, s) => sum + s, 0);
  weights
    .map((w, index) => ({ index, rest: (total * w) % weightTotal }))
    .sort((a, b) => b.rest - a.rest || a.index - b.index)
    .slice(0, remainder)
    .forEach(({ index }) => (shares[index] += 1));
  return shares.map(fromPaise);
}

export function clampDiscount(discount, subtotal) {
  return fromPaise(Math.min(toPaise(subtotal), Math.max(0, toPaise(discount))));
}

// items: [{product_id, qty}], lookup: id -> product (with default_unit_price)
export function calculate(items, discount, lookup) {
  const lines = items.map((item) => {
    const product = lookup(item.product_id);
    const price = Number(product?.default_unit_price || 0);
    const qty = Number(item.qty || 0);
    return { item, product, price, qty, gross: fromPaise(toPaise(price * qty)) };
  });
  const subtotal = fromPaise(lines.reduce((sum, line) => sum + toPaise(line.gross), 0));
  const appliedDiscount = clampDiscount(discount, subtotal);
  const shares = allocateDiscount(appliedDiscount, lines.map((line) => line.gross));
  lines.forEach((line, index) => {
    line.discount = shares[index];
    line.net = fromPaise(toPaise(line.gross) - toPaise(line.discount));
  });
  return { lines, subtotal, discount: appliedDiscount, total: fromPaise(toPaise(subtotal) - toPaise(appliedDiscount)) };
}
