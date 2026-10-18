"""Read-only view of the audit trail."""
import json

from crm.domain import validation as v
from crm.services.base import Service


class AuditLogService(Service):
    def search(self, start=None, end=None, user_id=None, entity_type=None, text=None):
        start = v.iso_date(start, 'Start date') or self.today()
        end = v.iso_date(end, 'End date') or self.today()
        rows = self.repos.audit_log.search(start, end, int(user_id) if str(user_id or '').isdigit() else None,
                                           v.text(entity_type, 40) or None, v.text(text, 100) or None)
        for row in rows:
            for key in ('previous_json', 'new_json'):
                raw = row.pop(key)
                try:
                    row[key.replace('_json', '')] = json.loads(raw) if raw else None
                except ValueError:
                    row[key.replace('_json', '')] = raw
            # Never show credentials, even if an old entry captured them.
            for part in (row['previous'], row['new']):
                if isinstance(part, dict):
                    part.pop('password', None)
                    part.pop('password_hash', None)
        return {'entries': rows, 'entity_types': self.repos.audit_log.entity_types(), 'users': self.repos.users.list_public()}
