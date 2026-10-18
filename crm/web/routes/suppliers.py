from crm.domain.permissions import Permission as P


def list_suppliers(ctx):
    return ctx.services.suppliers.list()


def create_supplier(ctx):
    return {'ok': True, 'id': ctx.services.suppliers.create(ctx.user, ctx.body())}


def ledger(ctx):
    return ctx.services.suppliers.ledger(ctx.params['supplier_id'])


def record_payment(ctx):
    return {'ok': True, **ctx.services.suppliers.record_payment(ctx.user, ctx.params['supplier_id'], ctx.body())}


def register(router):
    router.add('GET', '/api/suppliers', list_suppliers, (P.SUPPLIERS_MANAGE, P.PURCHASES_MANAGE))
    router.add('POST', '/api/suppliers', create_supplier, (P.SUPPLIERS_MANAGE, P.PURCHASES_MANAGE))
    router.add('GET', '/api/suppliers/{supplier_id}', ledger, P.SUPPLIERS_MANAGE)
    router.add('POST', '/api/suppliers/{supplier_id}/payments', record_payment, P.SUPPLIERS_MANAGE)
