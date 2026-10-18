// Print page: shows one invoice PDF and opens the browser's print dialog automatically.
// Only our own invoice PDFs can be shown here (/api/invoice-pdf/<id> or /api/invoice-receipt/<id>).
const params = new URLSearchParams(location.search);
const kind = params.get('kind') === 'receipt' ? 'invoice-receipt' : 'invoice-pdf';
const id = params.get('id') || '';
// The bill number is only a label; anything that doesn't look like one is ignored.
const number = /^[A-Za-z0-9/-]{1,40}$/.test(params.get('number') || '') ? params.get('number') : '';
// Print automatically only when the app itself opened this tab; a link from elsewhere needs a click on Print.
const openedByApp = (() => {
  try {
    return Boolean(window.opener) && window.opener.location.origin === location.origin;
  } catch {
    return false;
  }
})();
const frame = document.getElementById('doc');
const title = document.getElementById('title');

function printNow() {
  try {
    frame.contentWindow.focus();
    frame.contentWindow.print();
  } catch {
    window.print();
  }
}

if (/^\d+$/.test(id)) {
  const src = `/api/${kind}/${id}`;
  document.getElementById('openPdf').href = src;
  title.textContent = `${number || 'Bill'} — ${kind === 'invoice-receipt' ? '80 mm receipt' : 'A4 invoice'}`;
  document.title = `Print ${number || 'bill'}`;
  if (openedByApp) frame.addEventListener('load', () => setTimeout(printNow, 400), { once: true });
  else document.getElementById('hint').textContent = 'Press Print above to print this bill.';
  frame.src = src;
} else {
  title.textContent = 'No bill selected';
}

document.getElementById('printAgain').addEventListener('click', printNow);
document.getElementById('closeTab').addEventListener('click', () => window.close());
