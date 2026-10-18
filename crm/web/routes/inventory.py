from crm.domain.permissions import Permission as P


def adjust(ctx):
    return {'ok': True, 'stock': ctx.services.inventory.adjust(ctx.user, ctx.body())}


def remove(ctx):
    return {'ok': True, 'stock': ctx.services.inventory.remove(ctx.user, ctx.body())}


def ledger(ctx):
    q = ctx.request.query
    return ctx.services.inventory.ledger(q.get('product_id'), q.get('start'), q.get('end'))


def list_purchases(ctx):
    return ctx.services.inventory.list_purchases()


def record_purchase(ctx):
    return {'ok': True, **ctx.services.inventory.record_purchase(ctx.user, ctx.body())}


def register(router):
    router.add('POST', '/api/inventory/adjust', adjust, P.INVENTORY_MANAGE)
    router.add('POST', '/api/inventory/remove', remove, P.INVENTORY_MANAGE)
    router.add('GET', '/api/inventory/ledger', ledger, P.INVENTORY_MANAGE)
    router.add('GET', '/api/purchases', list_purchases, P.INVENTORY_MANAGE)
    router.add('POST', '/api/purchases', record_purchase, P.INVENTORY_MANAGE)
