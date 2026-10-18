// On phones, tables are shown as a list of cards (see overrides.css). Each cell
// needs its column name for that, so this copies the header text into a
// data-label on every cell whenever tables are added or re-rendered.
function labelTables(root) {
  for (const table of root.querySelectorAll('table.table')) {
    const headers = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim());
    for (const row of table.querySelectorAll('tbody tr')) {
      [...row.children].forEach((cell, i) => {
        if (!cell.hasAttribute('data-label')) cell.setAttribute('data-label', cell.colSpan > 1 ? '' : headers[i] || '');
      });
    }
  }
}

export function installResponsiveTables(root = document.body) {
  labelTables(root);
  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      labelTables(root);
    });
  }).observe(root, { childList: true, subtree: true });
}
