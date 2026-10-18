// Entry point: session bootstrap, login, page rendering and account actions.
import { api, setUnauthorizedHandler } from './core/api.js';
import { $, html, setHtml } from './core/html.js';
import { formValues, installActionListeners, registerActions, setErrorReporter } from './core/actions.js';
import { loadReferenceData, state } from './core/state.js';
import { currentRoute, go, resolvePage, setRenderer } from './core/router.js';
import { renderShell } from './ui/layout.js';
import { closeModal, formModal, modalIsOpen, showError, toast } from './ui/feedback.js';
import { errorBox } from './ui/widgets.js';

// Pages register themselves in navigation order.
import './pages/dashboard.js';
import './pages/billing.js';
import './pages/sales.js';
import './pages/cash_closing.js';
import './pages/dues.js';
import './pages/products.js';
import './pages/inventory.js';
import './pages/suppliers.js';
import './pages/customers.js';
import './pages/expenses.js';
import './pages/pricing.js';
import './pages/analytics.js';
import './pages/settings.js';
import './pages/users.js';
import './pages/audit.js';
import './pages/backup.js';

function renderLogin() {
  state.user = null;
  setHtml($('#app'), html`<div class="login"><div class="loginbox"><div class="brand">🎇 Fireworks CRM<small>Billing • Inventory • Analytics</small></div>
    <form data-submit="auth.login"><label>Username<input class="input" name="username" autocomplete="username" required></label><br>
    <label>Password<input class="input" name="password" type="password" autocomplete="current-password" required></label><br>
    <button class="button primary" style="width:100%">Sign in</button></form></div></div>`);
  $('#app input')?.focus();
}

async function renderPage() {
  if (!state.user) return renderLogin();
  const page = resolvePage(currentRoute());
  if (!page) return setHtml($('#app'), errorBox(new Error('This account has no pages available.')));
  if (page.name !== currentRoute()) {
    history.replaceState(null, '', `#${page.name}`);
  }
  closeModal();
  renderShell(page, html`<div class="muted small">Loading…</div>`);
  try {
    await page.render();
  } catch (error) {
    setHtml($('#page'), errorBox(error));
  }
}

async function startSession(user, limits) {
  state.user = user;
  if (limits) state.limits = limits;
  await loadReferenceData();
  await renderPage();
}

registerActions({
  'nav.go': (el) => go(el.dataset.page),
  'auth.login': async (form) => {
    const result = await api.post('/api/login', formValues(form));
    await startSession(result.user, result.limits);
  },
  'auth.logout': async () => {
    await api.post('/api/logout');
    renderLogin();
  },
  'account.password': () => formModal('Change Password', [
    { name: 'current_password', label: 'Current password', type: 'password', required: true },
    { name: 'new_password', label: 'New password (8+ characters)', type: 'password', required: true },
  ], 'account.savePassword', { submitLabel: 'Change Password', note: 'You will stay signed in here; other devices will be signed out.' }),
  'account.savePassword': async (form) => {
    await api.post('/api/password', formValues(form));
    closeModal();
    toast('Password changed');
  },
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && modalIsOpen()) closeModal();
});

setErrorReporter(showError);
setRenderer(renderPage);
setUnauthorizedHandler(() => {
  if (state.user) {
    toast('Your session has ended. Please sign in again.');
    renderLogin();
  }
});
installActionListeners();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(() => {});

(async () => {
  try {
    const me = await api.get('/api/me');
    if (me.authenticated) await startSession(me.user, me.limits);
    else renderLogin();
  } catch (error) {
    setHtml($('#app'), errorBox(error));
  }
})();
