from crm.domain.permissions import Permission as P


def search(ctx):
    return ctx.services.customers.search(ctx.request.arg('q', ''))


def create(ctx):
    return {'ok': True, 'id': ctx.services.customers.create(ctx.user, ctx.body())}


def register(router):
    router.add('GET', '/api/customers', search, (P.CUSTOMERS_VIEW, P.CUSTOMERS_MANAGE))
    router.add('POST', '/api/customers', create, P.CUSTOMERS_MANAGE)
