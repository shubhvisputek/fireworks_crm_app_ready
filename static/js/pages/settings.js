import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { field, toast } from '../ui/feedback.js';
import { THEMES, applyTheme } from '../core/theme.js';

function render() {
  const s = state.settings || {};
  const t = state.targets || {};
  const current = s.theme || state.limits.theme || 'classic';
  setHtml($('#page'), html`<form data-submit="settings.save" class="grid"><div class="card"><h3>Appearance</h3>
    <p class="small muted">The look everyone in the shop sees. Click one to preview it; it applies to everyone when you save.
      Each person can still switch dark mode with the moon button at the top.</p>
    <div class="theme-grid" role="radiogroup" aria-label="Theme">${THEMES.map((t) => html`<label class="theme-option">
      <input type="radio" name="theme" value="${t.name}" ${t.name === current ? html`checked` : ''} data-change="settings.previewTheme">
      <span class="theme-swatch" aria-hidden="true"><i style="background:${t.swatch[0]}"></i><i style="background:${t.swatch[1]}"></i><i style="background:${t.swatch[2]}"></i></span>
      <span class="theme-name">${t.label}</span><span class="small muted">${t.note}</span></label>`)}</div></div>
    <div class="card"><h3>Business & Invoice Settings</h3><div class="formgrid">
    ${field({ name: 'business_name', label: 'Business Name', value: s.business_name, required: true })}
    ${field({ name: 'license_number', label: 'License Number', value: s.license_number })}
    ${field({ name: 'phone', label: 'Phone', value: s.phone })}
    ${field({ name: 'email', label: 'Email', value: s.email })}
    ${field({ name: 'address', label: 'Address', type: 'textarea', value: s.address, full: true })}
    ${field({ name: 'invoice_prefix', label: 'Invoice Prefix (letters/numbers)', value: s.invoice_prefix })}
    ${field({ name: 'invoice_footer', label: 'Invoice Footer', value: s.invoice_footer })}
    ${field({ name: 'receipt_format', label: 'Print after billing', type: 'select', value: s.receipt_format || 'A4', options: [['A4', 'A4 invoice (customer + seller copy)'], ['80mm', '80 mm thermal receipt']] })}
    ${field({ name: 'max_discount_pct', label: 'Max discount without manager approval (%)', type: 'number', value: s.max_discount_pct ?? 10, step: 1 })}
    ${field({ name: 'storage_limit_kg', label: 'Licence storage limit (kg explosive content, 0 = off)', type: 'number', value: s.storage_limit_kg ?? 0, step: '0.1' })}
    ${field({ name: 'login_lockout', label: 'Wrong-password lockout', type: 'select', value: s.login_lockout === false ? '0' : '1',
      options: [['1', 'On: lock after 10 wrong passwords for 15 min'], ['0', 'Off: never lock anyone out']] })}
    ${field({ name: 'backup_keep_days', label: 'Daily backups to keep', type: 'number', value: s.backup_keep_days ?? 30, min: 3, step: 1 })}
    ${field({ name: 'daily', label: 'Daily Sales Target', type: 'number', value: t.daily })}
    ${field({ name: 'weekly', label: 'Weekly Sales Target', type: 'number', value: t.weekly })}
    ${field({ name: 'monthly', label: 'Monthly Sales Target', type: 'number', value: t.monthly })}
    ${field({ name: 'seasonal', label: 'Seasonal Sales Target', type: 'number', value: t.seasonal })}
    ${field({ name: 'season_start', label: 'Season Start', type: 'date', value: t.season_start })}
    ${field({ name: 'season_end', label: 'Season End', type: 'date', value: t.season_end })}
  </div><br><button class="button primary">Save Settings</button></div></form>`);
}

registerActions({
  'settings.previewTheme': (el) => applyTheme(el.value),
  'settings.save': async (form) => {
    const v = formValues(form);
    const settings = { business_name: v.business_name, license_number: v.license_number, phone: v.phone, email: v.email, address: v.address,
      invoice_prefix: v.invoice_prefix, invoice_footer: v.invoice_footer, receipt_format: v.receipt_format, max_discount_pct: v.max_discount_pct,
      storage_limit_kg: v.storage_limit_kg, backup_keep_days: v.backup_keep_days, theme: v.theme, login_lockout: v.login_lockout === '1' };
    const targets = { daily: v.daily, weekly: v.weekly, monthly: v.monthly, seasonal: v.seasonal, season_start: v.season_start, season_end: v.season_end };
    await api.post('/api/settings', { settings, targets });
    await loadReferenceData();
    Object.assign(state.limits, { theme: settings.theme, receipt_format: settings.receipt_format, max_discount_pct: Number(settings.max_discount_pct), business_name: settings.business_name });
    toast('Settings saved');
  },
});

registerPage({ name: 'settings', icon: 'settings', group: 'Admin', label: 'Settings', permission: 'settings.manage', render });
