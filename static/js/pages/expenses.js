import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { money, todayISO, yearStartISO } from '../core/format.js';
import { can, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { closeModal, confirmDialog, formModal, toast } from '../ui/feedback.js';
import { barChart, kpi, table } from '../ui/widgets.js';

const FREQUENCIES = ['Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly'].map((f) => [f, f]);
const YES_NO = [['false', 'No'], ['true', 'Yes']];

let expenses = [];
let recurring = [];

// Own entries with 'Add expenses'; anyone's with 'Edit and delete everyone's expenses'.
const canChange = (x) => can('expenses.manage') || (can('expenses.create') && x.user_id === state.user?.id);
const canSeeRecurring = () => can(['recurring_expenses.view', 'expenses.manage']);

const expenseFields = (x = {}) => [
  { name: 'expense_date', label: 'Date', type: 'date', value: x.expense_date || todayISO(), required: true },
  { name: 'category', label: 'Category', value: x.category || 'Miscellaneous', required: true },
  { name: 'amount', label: 'Amount', type: 'number', value: x.amount ?? '', min: 0.01, required: true },
  { name: 'payment_mode', label: 'Payment Mode', value: x.payment_mode || 'Cash' }, { name: 'vendor', label: 'Vendor/Paid To', value: x.vendor || '' },
  { name: 'recurring', label: 'Recurring', type: 'select', value: x.recurring ? 'true' : 'false', options: YES_NO },
  { name: 'notes', label: 'Notes', type: 'textarea', full: true, value: x.notes || '' },
];

const recurringFields = (r = {}) => [
  { name: 'category', label: 'Category', value: r.category || 'Miscellaneous', required: true },
  { name: 'amount', label: 'Amount', type: 'number', value: r.amount ?? '', min: 0.01, required: true },
  { name: 'payment_mode', label: 'Payment Mode', value: r.payment_mode || 'Cash' }, { name: 'vendor', label: 'Vendor/Paid To', value: r.vendor || '' },
  { name: 'frequency', label: 'Frequency', type: 'select', value: r.frequency || 'Monthly', options: FREQUENCIES },
  { name: 'start_date', label: 'Start Date', type: 'date', value: r.start_date || todayISO(), required: true },
  { name: 'end_date', label: 'End Date', type: 'date', value: r.end_date || '' },
  { name: 'notes', label: 'Notes', type: 'textarea', full: true, value: r.notes || '' },
];

const RECURRING_NOTE = 'Recurring templates are saved for reference; post each actual payment as an expense.';

function recurringSection() {
  if (!canSeeRecurring()) return '';
  const rows = recurring.map((r) => html`<tr class="${r.active ? '' : 'muted'}"><td>${r.category}</td><td>${r.vendor || ''}</td><td>${r.frequency}</td>
    <td>${r.start_date}${r.end_date ? html` → ${r.end_date}` : ''}</td><td>${r.payment_mode}</td><td>${money(r.amount)}</td>
    <td><span class="tag ${r.active ? 'good' : ''}">${r.active ? 'Active' : 'Paused'}</span></td>
    <td>${can('expenses.manage') ? html`<div class="row">
      <button class="button" data-action="expenses.editRecurring" data-id="${r.id}">Edit</button>
      <button class="button" data-action="expenses.toggleRecurring" data-id="${r.id}" data-active="${r.active ? 0 : 1}">${r.active ? 'Pause' : 'Resume'}</button>
      <button class="button danger" data-action="expenses.deleteRecurring" data-id="${r.id}">Delete</button></div>` : ''}</td></tr>`);
  return html`<br><div class="card"><h3>Recurring Expenses</h3><p class="small muted">${RECURRING_NOTE}</p>
    ${table(['Category', 'Vendor', 'Frequency', 'Period', 'Mode', 'Amount', 'Status', ''], rows, 'No recurring expenses yet.', { search: false })}</div>`;
}

async function render() {
  [expenses, recurring] = await Promise.all([
    api.get('/api/expenses', { start: yearStartISO(), end: todayISO() }),
    canSeeRecurring() ? api.get('/api/recurring-expenses') : [],
  ]);
  const total = expenses.reduce((sum, x) => sum + Number(x.amount || 0), 0);
  const byDay = {};
  expenses.forEach((x) => (byDay[x.expense_date] = (byDay[x.expense_date] || 0) + Number(x.amount || 0)));
  const days = Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b)).map(([day, value]) => ({ label: day.slice(5), value }));
  const label = can('expenses.view') ? 'Expenses this year' : 'My expenses this year';
  setHtml($('#page'), html`<div class="grid kpis">${kpi(label, money(total))}${kpi('Entries', expenses.length)}</div><br>
    <div class="row"><button class="button primary" data-action="expenses.add">+ Add Expense</button>
      <button class="button" data-action="expenses.addRecurring">+ Recurring</button></div><br>
    <div class="card"><h3>Day-wise Expenses</h3>${barChart(days, 'No expenses recorded.')}</div><br>
    <div class="card">${table(['Date', 'Category', 'Vendor', 'Mode', 'Notes', 'Amount', ''], expenses.map((x) => html`<tr><td>${x.expense_date}</td><td>${x.category}</td>
      <td>${x.vendor || ''}</td><td>${x.payment_mode}</td><td class="small muted">${x.notes || ''}</td><td>${money(x.amount)}</td>
      <td>${canChange(x) ? html`<div class="row"><button class="button" data-action="expenses.edit" data-id="${x.id}">Edit</button>
        <button class="button danger" data-action="expenses.delete" data-id="${x.id}">Delete</button></div>` : ''}</td></tr>`), 'No expenses recorded.')}</div>
    ${recurringSection()}`);
}

