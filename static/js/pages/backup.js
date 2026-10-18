import { $, html, setHtml } from '../core/html.js';
import { registerPage } from '../core/router.js';

function render() {
  setHtml($('#page'), html`<div class="grid three">
      <div class="card"><h3>Full Backup</h3><p class="small muted">All business data as JSON (passwords are never included).</p>
        <a class="button primary" href="/api/backup">Download Backup</a></div>
      <div class="card"><h3>Sales Reports</h3><p class="small muted">Invoice summary or line-by-line sales and payment detail.</p>
        <a class="button" href="/api/export/sales.xlsx">Summary Excel</a><br><br>
        <a class="button primary" href="/api/export/sales-detailed.xlsx">Detailed Sales Excel</a><br><br>
        <a class="button" href="/api/export/sales.pdf">Export PDF</a></div>
      <div class="card"><h3>Help</h3><p class="small muted">Initial Product Master → map/validate → import. Then use Billing, Inventory, Pricing and Expenses directly.</p></div>
    </div><br><div class="notice warn">Keep backup files in a secure location. Financially important records are never hard-deleted.</div>`);
}

registerPage({ name: 'backup', label: 'Backup & Export', permission: 'backup.download', render });
