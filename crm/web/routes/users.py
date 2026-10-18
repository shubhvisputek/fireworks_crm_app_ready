from crm.domain.permissions import Permission as P


def list_users(ctx):
    return ctx.services.users.list()


def create_user(ctx):
    body = ctx.body()
    return {'ok': True, 'id': ctx.services.users.create_staff(ctx.user, body.get('username'), body.get('password'))}


def set_status(ctx):
    active = ctx.services.users.set_active(ctx.user, ctx.params['user_id'], ctx.body())
    return {'ok': True, 'active': active}


def register(router):
    router.add('GET', '/api/users', list_users, P.USERS_MANAGE)
    router.add('POST', '/api/users', create_user, P.USERS_MANAGE)
    router.add('POST', '/api/users/{user_id}/status', set_status, P.USERS_MANAGE)
