"""Base class giving every service its repositories, clock and config."""
from crm.db import transaction


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

    def audit(self, actor, action, entity_type, entity_id, previous=None, new=None):
        self.repos.audit.log(actor['id'] if actor else None, action, entity_type, entity_id, self.now(), previous, new)
