from crm.domain.permissions import Permission as P


def list_expenses(ctx):
    return ctx.services.expenses.list(ctx.user, ctx.request.arg('start'), ctx.request.arg('end'))


def create_expense(ctx):
    return {'ok': True, 'id': ctx.services.expenses.create(ctx.user, ctx.body())}


def get_expense(ctx):
    return ctx.services.expenses.get(ctx.user, ctx.params['expense_id'])


def edit_expense(ctx):
    return {'ok': True, 'expense': ctx.services.expenses.update(ctx.user, ctx.params['expense_id'], ctx.body())}


def delete_expense(ctx):
    ctx.services.expenses.delete(ctx.user, ctx.params['expense_id'])
    return {'ok': True}


def list_recurring(ctx):
    return ctx.services.expenses.list_recurring()


def create_recurring(ctx):
    return {'ok': True, 'id': ctx.services.expenses.create_recurring(ctx.user, ctx.body())}


def edit_recurring(ctx):
    return {'ok': True, 'recurring': ctx.services.expenses.update_recurring(ctx.user, ctx.params['recurring_id'], ctx.body())}


def set_recurring_active(ctx):
    return {'ok': True, 'recurring': ctx.services.expenses.set_recurring_active(ctx.user, ctx.params['recurring_id'], ctx.body().get('active'))}


def delete_recurring(ctx):
    ctx.services.expenses.delete_recurring(ctx.user, ctx.params['recurring_id'])
    return {'ok': True}


def register(router):
    router.add('GET', '/api/expenses', list_expenses, (P.EXPENSES_VIEW, P.EXPENSES_CREATE))
    router.add('POST', '/api/expenses', create_expense, P.EXPENSES_CREATE)
    router.add('GET', '/api/expenses/{expense_id}', get_expense, (P.EXPENSES_VIEW, P.EXPENSES_CREATE))
    # Own entries with 'Add expenses'; anyone's with 'Edit and delete everyone's expenses' (checked in the service).
    router.add('POST', '/api/expenses/{expense_id}/edit', edit_expense, (P.EXPENSES_CREATE, P.EXPENSES_MANAGE))
    router.add('POST', '/api/expenses/{expense_id}/delete', delete_expense, (P.EXPENSES_CREATE, P.EXPENSES_MANAGE))
    router.add('GET', '/api/recurring-expenses', list_recurring, (P.RECURRING_EXPENSES_VIEW, P.EXPENSES_MANAGE))
    router.add('POST', '/api/recurring-expenses', create_recurring, P.EXPENSES_CREATE)
    router.add('POST', '/api/recurring-expenses/{recurring_id}/edit', edit_recurring, P.EXPENSES_MANAGE)
    router.add('POST', '/api/recurring-expenses/{recurring_id}/active', set_recurring_active, P.EXPENSES_MANAGE)
    router.add('POST', '/api/recurring-expenses/{recurring_id}/delete', delete_recurring, P.EXPENSES_MANAGE)
