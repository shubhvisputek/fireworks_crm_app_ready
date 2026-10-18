from crm.domain.permissions import Permission as P


def list_users(ctx):
    return ctx.services.users.list()


def catalog(ctx):
    return ctx.services.users.catalog()


def create_user(ctx):
    return {'ok': True, 'id': ctx.services.users.create(ctx.user, ctx.body())}


def update_user(ctx):
    return {'ok': True, 'user': ctx.services.users.update(ctx.user, ctx.params['user_id'], ctx.body())}


def set_status(ctx):
    active = ctx.services.users.set_active(ctx.user, ctx.params['user_id'], ctx.body())
    return {'ok': True, 'active': active}


def reset_password(ctx):
    ctx.services.users.reset_password(ctx.user, ctx.params['user_id'], ctx.body().get('password'))
    return {'ok': True}


def register(router):
    router.add('GET', '/api/users', list_users, P.USERS_MANAGE)
    router.add('GET', '/api/users/catalog', catalog, P.USERS_MANAGE)
    router.add('POST', '/api/users', create_user, P.USERS_MANAGE)
    router.add('POST', '/api/users/{user_id}', update_user, P.USERS_MANAGE)
    router.add('POST', '/api/users/{user_id}/status', set_status, P.USERS_MANAGE)
    router.add('POST', '/api/users/{user_id}/password', reset_password, P.USERS_MANAGE)
