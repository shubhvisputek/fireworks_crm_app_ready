from crm.domain.permissions import Permission as P


def get_settings(ctx):
    return {'settings': ctx.services.settings.get_settings(), 'targets': ctx.services.settings.get_targets()}


def update_settings(ctx):
    ctx.services.settings.update(ctx.user, ctx.body())
    return {'ok': True}


def register(router):
    router.add('GET', '/api/settings', get_settings, P.SETTINGS_MANAGE)
    router.add('POST', '/api/settings', update_settings, P.SETTINGS_MANAGE)
