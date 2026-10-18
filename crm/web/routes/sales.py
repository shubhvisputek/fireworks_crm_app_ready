from crm.domain.permissions import Permission as P
from crm.web.http import Response


def create_sale(ctx):
    invoice_id, number = ctx.services.sales.create_sale(ctx.user, ctx.body())
    return {'ok': True, 'invoice_id': invoice_id, 'invoice_number': number}


def list_invoices(ctx):
    q = ctx.request.query
    return ctx.services.sales.list_invoices(ctx.user, q.get('start'), q.get('end'), q.get('status', 'FINALIZED'))


def invoice_detail(ctx):
    return ctx.services.sales.invoice_detail(ctx.user, ctx.params['invoice_id'])


def invoice_pdf(ctx):
    filename, content = ctx.services.exports.invoice_pdf(ctx.user, ctx.params['invoice_id'])
    return Response.download(filename, content, 'application/pdf', inline=True)


def invoice_receipt(ctx):
    filename, content = ctx.services.exports.invoice_pdf(ctx.user, ctx.params['invoice_id'], receipt=True)
    return Response.download(filename, content, 'application/pdf', inline=True)


def dues(ctx):
    return ctx.services.sales.dues()


def void(ctx):
    return {'ok': True, **ctx.services.sales.void(ctx.user, ctx.params['invoice_id'])}


def edit(ctx):
    return {'ok': True, **ctx.services.sales.edit(ctx.user, ctx.params['invoice_id'], ctx.body())}


def record_return(ctx):
    return {'ok': True, **ctx.services.sales.record_return(ctx.user, ctx.body())}


def collect_payment(ctx):
    return {'ok': True, 'outstanding': ctx.services.sales.collect_payment(ctx.user, ctx.body())}


# --- held bills -------------------------------------------------------------
def hold(ctx):
    return {'ok': True, **ctx.services.held_bills.hold(ctx.user, ctx.body())}


def list_held(ctx):
    return ctx.services.held_bills.list(ctx.user)


def peek_held(ctx):
    return ctx.services.held_bills.peek(ctx.user, ctx.params['held_id'])


def resume_held(ctx):
    return ctx.services.held_bills.resume(ctx.user, ctx.params['held_id'])


def delete_held(ctx):
    ctx.services.held_bills.delete(ctx.user, ctx.params['held_id'])
    return {'ok': True}


def register(router):
    router.add('POST', '/api/sales', create_sale, P.BILLING_CREATE)
    router.add('GET', '/api/invoices', list_invoices, (P.SALES_VIEW, P.SALES_VIEW_OWN))
    router.add('GET', '/api/invoices/{invoice_id}', invoice_detail, (P.SALES_VIEW, P.SALES_VIEW_OWN))
    router.add('GET', '/api/invoice-pdf/{invoice_id}', invoice_pdf, P.INVOICE_PRINT)
    router.add('GET', '/api/invoice-receipt/{invoice_id}', invoice_receipt, P.INVOICE_PRINT)
    router.add('GET', '/api/dues', dues, P.DUES_VIEW)
    router.add('POST', '/api/invoices/{invoice_id}/void', void, P.SALES_VOID)
    router.add('POST', '/api/invoices/{invoice_id}/edit', edit, P.SALES_EDIT)
    router.add('POST', '/api/returns', record_return, P.RETURNS_CREATE)
    router.add('POST', '/api/payments', collect_payment, P.PAYMENTS_COLLECT)
    router.add('GET', '/api/held-bills', list_held, P.HELD_BILLS_USE)
    router.add('POST', '/api/held-bills', hold, P.HELD_BILLS_USE)
    router.add('GET', '/api/held-bills/resume/{held_id}', peek_held, P.HELD_BILLS_USE)
    router.add('POST', '/api/held-bills/resume/{held_id}', resume_held, P.HELD_BILLS_USE)
    router.add('POST', '/api/held-bills/delete/{held_id}', delete_held, P.HELD_BILLS_DELETE)
