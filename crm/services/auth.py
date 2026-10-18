"""Login, sessions and password changes."""
from crm.domain.permissions import permissions_for
from crm.errors import AuthenticationError, RateLimited, ValidationError
from crm.security import hash_password, verify_password
from crm.services.base import Service

MIN_PASSWORD_LENGTH = 8


def public_user(user):
    """User fields safe to send to the browser, plus their permissions."""
    if not user:
        return None
    safe = {key: user[key] for key in ('id', 'username', 'role', 'active', 'created_at') if key in user}
    safe['permissions'] = sorted(p.value for p in permissions_for(user.get('role')))
    return safe


class AuthService(Service):
    def __init__(self, *args, throttle, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle = throttle

    def login(self, username, password):
        key = str(username or '').strip().lower()
        if self.throttle.is_blocked(key):
            raise RateLimited('Too many failed login attempts. Try again in 15 minutes.')
        user = self.repos.users.get_active_by_username(str(username or ''))
        if not user or not verify_password(str(password or ''), user['password_hash']):
            self.throttle.record_failure(key)
            raise AuthenticationError('Invalid username or password')
        self.throttle.reset(key)
        return user

    def session_payload(self, user):
        return {'uid': user['id'], 'sv': user['session_version'], 'exp': self.clock.timestamp() + 86400 * self.config.session_days}

    def user_for_session(self, payload):
        """The active user a verified session token belongs to, or None if revoked."""
        if not payload:
            return None
        user = self.repos.users.get_active(payload.get('uid'))
        if not user or payload.get('sv', 0) != user['session_version']:
            return None
        return user

    def change_password(self, actor, current_password, new_password):
        new_password = str(new_password or '')
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(f'New password must be at least {MIN_PASSWORD_LENGTH} characters.')
        user = self.repos.users.get(actor['id'])
        if not verify_password(str(current_password or ''), user['password_hash']):
            raise ValidationError('Current password is incorrect.')
        with self.transaction():
            self.repos.users.set_password(user['id'], hash_password(new_password))
            self.audit(actor, 'Password changed', 'USER', user['id'])
        return self.repos.users.get(user['id'])

    def ensure_admin(self):
        """Create the first administrator on an empty database."""
        if self.repos.users.count():
            return
        password = self.config.admin_password
        if self.config.require_admin_password and not password:
            raise RuntimeError('Set FIREWORKS_ADMIN_PASSWORD before initializing the hosted database.')
        if password and len(password) < 12:
            raise RuntimeError('FIREWORKS_ADMIN_PASSWORD must be at least 12 characters.')
        if not password and self.config.is_network_exposed:
            raise RuntimeError('Set FIREWORKS_ADMIN_PASSWORD before exposing the app on a network (HOST is not localhost).')
        with self.transaction():
            self.repos.users.create('admin', hash_password(password or self.config.default_admin_password), 'OWNER', self.now())

    def default_password_in_use(self):
        return any(verify_password(self.config.default_admin_password, h) for h in self.repos.users.list_active_hashes())
