// Audit log: who did what and when, with before/after details.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { dateTime, todayISO } from '../core/format.js';
import { registerPage } from '../core/router.js';
import { field } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

let filters = {};

function describe(value) {
  if (!value || typeof value !== 'object') return value ?? '';
  return Object.entries(value).slice(0, 8).map(([key, item]) => `${key}: ${typeof item === 'object' ? JSON.stringify(item) : item}`).join(' · ');
}

async function render() {
  const query = { start: filters.start || todayISO(), end: filters.end || todayISO(), ...(filters.user_id ? { user_id: filters.user_id } : {}),
    ...(filters.entity ? { entity: filters.entity } : {}), ...(filters.q ? { q: filters.q } : {}) };
  const data = await api.get('/api/audit', query);
  setHtml($('#page'), html`<div class="card"><form data-submit="audit.filter"><div class="formgrid">
      ${field({ name: 'start', label: 'From', type: 'date', value: query.start })}${field({ name: 'end', label: 'To', type: 'date', value: query.end })}
      ${field({ name: 'user_id', label: 'User', type: 'select', value: filters.user_id || '', options: [['', 'Everyone'], ...data.users.map((u) => [u.id, u.display_name || u.username])] })}
      ${field({ name: 'entity', label: 'Area', type: 'select', value: filters.entity || '', options: [['', 'Everything'], ...data.entity_types.map((t) => [t, t.replace(/_/g, ' ').toLowerCase()])] })}
      ${field({ name: 'q', label: 'Contains text', value: filters.q || '' })}</div><br><button class="button primary">Show</button></form></div><br>
    <div class="card">${table(['When', 'Who', 'Action', 'Item', 'Before', 'After'], data.entries.map((e) => html`<tr>
      <td>${dateTime(e.created_at)}</td><td>${e.user_name || '-'}</td><td><strong>${e.action}</strong></td><td>${e.entity_type || ''} ${e.entity_id || ''}</td>
      <td class="small">${describe(e.previous)}</td><td class="small">${describe(e.new)}</td></tr>`), 'Nothing recorded for these filters.')}</div>`);
}

registerActions({
  'audit.filter': (form) => {
    filters = formValues(form);
    render();
  },
});

registerPage({ name: 'audit', label: 'Audit Log', permission: 'audit.view', render });
