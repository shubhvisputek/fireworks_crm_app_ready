// Hash-based page routing. Pages declare the permission they need; the
// navigation and the access check both come from the same list.
import { can, state } from './state.js';

const pages = [];

export function registerPage(page) {
  pages.push(page);
}

export const visiblePages = () => pages.filter((page) => !page.permission || can(page.permission));

export function currentRoute() {
  return location.hash.slice(1) || 'dashboard';
}

let renderCurrent = () => {};
export function setRenderer(renderer) {
  renderCurrent = renderer;
}

export function resolvePage(name) {
  const allowed = visiblePages();
  return allowed.find((page) => page.name === name) || allowed[0];
}

export function go(name) {
  state.menuOpen = false;
  if (currentRoute() === name) renderCurrent();
  else location.hash = name;
}

window.addEventListener('hashchange', () => renderCurrent());
