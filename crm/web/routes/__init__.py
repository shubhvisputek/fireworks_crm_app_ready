"""HTTP controllers. Each module registers its routes; controllers stay thin and call services."""
from crm.web.routes import auth, catalog, customers, expenses, inventory, operations, reports, sales, settings, suppliers, users


def register_all(router):
    for module in (auth, users, catalog, inventory, suppliers, customers, sales, expenses, settings, reports, operations):
        module.register(router)
