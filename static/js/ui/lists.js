// Every table (see widgets.table): filter rows by the search box, show them 50 at a time, and export them to Excel.
// Works on the rendered rows, so every page gets it without extra code.
import { api } from '../core/api.js';
import { registerActions } from '../core/actions.js';
import { toast } from './feedback.js';

function rowsOf(list) {
  return [...list.querySelectorAll('tbody > tr')].filter((row) => !row.classList.contains('empty-row'));
}

function matching(list) {
  const query = (list.querySelector('[data-input="list.filter"]')?.value || '').trim().toLowerCase();
  const rows = rowsOf(list);
  return query ? rows.filter((row) => row.textContent.toLowerCase().includes(query)) : rows;
}

// A cell's words as the person reads them: its separate lines joined with " · ", buttons and menus left out.
// A plain amount or count becomes a number, so Excel can add it up.
const SKIP = 'button, details, select, input, textarea, svg, script';
function cellValue(cell) {
  const parts = [];
  const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => (node.parentElement?.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent.replace(/\s+/g, ' ').trim();
    if (text) parts.push(text);
  }
  const value = parts.join(' · ');
  // Long digit strings (mobile numbers, barcodes) and ones with a leading 0 are identifiers: keep them as text.
  if (/^0\d|^\d{8,}$/.test(value)) return value;
  const plain = value.replace(/[₹,\s]/g, '').replace(/^[−–]/, '-');
  return /^-?\d+(\.\d+)?$/.test(plain) ? Number(plain) : value;
}

async function exportList(button) {
  const list = button.closest('[data-list]');
  const headers = [...list.querySelectorAll('thead th')].map((th, index) => ({ index, name: th.textContent.trim() }))
    .filter((column) => column.name && !/^actions?$/i.test(column.name)); // the buttons column is not data
  const rows = matching(list).map((row) => headers.map((column) => (row.cells[column.index] ? cellValue(row.cells[column.index]) : '')));
  const title = list.closest('.card, .modalbox')?.querySelector('h3')?.textContent.trim() || document.querySelector('.topbar h1')?.textContent.trim() || 'List';
  const page = document.querySelector('.topbar h1')?.textContent.trim();
  const name = page && page !== title ? `${page} - ${title}` : title;
  const file = await api.download('/api/export/list.xlsx', { title: name, headers: headers.map((column) => column.name), rows });
  toast(`Exported ${rows.length} row${rows.length === 1 ? '' : 's'} to ${file}`);
}

function apply(list) {
  const pageSize = Number(list.dataset.pageSize) || 50;
  const shown = Number(list.dataset.shown) || pageSize;
  const query = (list.querySelector('[data-input="list.filter"]')?.value || '').trim().toLowerCase();
  const rows = rowsOf(list);
  const matches = matching(list);
  const visible = new Set(matches.slice(0, shown));
  rows.forEach((row) => row.classList.toggle('is-hidden', !visible.has(row)));
  const remaining = matches.length - visible.size;
  const more = list.querySelector('.list-more');
  more.classList.toggle('is-hidden', remaining <= 0);
  more.textContent = `Show ${Math.min(pageSize, remaining)} more (${remaining} left)`;
  list.querySelector('.list-none').classList.toggle('is-hidden', matches.length > 0);
  const count = list.querySelector('.list-count');
  if (count) count.textContent = query ? `${matches.length} of ${rows.length} match` : visible.size < rows.length ? `Showing ${visible.size} of ${rows.length}` : `${rows.length} rows`;
}

function initLists(root) {
  for (const list of root.querySelectorAll('[data-list]:not([data-ready])')) {
    list.dataset.ready = '1';
    apply(list);
  }
}

export function installLists(root = document.body) {
  initLists(root);
  new MutationObserver(() => initLists(root)).observe(root, { childList: true, subtree: true });
}

registerActions({
  'list.filter': (input) => {
    const list = input.closest('[data-list]');
    delete list.dataset.shown;
    apply(list);
  },
  'list.export': exportList,
  'list.more': (button) => {
    const list = button.closest('[data-list]');
    list.dataset.shown = String((Number(list.dataset.shown) || Number(list.dataset.pageSize)) + Number(list.dataset.pageSize));
    apply(list);
  },
});
