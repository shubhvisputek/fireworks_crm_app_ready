import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { can, loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

const TYPES = [['WHOLESALE', 'Wholesale'], ['RETAIL', 'Retail']];

function render() {
  setHtml($('#page'), html`${can('customers.manage') ? html`<div class="row"><button class="button primary" data-action="customers.add">+ Customer</button></div><br>` : ''}
    <div class="card">${table(['Customer', 'Phone', 'Type', 'Address', 'Notes'], state.customers.map((c) => html`<tr>
      <td><strong>${c.name}</strong><div class="small muted">${c.customer_code}</div></td><td>${c.phone || ''}</td><td>${c.customer_type}</td>
      <td>${c.address || ''}</td><td>${c.notes || ''}</td></tr>`), 'No customers yet. Customers are also added automatically from bills with a name or mobile number.')}</div>`);
}

registerActions({
  'customers.add': () => formModal('New Customer', [
    { name: 'name', label: 'Name', required: true }, { name: 'phone', label: 'Phone', type: 'tel' },
    { name: 'customer_type', label: 'Type', type: 'select', value: 'WHOLESALE', options: TYPES },
    { name: 'address', label: 'Address' }, { name: 'notes', label: 'Notes', type: 'textarea', full: true },
  ], 'customers.save'),
  'customers.save': async (form) => {
    await api.post('/api/customers', formValues(form));
    await loadReferenceData();
    closeModal();
    render();
    toast('Customer added');
  },
});

registerPage({ name: 'customers', label: 'Customers', permission: ['customers.view', 'customers.manage'], render });
