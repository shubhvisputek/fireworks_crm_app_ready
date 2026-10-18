from crm.domain.permissions import Permission as P


def list_expenses(ctx):
    return ctx.services.expenses.list(ctx.user, ctx.request.arg('start'), ctx.request.arg('end'))


def create_expense(ctx):
    return {'ok': True, 'id': ctx.services.expenses.create(ctx.user, ctx.body())}


def list_recurring(ctx):
    return ctx.services.expenses.list_recurring()


def create_recurring(ctx):
    return {'ok': True, 'id': ctx.services.expenses.create_recurring(ctx.user, ctx.body())}


def register(router):
    router.add('GET', '/api/expenses', list_expenses, (P.EXPENSES_VIEW, P.EXPENSES_CREATE))
    router.add('POST', '/api/expenses', create_expense, P.EXPENSES_CREATE)
    router.add('GET', '/api/recurring-expenses', list_recurring, P.RECURRING_EXPENSES_VIEW)
    router.add('POST', '/api/recurring-expenses', create_recurring, P.EXPENSES_CREATE)
