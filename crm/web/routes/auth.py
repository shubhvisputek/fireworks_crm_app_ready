from crm.errors import ValidationError
from crm.services.auth import public_user
from crm.web.router import AUTHENTICATED, PUBLIC


def shop_limits(ctx):
    settings = ctx.services.settings.get_settings()
    return {'max_discount_pct': settings.get('max_discount_pct'), 'receipt_format': settings.get('receipt_format', 'A4'),
            'business_name': settings.get('business_name')}


def me(ctx):
    user = ctx.services.auth.user_for_session(ctx.app.session_payload(ctx.request))
    return {'authenticated': bool(user), 'user': public_user(user), 'limits': shop_limits(ctx) if user else None}


def login(ctx):
    try:
        body = ctx.body()
    except ValidationError:
        raise ValidationError('Invalid login request.')
    user = ctx.services.auth.login(body.get('username', ''), body.get('password', ''))
    ctx.start_session(user)
    return {'ok': True, 'user': public_user(user), 'limits': shop_limits(ctx)}


def logout(ctx):
    ctx.end_session()
    return {'ok': True}


def change_password(ctx):
    body = ctx.body()
    user = ctx.services.auth.change_password(ctx.user, body.get('current_password'), body.get('new_password'))
    ctx.start_session(user)  # other sessions were revoked; keep this one signed in
    return {'ok': True}


def register(router):
    router.add('GET', '/api/me', me, PUBLIC)
    router.add('POST', '/api/login', login, PUBLIC)
    router.add('POST', '/api/logout', logout, PUBLIC)
    router.add('POST', '/api/password', change_password, AUTHENTICATED)
