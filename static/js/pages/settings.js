import { api } from '../core/api.js';
import { $, html, setHtml } from '../core/html.js';
import { formValues, registerActions } from '../core/actions.js';
import { loadReferenceData, state } from '../core/state.js';
import { registerPage } from '../core/router.js';
import { field, toast } from '../ui/feedback.js';

function render() {
  const s = state.settings || {};
  const t = state.targets || {};
  setHtml($('#page'), html`<div class="card"><h3>Business & Invoice Settings</h3><form data-submit="settings.save"><div class="formgrid">
    ${field({ name: 'business_name', label: 'Business Name', value: s.business_name, required: true })}
    ${field({ name: 'license_number', label: 'License Number', value: s.license_number })}
    ${field({ name: 'phone', label: 'Phone', value: s.phone })}
    ${field({ name: 'email', label: 'Email', value: s.email })}
    ${field({ name: 'address', label: 'Address', type: 'textarea', value: s.address, full: true })}
    ${field({ name: 'invoice_prefix', label: 'Invoice Prefix (letters/numbers)', value: s.invoice_prefix })}
    ${field({ name: 'invoice_footer', label: 'Invoice Footer', value: s.invoice_footer })}
    ${field({ name: 'daily', label: 'Daily Sales Target', type: 'number', value: t.daily })}
    ${field({ name: 'weekly', label: 'Weekly Sales Target', type: 'number', value: t.weekly })}
    ${field({ name: 'monthly', label: 'Monthly Sales Target', type: 'number', value: t.monthly })}
    ${field({ name: 'seasonal', label: 'Seasonal Sales Target', type: 'number', value: t.seasonal })}
    ${field({ name: 'season_start', label: 'Season Start', type: 'date', value: t.season_start })}
    ${field({ name: 'season_end', label: 'Season End', type: 'date', value: t.season_end })}
  </div><br><button class="button primary">Save Settings</button></form></div>`);
}

registerActions({
  'settings.save': async (form) => {
    const v = formValues(form);
    const settings = { business_name: v.business_name, license_number: v.license_number, phone: v.phone, email: v.email, address: v.address,
      invoice_prefix: v.invoice_prefix, invoice_footer: v.invoice_footer };
    const targets = { daily: v.daily, weekly: v.weekly, monthly: v.monthly, seasonal: v.seasonal, season_start: v.season_start, season_end: v.season_end };
    await api.post('/api/settings', { settings, targets });
    await loadReferenceData();
    toast('Settings saved');
  },
});

registerPage({ name: 'settings', label: 'Settings', permission: 'settings.manage', render });
