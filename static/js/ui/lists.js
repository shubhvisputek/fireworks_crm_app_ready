// Long tables (see widgets.table): filter rows by the search box and show them 50 at a time.
// Works on the rendered rows, so every page gets it without extra code.
import { registerActions } from '../core/actions.js';

function rowsOf(list) {
  return [...list.querySelectorAll('tbody > tr')].filter((row) => !row.classList.contains('empty-row'));
}

function apply(list) {
  const pageSize = Number(list.dataset.pageSize) || 50;
  const shown = Number(list.dataset.shown) || pageSize;
  const query = (list.querySelector('[data-input="list.filter"]')?.value || '').trim().toLowerCase();
  const rows = rowsOf(list);
  const matches = query ? rows.filter((row) => row.textContent.toLowerCase().includes(query)) : rows;
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
  'list.more': (button) => {
    const list = button.closest('[data-list]');
    list.dataset.shown = String((Number(list.dataset.shown) || Number(list.dataset.pageSize)) + Number(list.dataset.pageSize));
    apply(list);
  },
});
