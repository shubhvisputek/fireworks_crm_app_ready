import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money, todayISO, yearStartISO } from '../core/format.js';
import { registerPage } from '../core/router.js';
import { closeModal, formModal, toast } from '../ui/feedback.js';
import { barChart, kpi, table } from '../ui/widgets.js';

const FREQUENCIES = ['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly'].map((f) => [f, f]);

async function render() {
  const rows = await api.get('/api/expenses', { start: yearStartISO(), end: todayISO() });
  const total = rows.reduce((sum, x) => sum + Number(x.amount || 0), 0);
  const byDay = {};
  rows.forEach((x) => (byDay[x.expense_date] = (byDay[x.expense_date] || 0) + Number(x.amount || 0)));
  const days = Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b)).map(([day, value]) => ({ label: day.slice(5), value }));
  setHtml($('#page'), html`<div class="grid kpis">${kpi('Expenses this year', money(total))}${kpi('Entries', rows.length)}</div><br>
    <div class="row"><button class="button primary" data-action="expenses.add">+ Add Expense</button>
      <button class="button" data-action="expenses.addRecurring">+ Recurring</button></div><br>
    <div class="card"><h3>Day-wise Expenses</h3>${barChart(days, 'No expenses recorded.')}</div><br>
    <div class="card">${table(['Date', 'Category', 'Vendor', 'Mode', 'Amount'], rows.map((x) => html`<tr><td>${x.expense_date}</td><td>${x.category}</td>
      <td>${x.vendor || ''}</td><td>${x.payment_mode}</td><td>${money(x.amount)}</td></tr>`), 'No expenses recorded.')}</div>`);
}

registerActions({
  'expenses.add': () => formModal('Add Expense', [
    { name: 'expense_date', label: 'Date', type: 'date', value: todayISO(), required: true },
    { name: 'category', label: 'Category', value: 'Miscellaneous', required: true },
    { name: 'amount', label: 'Amount', type: 'number', value: '', min: 0.01, required: true },
    { name: 'payment_mode', label: 'Payment Mode', value: 'Cash' }, { name: 'vendor', label: 'Vendor/Paid To' },
    { name: 'recurring', label: 'Recurring', type: 'select', value: 'false', options: [['false', 'No'], ['true', 'Yes']] },
    { name: 'notes', label: 'Notes', type: 'textarea', full: true },
  ], 'expenses.save'),
  'expenses.save': async (form) => {
    await api.post('/api/expenses', formValues(form));
    closeModal();
    await render();
    toast('Expense saved');
  },
  'expenses.addRecurring': () => formModal('Recurring Expense', [
    { name: 'category', label: 'Category', value: 'Miscellaneous', required: true },
    { name: 'amount', label: 'Amount', type: 'number', value: '', min: 0.01, required: true },
    { name: 'payment_mode', label: 'Payment Mode', value: 'Cash' }, { name: 'vendor', label: 'Vendor/Paid To' },
    { name: 'frequency', label: 'Frequency', type: 'select', value: 'Monthly', options: FREQUENCIES },
    { name: 'start_date', label: 'Start Date', type: 'date', value: todayISO(), required: true }, { name: 'end_date', label: 'End Date', type: 'date' },
    { name: 'notes', label: 'Notes', type: 'textarea', full: true },
  ], 'expenses.saveRecurring', { note: 'Recurring templates are saved for reference; post each actual payment as an expense.' }),
  'expenses.saveRecurring': async (form) => {
    await api.post('/api/recurring-expenses', formValues(form));
    closeModal();
    toast('Recurring expense saved');
  },
});

registerPage({ name: 'expenses', label: 'Expenses', permission: 'expenses.view', render });
