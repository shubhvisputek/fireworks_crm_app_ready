"""Business settings and sales targets."""
from crm.db.schema import DEFAULT_SETTINGS
from crm.domain import validation as v
from crm.errors import ValidationError
from crm.services.base import Service

TEXT_SETTINGS = ('business_name', 'address', 'gstin', 'license_number', 'phone', 'email', 'logo', 'state', 'state_code',
                 'invoice_prefix', 'invoice_footer', 'walk_in_name')
BOOL_SETTINGS = ('negative_stock_allowed', 'batch_tracking')
NUMBER_SETTINGS = ('default_gst_rate', 'default_cess_rate')
TARGET_FIELDS = ('daily', 'weekly', 'monthly', 'seasonal')


class SettingsService(Service):
    _cache = None  # per-request cache; a new service instance is built for each request

    def get_settings(self):
        if self._cache is None:
            self._cache = {**DEFAULT_SETTINGS, **self.repos.settings.settings()}
        return self._cache

    def get_targets(self):
        return self.repos.settings.targets()

    def update(self, actor, data):
        """Merge known settings over the current ones; unknown keys are ignored."""
        incoming = data.get('settings') or {}
        targets_in = data.get('targets') or {}
        if not isinstance(incoming, dict) or not isinstance(targets_in, dict):
            raise ValidationError('Settings must be an object.')
        old = self.get_settings()
        merged = dict(old)
        for key in TEXT_SETTINGS:
            if key in incoming:
                merged[key] = v.text(incoming[key], 1000)
        for key in BOOL_SETTINGS:
            if key in incoming:
                merged[key] = v.parse_bool(incoming[key])
        for key in NUMBER_SETTINGS:
            if key in incoming:
                merged[key] = v.amount(incoming[key], key.replace('_', ' ').capitalize(), default=0.0)
        if not merged['business_name']:
            raise ValidationError('Business name is required.')
        current_targets = self.get_targets()
        targets = {key: v.amount(targets_in.get(key, current_targets.get(key)), f'{key.title()} target', default=0.0) for key in TARGET_FIELDS}
        targets['season_start'] = v.iso_date(targets_in.get('season_start', current_targets.get('season_start')), 'Season start')
        targets['season_end'] = v.iso_date(targets_in.get('season_end', current_targets.get('season_end')), 'Season end')
        if targets['season_start'] and targets['season_end'] and targets['season_end'] < targets['season_start']:
            raise ValidationError('Season end cannot be before season start.')
        with self.transaction():
            self.repos.settings.save_settings(merged)
            self.repos.settings.save_targets(targets)
            self.audit(actor, 'Settings updated', 'SETTINGS', 1, previous={'settings': old, 'targets': current_targets},
                       new={'settings': merged, 'targets': targets})
        self._cache = merged
