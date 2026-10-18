"""HTTP controllers. Each module registers its routes; controllers stay thin and call services."""
from crm.web.routes import auth, catalog, customers, expenses, inventory, reports, sales, settings, users


def register_all(router):
    for module in (auth, users, catalog, inventory, customers, sales, expenses, settings, reports):
        module.register(router)
