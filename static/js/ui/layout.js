// The signed-in app frame: sidebar navigation and top bar.
import { $, html, setHtml } from '../core/html.js';
import { can, saveSetting, state } from '../core/state.js';
import { visiblePages } from '../core/router.js';
import { registerActions } from '../core/actions.js';
import { effectiveMode } from '../core/theme.js';
import { icon } from './icons.js';

// Below this width the sidebar is a slide-out drawer (phones and tablets); keep in step with overrides.css.
const isMobile = () => matchMedia('(max-width:1024px)').matches;

// Pages are listed in registration order; a section label appears where the group changes.
function navItems(activePage) {
  let group = null;
  return visiblePages().map((page) => {
    const label = page.group && page.group !== group ? html`<div class="nav-group">${page.group}</div>` : '';
    group = page.group;
    return html`${label}<button class="${page.name === activePage.name ? 'active' : ''}" data-action="nav.go" data-page="${page.name}"
      ${page.name === activePage.name ? html`aria-current="page"` : ''}>${icon(page.icon, 'nav-icon')}<span>${page.label}</span></button>`;
  });
}

export function renderShell(activePage, body) {
  const expanded = isMobile() ? state.menuOpen : !state.menuCollapsed;
  setHtml($('#app'), html`<div class="app ${state.menuCollapsed ? 'menu-collapsed' : ''} ${state.menuOpen ? 'mobile-menu-open' : ''}">
    <div class="sidebar-backdrop" data-action="menu.close"></div>
    <aside class="sidebar"><div class="brand">🎇 Fireworks CRM<small>${state.user?.name || state.user?.username} • ${state.user?.role_label || ''}</small></div>
      <button class="button sidebar-close" aria-label="Close navigation" data-action="menu.close">×</button>
      <nav class="nav" aria-label="Main">${navItems(activePage)}</nav>
    </aside>
    <main class="main"><div class="topbar">
      <button class="button menu-toggle" aria-label="Toggle navigation" aria-expanded="${expanded}" data-action="menu.toggle">☰</button>
      <h1>${activePage.title || activePage.label}</h1>
      <div class="row topbar-actions">${can('billing.create') ? html`<button class="button primary" data-action="billing.newFromAnywhere" aria-label="New Bill" title="New bill">${icon('plus')}<span class="label">New Bill</span></button>` : ''}
        <span class="small muted topbar-user">${state.user?.name || state.user?.username}</span>
        <button class="button icon-only mode-toggle" data-action="theme.toggleMode" aria-pressed="${effectiveMode() === 'dark'}"
          aria-label="Dark mode" title="Switch light / dark">${icon('moon', 'icon-svg when-light')}${icon('sun', 'icon-svg when-dark')}</button>
        <button class="button icon-button" data-action="account.password" aria-label="Change password" title="Change password"><span class="icon">${icon('key')}</span><span class="label">Password</span></button>
        <button class="button icon-button" data-action="auth.logout" aria-label="Logout" title="Logout"><span class="icon">${icon('logout')}</span><span class="label">Logout</span></button></div></div>
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
