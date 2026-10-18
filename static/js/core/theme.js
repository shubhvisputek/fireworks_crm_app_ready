// Shop theme (chosen by the owner in Settings) and each person's light/dark mode.
// Both are attributes on <html>; static/themes.css does the rest. The last theme is
// remembered on this device so the login screen and first paint already use it.
import { setChartMode } from '../ui/charts.js';

export const THEMES = [
  { name: 'classic', label: 'Classic', note: 'The original look: dark sidebar, indigo buttons.', swatch: ['#111827', '#4f46e5', '#f6f7fb'] },
  { name: 'clean', label: 'Clean & calm', note: 'White sidebar, one blue accent, flat cards. Easy on the eyes all day.', swatch: ['#ffffff', '#2563eb', '#f6f6f4'] },
  { name: 'festive', label: 'Festive brand', note: 'Night-sky sidebar, saffron buttons, warm cream background.', swatch: ['#1e1b4b', '#e8590c', '#fbf6ee'] },
  { name: 'counter', label: 'Counter pro', note: 'High contrast, bigger text and buttons. Best for tablets and touch screens.', swatch: ['#09090b', '#0f766e', '#f4f4f5'] },
  { name: 'royal', label: 'Royal Diwali', note: 'Maroon and gold on ivory. Traditional and premium.', swatch: ['#5b0f1d', '#c9a227', '#fdf9f1'] },
  { name: 'soft', label: 'Soft modern', note: 'Soft gradient background with frosted-glass cards.', swatch: ['#c7d2fe', '#0d9488', '#f4f6fd'] },
];
const MODES = ['system', 'light', 'dark'];

const read = (key) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
const write = (key, value) => {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: the choice just isn't remembered */
  }
};

const darkQuery = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
const listeners = new Set();

/** Called with no arguments whenever the effective light/dark mode changes. */
export function onModeChange(listener) {
  listeners.add(listener);
}

export const modePreference = () => (MODES.includes(read('fw-mode')) ? read('fw-mode') : 'system');
export const effectiveMode = () => document.documentElement.dataset.mode || 'light';

function applyMode() {
  const preference = modePreference();
  const mode = preference === 'system' ? (darkQuery?.matches ? 'dark' : 'light') : preference;
  const changed = document.documentElement.dataset.mode !== mode;
  document.documentElement.dataset.mode = mode;
  setChartMode(mode);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = getComputedStyle(document.documentElement).getPropertyValue('--top-bg').trim() || '#111827';
  if (changed) listeners.forEach((listener) => listener());
}

export function applyTheme(name) {
  const theme = THEMES.some((t) => t.name === name) ? name : 'classic';
  document.documentElement.dataset.theme = theme;
  write('fw-theme', theme);
  applyMode();
}

/** Switch between light and dark. Until someone switches, the device's own setting is followed. */
export function toggleMode() {
  write('fw-mode', effectiveMode() === 'dark' ? 'light' : 'dark');
  applyMode();
  return effectiveMode();
}

darkQuery?.addEventListener?.('change', () => modePreference() === 'system' && applyMode());
applyTheme(read('fw-theme'));
