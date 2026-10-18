// The signed-in app frame: sidebar navigation and top bar.
import { $, html, setHtml } from '../core/html.js';
import { can, saveSetting, state } from '../core/state.js';
import { visiblePages } from '../core/router.js';
import { registerActions } from '../core/actions.js';

const isMobile = () => matchMedia('(max-width:760px)').matches;

export function renderShell(activePage, body) {
  const expanded = isMobile() ? state.menuOpen : !state.menuCollapsed;
  setHtml($('#app'), html`<div class="app ${state.menuCollapsed ? 'menu-collapsed' : ''} ${state.menuOpen ? 'mobile-menu-open' : ''}">
    <div class="sidebar-backdrop" data-action="menu.close"></div>
    <aside class="sidebar"><div class="brand">🎇 Fireworks CRM<small>${state.user?.role_label || ''}</small></div>
      <button class="button sidebar-close" aria-label="Close navigation" data-action="menu.close">×</button>
      <nav class="nav">${visiblePages().map((page) =>
        html`<button class="${page.name === activePage.name ? 'active' : ''}" data-action="nav.go" data-page="${page.name}">${page.label}</button>`)}</nav>
    </aside>
    <main class="main"><div class="topbar">
      <button class="button menu-toggle" aria-label="Toggle navigation" aria-expanded="${expanded}" data-action="menu.toggle">☰</button>
      <h1>${activePage.title || activePage.label}</h1>
      <div class="row">${can('billing.create') ? html`<button class="button primary" data-action="billing.newFromAnywhere">+ New Bill</button>` : ''}
        <span class="small muted">${state.user?.name || state.user?.username}</span>
        <button class="button" data-action="account.password">Password</button>
        <button class="button" data-action="auth.logout">Logout</button></div></div>
      <div class="content" id="page">${body}</div></main></div>`);
}

registerActions({
  'menu.toggle': () => {
    if (isMobile()) state.menuOpen = !state.menuOpen;
    else {
      state.menuCollapsed = !state.menuCollapsed;
      saveSetting('fw-menu-collapsed', String(state.menuCollapsed));
    }
    const app = $('.app');
    app.classList.toggle('menu-collapsed', state.menuCollapsed);
    app.classList.toggle('mobile-menu-open', state.menuOpen);
  },
  'menu.close': () => {
    state.menuOpen = false;
    $('.app')?.classList.remove('mobile-menu-open');
  },
});
