// Application state shared across pages.
import { api } from './api.js';

export const state = {
  user: null,
  products: [],
  customers: [],
  settings: null,
  targets: null,
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

export const can = (permission) => Boolean(state.user?.permissions?.includes(permission));

export function findProduct(id) {
  return state.products.find((product) => product.id === Number(id));
}

// Reference data the pages need, limited to what this user may read.
export async function loadReferenceData() {
  const tasks = [api.get('/api/products', { limit: 500 }).then((rows) => (state.products = rows))];
  if (can('customers.manage')) tasks.push(api.get('/api/customers').then((rows) => (state.customers = rows)));
  if (can('settings.manage')) {
    tasks.push(api.get('/api/settings').then((data) => {
      state.settings = data.settings;
      state.targets = data.targets;
    }));
  }
  await Promise.all(tasks);
}
