import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money } from '../core/format.js';
import { can } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

const TYPES = [['RETAIL', 'Retail'], ['WHOLESALE', 'Wholesale']];

// Every customer, with what they have bought and still owe (the list is fetched whole, not the first 100).
async function render() {
  const customers = await api.get('/api/customers/all');
  const owing = customers.filter((c) => c.outstanding > 0);
  setHtml($('#page'), html`${can('customers.manage') ? html`<div class="row"><button class="button primary" data-action="customers.add">+ Customer</button></div><br>` : ''}
    <div class="card"><div class="between wrap"><h3>Customers</h3><span class="small muted">${customers.length} customers${owing.length
      ? ` • ${owing.length} owe ${money(owing.reduce((sum, c) => sum + c.outstanding, 0))}` : ''}</span></div>
    ${table(['Customer', 'Phone', 'Type', 'Bills', 'Bought', 'Due', 'Last bill', 'Address / notes'], customers.map((c) => html`<tr>
      <td><strong>${c.name}</strong><div class="small muted">${c.customer_code}</div></td><td>${c.phone || ''}</td><td>${c.customer_type}</td>
      <td>${c.bills}</td><td>${money(c.total_bought)}</td><td>${c.outstanding > 0 ? html`<strong>${money(c.outstanding)}</strong>` : '—'}</td>
      <td>${c.last_bill || '—'}</td><td>${c.address || ''}${c.notes ? html`<div class="small muted">${c.notes}</div>` : ''}</td></tr>`),
      'No customers yet. Customers are also added automatically from bills with a name or mobile number.')}</div>`);
}

registerActions({
  'customers.add': () => formModal('New Customer', [
    { name: 'name', label: 'Name', required: true }, { name: 'phone', label: 'Phone', type: 'tel' },
    { name: 'customer_type', label: 'Type', type: 'select', value: 'RETAIL', options: TYPES },
    { name: 'address', label: 'Address' }, { name: 'notes', label: 'Notes', type: 'textarea', full: true },
  ], 'customers.save'),
  'customers.save': async (form) => {
    await api.post('/api/customers', formValues(form));
    closeModal();
    await render();
    toast('Customer added');
  },
});

registerPage({ name: 'customers', icon: 'customers', group: 'People & money', label: 'Customers', permission: ['customers.view', 'customers.manage'], render });
