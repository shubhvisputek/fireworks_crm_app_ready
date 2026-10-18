// Application state shared across pages.
import { api } from './api.js';

export const state = {
  user: null,
  products: [],
  customers: [],
  settings: null,
  targets: null,
  limits: { max_discount_pct: 100, receipt_format: 'A4' }, // shop rules every user needs (from /api/me)
  menuCollapsed: readSetting('fw-menu-collapsed') === 'true',
  menuOpen: false,
};

function readSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function saveSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: preference just isn't remembered */
  }
}

// can('a') or can(['a', 'b']) — true when the user has any of the permissions.
export const can = (permission) =>
  (Array.isArray(permission) ? permission : [permission]).some((p) => state.user?.permissions?.includes(p));

export function findProduct(id) {
  return state.products.find((product) => product.id === Number(id));
}

// Reference data the pages need, limited to what this user may read.
export async function loadReferenceData() {
  const tasks = [api.get('/api/products', { limit: 500 }).then((rows) => (state.products = rows))];
  if (can(['customers.view', 'customers.manage'])) tasks.push(api.get('/api/customers').then((rows) => (state.customers = rows)));
  if (can('settings.manage')) {
    tasks.push(api.get('/api/settings').then((data) => {
      state.settings = data.settings;
      state.targets = data.targets;
    }));
  }
  await Promise.all(tasks);
}
