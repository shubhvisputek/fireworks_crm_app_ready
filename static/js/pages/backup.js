// Exports, the JSON backup, and (for the owner) automatic database backups with restore.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { registerActions } from '../core/actions.js';
import { can } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { openModal, toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

const size = (bytes) => (bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`);
const KIND_LABELS = { daily: 'Automatic (daily)', manual: 'Manual', prerestore: 'Safety copy before a restore' };

async function backupsSection() {
  if (!can('backup.restore')) return '';
  const { backups, keep_days: keep } = await api.get('/api/backups');
  return html`<div class="card"><div class="between"><div><h3>Database backups</h3>
      <div class="small muted">A backup is taken automatically every day; the last ${keep} daily backups are kept. Restoring replaces all current data —
        a safety copy is taken first.</div></div>
      <div class="row"><button class="button primary" data-action="backups.create">Backup now</button>
        <button class="button" data-action="backups.upload">Restore from file…</button></div></div><br>
    ${table(['Taken', 'Type', 'Size', ''], backups.map((b) => html`<tr><td>${b.created}</td><td>${KIND_LABELS[b.kind] || b.kind}</td><td>${size(b.size)}</td>
      <td><div class="row"><a class="button" href="/api/backups/download?name=${encodeURIComponent(b.name)}">Download</a>
        <button class="button danger" data-action="backups.restore" data-name="${b.name}" data-created="${b.created}">Restore</button></div></td></tr>`),
      'No backups yet. The first automatic backup is taken shortly after the server starts.')}</div><br>`;
}

async function render() {
  const reports = can('reports.export');
  setHtml($('#page'), html`${await backupsSection()}<div class="grid three">
      ${can('backup.download') ? html`<div class="card"><h3>Data export (JSON)</h3><p class="small muted">All business data as JSON for your records (passwords are never included).</p>
        <a class="button primary" href="/api/backup">Download JSON</a></div>` : ''}
      ${reports ? html`<div class="card"><h3>Sales Reports</h3><p class="small muted">Invoice summary or line-by-line sales and payment detail.</p>
        <a class="button" href="/api/export/sales.xlsx">Summary Excel</a><br><br>
        <a class="button primary" href="/api/export/sales-detailed.xlsx">Detailed Sales Excel</a><br><br>
        <a class="button" href="/api/export/sales.pdf">Export PDF</a></div>` : ''}
    </div><br><div class="notice warn">Keep backup files somewhere safe (for example a pen drive or cloud folder). Financially important records are never hard-deleted.</div>`);
}

async function afterRestore(result) {
  toast(`Restored. A safety copy of the previous data was saved as ${result.safety_backup}. Please sign in again.`);
  setTimeout(() => location.reload(), 2500);
}

registerActions({
  'backups.create': async () => {
    const result = await api.post('/api/backups');
    toast(`Backup saved: ${result.name}`);
    await render();
  },
  'backups.restore': async (el) => {
    if (!confirm(`Restore the backup from ${el.dataset.created}? All changes made after it will be replaced (a safety copy is kept).`)) return;
    await afterRestore(await api.post('/api/backups/restore', { name: el.dataset.name }));
  },
  'backups.upload': () => openModal('Restore from a backup file', html`<p class="small muted">Choose a <strong>.sqlite</strong> backup downloaded from this app.
      All current data will be replaced; a safety copy is taken first.</p>
    <form data-submit="backups.uploadRestore"><input class="input" type="file" name="file" accept=".sqlite,.db" required><br><br>
      <button class="button danger">Restore this file</button></form>`),
  'backups.uploadRestore': async (form) => {
    const file = form.elements.file.files[0];
    if (!file || !confirm(`Replace all current data with ${file.name}?`)) return;
    const data = new FormData();
    data.append('file', file);
    await afterRestore(await api.upload('/api/backups/restore', data));
  },
});

registerPage({ name: 'backup', label: 'Backup & Export', permission: ['backup.download', 'reports.export', 'backup.restore'], render });
