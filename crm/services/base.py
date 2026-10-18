"""Base class giving every service its repositories, clock and config."""
from crm.db import transaction
from crm.domain.permissions import Permission, has_permission
from crm.domain.visibility import strip_fields


class Service:
    def __init__(self, repos, clock, config, services=None):
        self.repos = repos
        self.clock = clock
        self.config = config
        self.services = services  # the owning Services container, for cross-service calls

    def transaction(self):
        return transaction(self.repos.conn)

    def now(self):
        return self.clock.now_iso()

    def today(self):
        return self.clock.today_iso()

    @staticmethod
    def can(actor, permission):
        return has_permission(actor, permission)

    def visible(self, actor, data):
        """Data as this user may see it: cost and profit removed without the profit permission."""
        return data if self.can(actor, Permission.PROFIT_VIEW) else strip_fields(data)

    def audit(self, actor, action, entity_type, entity_id, previous=None, new=None):
        self.repos.audit.log(actor['id'] if actor else None, action, entity_type, entity_id, self.now(), previous, new)
