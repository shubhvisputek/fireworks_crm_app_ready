// Users: roles, per-user permissions, password resets and activation.
import { api } from '../core/api.js';
import { $, $$, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, field, formModal, openModal, toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

let catalog = null;
let users = [];

const roleLabel = (role) => catalog.roles.find((r) => r.role === role)?.label || role;
const rolePreset = (role) => new Set(catalog.roles.find((r) => r.role === role)?.permissions || []);
const roleOptions = () => catalog.assignable_roles.map((role) => [role, roleLabel(role)]);

const ROLE_HELP = {
  MANAGER: 'Runs the counter and stock: bills, edits, voids, returns, approvals, stock and suppliers. No profit, prices, settings or users.',
  CASHIER: 'Bills customers and sees only their own bills, held bills and expenses. Closes their own cash drawer.',
  STOCK_KEEPER: 'Products, purchases, suppliers and stock adjustments only.',
  ACCOUNTANT: 'Sales, profit, dues, expenses and reports. Cannot bill, edit or void.',
  STAFF: 'The access staff had before roles existed.',
};

async function render() {
  [catalog, users] = await Promise.all([catalog || api.get('/api/users/catalog'), api.get('/api/users')]);
  setHtml($('#page'), html`<div class="grid two">
      <div class="card"><h3>Add a user</h3><form data-submit="users.create"><div class="formgrid">
        <label>Username<input class="input" name="username" minlength="3" maxlength="32" pattern="[A-Za-z0-9][A-Za-z0-9_.\\-]{2,31}" autocomplete="off" required></label>
        ${field({ name: 'display_name', label: 'Name shown on bills', placeholder: 'e.g. Rohan' })}
        ${field({ name: 'role', label: 'Role', type: 'select', value: 'CASHIER', options: roleOptions() })}
        <label>Temporary password<input class="input" name="password" type="password" minlength="8" autocomplete="new-password" required></label></div><br>
        <button class="button primary">Add user</button></form></div>
      <div class="card"><h3>Roles</h3>${catalog.assignable_roles.map((role) => html`<p class="small"><strong>${roleLabel(role)}:</strong>
        <span class="muted">${ROLE_HELP[role] || ''}</span></p>`)}<p class="small muted">Use <strong>Edit</strong> to tick or untick individual permissions for one person.</p></div>
    </div><br>
    <div class="card"><h3>Accounts</h3>${table(['User', 'Role', 'Status', 'Created', ''], users.map((user) => html`<tr>
      <td><strong>${user.name}</strong>${user.name !== user.username ? html`<div class="small muted">${user.username}</div>` : ''}</td>
      <td>${user.role_label}${user.custom_permissions ? html` <span class="tag warn">custom</span>` : ''}</td>
      <td><span class="tag ${user.active ? 'good' : 'bad'}">${user.active ? 'Active' : 'Inactive'}</span></td><td>${String(user.created_at || '').slice(0, 10)}</td>
      <td><div class="row"><button class="button" data-action="users.edit" data-id="${user.id}">Edit</button>
        ${user.id === state.user.id ? html`<span class="small muted">You</span>` : html`
        <button class="button" data-action="users.resetPassword" data-id="${user.id}" data-name="${user.name}">Reset password</button>
        <button class="button ${user.active ? 'danger' : 'primary'}" data-action="users.setStatus" data-id="${user.id}" data-active="${user.active ? 0 : 1}">${user.active ? 'Deactivate' : 'Activate'}</button>`}</div></td>
    </tr>`))}</div>`);
}

function permissionBoxes(selected, disabled) {
  return html`<div class="formgrid" id="permissionBoxes">${catalog.permissions.map((p) => html`<label class="row" style="gap:8px;align-items:center">
    <input type="checkbox" name="perm" value="${p.permission}" ${selected.has(p.permission) ? html`checked` : ''} ${disabled ? html`disabled` : ''}>
    <span class="small">${p.label}</span></label>`)}</div>`;
}

registerActions({
  'users.create': async (form) => {
    await api.post('/api/users', formValues(form));
    toast('User added');
    await render();
  },
  'users.edit': (el) => {
    const user = users.find((u) => u.id === Number(el.dataset.id));
    const isOwner = user.role === 'OWNER';
    openModal(`Edit ${user.name}`, html`<form data-submit="users.save"><input type="hidden" name="id" value="${user.id}"><div class="formgrid">
        ${field({ name: 'display_name', label: 'Name shown on bills', value: user.display_name || '' })}
        ${isOwner ? html`<label>Role<input class="input" value="Owner (full access)" disabled></label>`
          : field({ name: 'role', label: 'Role', type: 'select', value: user.role, options: roleOptions() })}</div><br>
      ${isOwner ? '' : html`<label class="row" style="gap:8px"><input type="checkbox" name="custom" data-change="users.toggleCustom" ${user.custom_permissions ? html`checked` : ''}>
        <span>Customise permissions for this person</span></label><br>`}
      ${permissionBoxes(new Set(user.permissions), isOwner || !user.custom_permissions)}<br>
      <div class="row" style="justify-content:flex-end"><button type="button" class="button" data-action="modal.close">Cancel</button>
        <button class="button primary">Save</button></div></form>`);
  },
  // Unticked: permissions follow the role. Ticked: the boxes become editable, starting from the role preset.
  'users.toggleCustom': (el) => {
    const form = el.form;
    const preset = rolePreset(form.elements.role.value);
    $$('input[name=perm]', form).forEach((box) => {
      box.disabled = !el.checked;
      if (!el.checked) box.checked = preset.has(box.value);
    });
  },
  'users.save': async (form) => {
    const id = form.elements.id.value;
    const body = { display_name: form.elements.display_name.value };
    if (form.elements.role) {
      body.role = form.elements.role.value;
      body.permissions = form.elements.custom?.checked ? $$('input[name=perm]:checked', form).map((box) => box.value) : null;
    }
    await api.post(`/api/users/${id}`, body);
    closeModal();
    toast('User updated. Their open sessions were signed out so the new access applies now.');
    await render();
  },
  'users.resetPassword': (el) => formModal(`Reset password for ${el.dataset.name}`, [
    { name: 'password', label: 'New temporary password (8+ characters)', type: 'password', required: true },
  ], 'users.savePassword', { hidden: { id: el.dataset.id }, submitLabel: 'Reset password', note: 'They will be signed out everywhere.' }),
  'users.savePassword': async (form) => {
    await api.post(`/api/users/${form.elements.id.value}/password`, { password: form.elements.password.value });
    closeModal();
    toast('Password reset');
  },
  'users.setStatus': async (el) => {
    const active = el.dataset.active === '1';
    await api.post(`/api/users/${el.dataset.id}/status`, { active });
    toast(active ? 'Account activated' : 'Account deactivated');
    await render();
  },
});

// Changing the role in the editor refreshes the preset ticks when not customising.
document.addEventListener('change', (event) => {
  const form = event.target.form;
  if (event.target.name !== 'role' || !form?.matches('[data-submit="users.save"]') || form.elements.custom?.checked) return;
  const preset = rolePreset(event.target.value);
  $$('input[name=perm]', form).forEach((box) => (box.checked = preset.has(box.value)));
});

registerPage({ name: 'users', icon: 'users', group: 'Admin', label: 'Users', title: 'Users & Roles', permission: 'users.manage', render });
