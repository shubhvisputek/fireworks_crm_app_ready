"""Fireworks CRM: billing, inventory and analytics for a fireworks shop.

Layers (each only depends on the ones below it):

    web/           HTTP adapter, routing, sessions, controllers
    services/      business rules and use cases
    repositories/  SQL access, one module per aggregate
    db/            connection, transactions, schema and migrations
    domain/        pure helpers: money, validation, permissions
    exports/       PDF and Excel rendering
"""
