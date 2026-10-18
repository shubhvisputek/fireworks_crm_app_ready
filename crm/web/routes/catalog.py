from crm.domain.permissions import Permission as P
from crm.domain.validation import integer_id


def list_products(ctx):
    q = ctx.request.query
    return ctx.services.catalog.list_products(q.get('status', 'ACTIVE'), q.get('q', ''), q.get('category', ''), q.get('limit', 200))


def product_detail(ctx):
    return ctx.services.catalog.product_detail(ctx.user, ctx.params['product_id'])


def categories(ctx):
    return ctx.services.catalog.categories()


def create_product(ctx):
    return {'ok': True, 'id': ctx.services.catalog.create_product(ctx.user, ctx.body())}


def update_product(ctx):
    ctx.services.catalog.update_product(ctx.user, ctx.params['product_id'], ctx.body())
    return {'ok': True}


def remove_product(ctx):
    return {'ok': True, 'action': ctx.services.catalog.remove_product(ctx.user, ctx.params['product_id'])}


def set_price(ctx):
    body = ctx.body()
    ctx.services.catalog.set_unit_price(ctx.user, integer_id(body.get('product_id'), 'Product'), body.get('unit_price'))
    return {'ok': True}


def import_products(ctx):
    fields, files = ctx.request.multipart()
    service = ctx.services.product_import
    if fields.get('mode') == 'preview':
        return service.preview(files.get('file'), fields.get('mapping'))
    return service.import_products(ctx.user, files.get('file'), fields.get('mapping'), fields.get('allow_over_limit'))


def register(router):
    router.add('GET', '/api/products', list_products, P.PRODUCTS_LIST)
    router.add('GET', '/api/products/{product_id}', product_detail, P.CATALOG_MANAGE)
    router.add('GET', '/api/categories', categories, P.CATALOG_MANAGE)
    router.add('POST', '/api/products', create_product, P.CATALOG_MANAGE)
    router.add('POST', '/api/products/{product_id}', update_product, P.CATALOG_MANAGE)
    router.add('POST', '/api/products/{product_id}/remove', remove_product, P.CATALOG_MANAGE)
    router.add('POST', '/api/pricing', set_price, P.PRICING_MANAGE)
    router.add('POST', '/api/import/products', import_products, P.CATALOG_MANAGE)