const byId = (list, el) => list.find((x) => String(x.id) === el.dataset.id);

registerActions({
  'expenses.add': () => formModal('Add Expense', expenseFields(), 'expenses.save'),
  'expenses.save': async (form) => {
    await api.post('/api/expenses', formValues(form));
    closeModal();
    await render();
    toast('Expense saved');
  },
  'expenses.edit': (el) => {
    const x = byId(expenses, el);
    formModal('Edit Expense', expenseFields(x), 'expenses.saveEdit', { hidden: { id: x.id } });
  },
  'expenses.saveEdit': async (form) => {
    const { id, ...values } = formValues(form);
    await api.post(`/api/expenses/${id}/edit`, values);
    closeModal();
    await render();
    toast('Expense updated');
  },
  'expenses.delete': async (el) => {
    const x = byId(expenses, el);
    const ok = await confirmDialog({ title: 'Delete expense?', danger: true, confirmLabel: 'Delete',
      message: `${x.category} of ${money(x.amount)} on ${x.expense_date} will be removed. This cannot be undone.` });
    if (!ok) return;
    await api.post(`/api/expenses/${x.id}/delete`, {});
    await render();
    toast('Expense deleted');
  },
  'expenses.addRecurring': () => formModal('Recurring Expense', recurringFields(), 'expenses.saveRecurring', { note: RECURRING_NOTE }),
  'expenses.saveRecurring': async (form) => {
    await api.post('/api/recurring-expenses', formValues(form));
    closeModal();
    await render();
    toast('Recurring expense saved');
  },
  'expenses.editRecurring': (el) => {
    const r = byId(recurring, el);
    formModal('Edit Recurring Expense', recurringFields(r), 'expenses.saveRecurringEdit', { hidden: { id: r.id } });
  },
  'expenses.saveRecurringEdit': async (form) => {
    const { id, ...values } = formValues(form);
    await api.post(`/api/recurring-expenses/${id}/edit`, values);
    closeModal();
    await render();
    toast('Recurring expense updated');
  },
  'expenses.toggleRecurring': async (el) => {
    const active = el.dataset.active === '1';
    await api.post(`/api/recurring-expenses/${el.dataset.id}/active`, { active });
    await render();
    toast(active ? 'Recurring expense resumed' : 'Recurring expense paused');
  },
  'expenses.deleteRecurring': async (el) => {
    const r = byId(recurring, el);
    const ok = await confirmDialog({ title: 'Delete recurring expense?', danger: true, confirmLabel: 'Delete',
      message: `The ${r.frequency.toLowerCase()} ${r.category} template of ${money(r.amount)} will be removed. Expenses already posted are kept.` });
    if (!ok) return;
    await api.post(`/api/recurring-expenses/${r.id}/delete`, {});
    await render();
    toast('Recurring expense deleted');
  },
});

registerPage({ name: 'expenses', icon: 'expenses', group: 'People & money', label: 'Expenses', permission: ['expenses.view', 'expenses.create'], render });
