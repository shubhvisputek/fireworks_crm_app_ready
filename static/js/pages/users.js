import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

async function render() {
  const users = await api.get('/api/users');
  setHtml($('#page'), html`<div class="grid two">
      <div class="card"><h3>Create staff account</h3><form data-submit="users.create"><div class="formgrid">
        <label>Username<input class="input" name="username" minlength="3" maxlength="32" pattern="[A-Za-z0-9][A-Za-z0-9_.\\-]{2,31}" autocomplete="off" required></label>
        <label>Temporary password<input class="input" name="password" type="password" minlength="8" autocomplete="new-password" required></label></div>
        <p class="small muted">Staff can use Dashboard, Billing, Expenses, Analytics, and Backup &amp; Export, and change their own password.</p>
        <button class="button primary">Create staff account</button></form></div>
      <div class="card"><h3>Access roles</h3><p class="small muted">Administrators have full access. Staff can record bills and expenses,
        view the dashboard and analytics, and download exports or backups. Only administrators can edit or delete bills, and manage
        products, stock, customers, prices, settings and users.</p></div></div><br>
    <div class="card"><h3>Accounts</h3>${table(['Username', 'Role', 'Status', 'Created', ''], users.map((user) => html`<tr>
      <td><strong>${user.username}</strong></td><td>${user.role === 'OWNER' ? 'Administrator' : 'Staff'}</td>
      <td><span class="tag ${user.active ? 'good' : 'bad'}">${user.active ? 'Active' : 'Inactive'}</span></td><td>${String(user.created_at || '').slice(0, 10)}</td>
      <td>${user.id === state.user.id ? html`<span class="small muted">Current account</span>`
        : html`<button class="button ${user.active ? 'danger' : 'primary'}" data-action="users.setStatus" data-id="${user.id}" data-active="${user.active ? 0 : 1}">${user.active ? 'Deactivate' : 'Activate'}</button>`}</td></tr>`))}</div>`);
}

registerActions({
  'users.create': async (form) => {
    await api.post('/api/users', formValues(form));
    toast('Staff account created');
    render();
  },
  'users.setStatus': async (el) => {
    const active = el.dataset.active === '1';
    await api.post(`/api/users/${el.dataset.id}/status`, { active });
    toast(active ? 'Account activated' : 'Account deactivated');
    render();
  },
});

registerPage({ name: 'users', label: 'Users', title: 'User Management', permission: 'users.manage', render });
