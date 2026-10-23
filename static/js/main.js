// Entry point: session bootstrap, login, page rendering and account actions.
import { applyTheme, onModeChange, toggleMode } from './core/theme.js';
import { api, setUnauthorizedHandler } from './core/api.js';
import { $, html, setHtml } from './core/html.js';
import { formValues, installActionListeners, registerActions, setErrorReporter } from './core/actions.js';
import { installResponsiveTables } from './ui/responsive.js';
import { installLists } from './ui/lists.js';
import { loadReferenceData, state } from './core/state.js';
import { currentRoute, go, resolvePage, setRenderer } from './core/router.js';
import { renderShell } from './ui/layout.js';
import { cancelConfirm, closeModal, confirmIsOpen, formModal, modalIsOpen, showError, toast } from './ui/feedback.js';
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
import './pages/pricing.js';
import './pages/customers.js';
import './pages/expenses.js';
import './pages/settings.js';
import './pages/users.js';
import './pages/audit.js';
import './pages/backup.js';

// Signing out reloads the app at the start page, so nothing the last person had open (dashboard period, a bill
// in progress, filters, lists) is still in memory when the next person signs in.
const NOTICE_KEY = 'fw-signin-notice';
function startOver(notice) {
  try {
    if (notice) sessionStorage.setItem(NOTICE_KEY, notice);
  } catch {
    /* storage unavailable: the notice is just not shown */
  }
  location.replace('/');
}

function showSigninNotice() {
  try {
    const notice = sessionStorage.getItem(NOTICE_KEY);
    sessionStorage.removeItem(NOTICE_KEY);
    if (notice) toast(notice, 'info');
  } catch {
    /* storage unavailable */
  }
}

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
  applyTheme(state.limits.theme); // undoes an unsaved preview from Settings
  renderShell(page, html`<div class="page-loading" role="status"><span class="spinner"></span>Loading ${page.label}…</div>`);
  try {
    await page.render();
  } catch (error) {
    setHtml($('#page'), errorBox(error));
  }
}

async function startSession(user, limits) {
  state.user = user;
  if (limits) state.limits = limits;
  applyTheme(state.limits.theme);
  await loadReferenceData();
  await renderPage();
}

registerActions({
  'nav.go': (el) => go(el.dataset.page),
  'theme.toggleMode': (el) => {
    const mode = toggleMode();
    el.setAttribute('aria-pressed', String(mode === 'dark'));
  },
  'auth.login': async (form) => {
    const result = await api.post('/api/login', formValues(form));
    await startSession(result.user, result.limits);
  },
  'auth.logout': async () => {
    try {
      await api.post('/api/logout');
    } finally {
      startOver();
    }
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
  if (event.key !== 'Escape') return;
  if (confirmIsOpen()) cancelConfirm();
  else if (modalIsOpen()) closeModal();
});

setErrorReporter(showError);
setRenderer(renderPage);
setUnauthorizedHandler(() => {
  if (state.user) startOver('Your session has ended. Please sign in again.');
});
installActionListeners();
// Charts draw with per-mode colours, so the dashboard is redrawn when the mode changes; CSS handles everything else.
onModeChange(() => {
  if (state.user && document.querySelector('.dashboard')) renderPage();
});
installResponsiveTables();
installLists();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js').catch(() => {});

(async () => {
  try {
    const me = await api.get('/api/me');
    if (me.authenticated) await startSession(me.user, me.limits);
    else {
      renderLogin();
      showSigninNotice();
    }
  } catch (error) {
    setHtml($('#app'), errorBox(error));
  }
})();
