// Day-end cash closing: expected takings since the last closing against the counted drawer.
import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { dateTime, money } from '../core/format.js';
import { can } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { field, toast } from '../ui/feedback.js';
import { table } from '../ui/widgets.js';

const differenceTag = (value) => html`<span class="tag ${Math.abs(value) < 0.01 ? 'good' : value < 0 ? 'bad' : 'warn'}">${value > 0 ? '+' : ''}${money(value)}</span>`;

async function render() {
  const [summary, history] = await Promise.all([
    can('cash_closing.own') ? api.get('/api/cash-closing/summary') : null,
    api.get('/api/cash-closings'),
  ]);
  const showUser = can('cash_closing.view_all');
  setHtml($('#page'), html`${summary ? html`<div class="grid two">
      <div class="card"><h3>Since ${dateTime(summary.period_start)}</h3>
        ${summary.modes.length ? summary.modes.map((m) => html`<div class="between notice"><span>${m.mode}</span><strong>${money(m.amount)}</strong></div>`)
          : html`<div class="muted small">No payments taken yet.</div>`}
        <div class="between"><span>Refunds given</span><strong>−${money(summary.refunds)}</strong></div>
        <div class="between"><span>Cash expenses paid</span><strong>−${money(summary.cash_expenses)}</strong></div><hr>
        <div class="between"><span>Cash expected in drawer</span><strong style="font-size:22px">${money(summary.expected_cash)}</strong></div>
        <p class="small muted">${summary.bills} bills. Credit sales are not cash and are excluded.</p></div>
      <div class="card"><h3>Close my drawer</h3><form data-submit="cashClosing.close"><div class="formgrid">
        ${field({ name: 'counted_cash', label: 'Cash counted in drawer', type: 'number', value: '', required: true })}
        ${summary.modes.filter((m) => m.mode.toUpperCase() !== 'CASH').map((m) => field({ name: `counted_${m.mode}`, label: `${m.mode} confirmed`, type: 'number', value: m.amount }))}
        ${field({ name: 'notes', label: 'Notes (e.g. reason for a difference)', type: 'textarea', full: true })}</div><br>
        <button class="button primary">Close drawer</button></form></div></div><br>` : ''}
    <div class="card"><h3>${showUser ? 'All closings' : 'My closings'}</h3>${table([...(showUser ? ['Cashier'] : []), 'Closed', 'Bills', 'Expected cash', 'Counted', 'Difference', 'Notes'],
      history.map((c) => html`<tr>${showUser ? html`<td>${c.user_name}</td>` : ''}<td>${dateTime(c.closed_at)}</td><td>${c.bills}</td>
        <td>${money(c.expected_cash)}</td><td>${money(c.counted_cash)}</td><td>${differenceTag(c.difference)}</td><td>${c.notes || ''}</td></tr>`),
      'No closings yet.')}</div>`);
}

registerActions({
  'cashClosing.close': async (form) => {
    const values = formValues(form);
    const counted = Object.fromEntries(Object.entries(values).filter(([key]) => key.startsWith('counted_') && key !== 'counted_cash')
      .map(([key, value]) => [key.slice('counted_'.length), Number(value)]));
    const result = await api.post('/api/cash-closing', { counted_cash: Number(values.counted_cash), counted, notes: values.notes });
    toast(Math.abs(result.difference) < 0.01 ? 'Drawer closed — cash matches.' : `Drawer closed. Difference ${money(result.difference)}`);
    await render();
  },
});

registerPage({ name: 'cash-closing', label: 'Cash Closing', permission: ['cash_closing.own', 'cash_closing.view_all'], render });
