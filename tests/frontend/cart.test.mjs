// Run with: node --test tests/frontend/
import assert from 'node:assert/strict';
import test from 'node:test';
import { allocateDiscount, calculate, clampDiscount } from '../../static/js/billing/cart.js';
import { escapeHtml, html, raw } from '../../static/js/core/html.js';

const products = { 1: { default_unit_price: 33.33 }, 2: { default_unit_price: 10 } };
const lookup = (id) => products[id];

test('discount shares add up to the exact discount', () => {
  const shares = allocateDiscount(10, [33.33, 33.33, 33.34]);
  assert.equal(Math.round(shares.reduce((a, b) => a + b, 0) * 100), 1000);
  assert.deepEqual(allocateDiscount(0, [10, 20]), [0, 0]);
});

test('discount is clamped to the subtotal and never negative', () => {
  assert.equal(clampDiscount(500, 120), 120);
  assert.equal(clampDiscount(-5, 120), 0);
});

test('bill totals match the server rules', () => {
  const totals = calculate([{ product_id: 1, qty: 3 }, { product_id: 2, qty: 2 }], 10, lookup);
  assert.equal(totals.subtotal, 119.99);
  assert.equal(totals.discount, 10);
  assert.equal(totals.total, 109.99);
  assert.equal(Math.round(totals.lines.reduce((s, l) => s + l.net, 0) * 100), 10999);
});

test('html template escapes interpolated values', () => {
  const name = `<img src=x onerror="alert(1)">'`;
  assert.equal(String(html`<b>${name}</b>`), `<b>${escapeHtml(name)}</b>`);
  assert.equal(String(html`<i>${html`<u>ok</u>`}</i>`), '<i><u>ok</u></i>');
  assert.equal(String(html`${[1, '<', raw('<br>')]}`), '1&lt;<br>');
  assert.equal(String(html`${null}${undefined}${false}`), '');
});
