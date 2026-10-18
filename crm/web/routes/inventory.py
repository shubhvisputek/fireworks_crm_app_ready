from crm.domain.permissions import Permission as P


def adjust(ctx):
    return {'ok': True, 'stock': ctx.services.inventory.adjust(ctx.user, ctx.body())}


def remove(ctx):
    return {'ok': True, 'stock': ctx.services.inventory.remove(ctx.user, ctx.body())}


def ledger(ctx):
    q = ctx.request.query
    return ctx.services.inventory.ledger(ctx.user, q.get('product_id'), q.get('start'), q.get('end'))


def list_purchases(ctx):
    return ctx.services.inventory.list_purchases(ctx.user)


def record_purchase(ctx):
    return {'ok': True, **ctx.services.inventory.record_purchase(ctx.user, ctx.body())}


def reorder_plan(ctx):
    q = ctx.request.query
    return ctx.services.inventory.reorder_plan(ctx.user, q.get('start'), q.get('end'), q.get('growth'))


def storage(ctx):
    return ctx.services.inventory.storage_status()


def register(router):
    router.add('POST', '/api/inventory/adjust', adjust, P.INVENTORY_MANAGE)
    router.add('POST', '/api/inventory/remove', remove, P.INVENTORY_MANAGE)
    router.add('GET', '/api/inventory/ledger', ledger, (P.INVENTORY_MANAGE, P.CATALOG_MANAGE))
    router.add('GET', '/api/inventory/storage', storage, (P.INVENTORY_MANAGE, P.PURCHASES_MANAGE))
    router.add('GET', '/api/reorder-plan', reorder_plan, P.INVENTORY_MANAGE)
    router.add('GET', '/api/purchases', list_purchases, P.PURCHASES_MANAGE)
    router.add('POST', '/api/purchases', record_purchase, P.PURCHASES_MANAGE)
