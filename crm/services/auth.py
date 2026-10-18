"""Login, sessions and password changes."""
import secrets

from crm.domain.permissions import ROLE_LABELS, effective_permissions
from crm.errors import AuthenticationError, RateLimited, ValidationError
from crm.security import DUMMY_HASH, hash_password, verify_password
from crm.services.base import Service

MIN_PASSWORD_LENGTH = 8
# Failed logins allowed per 15 minutes. Wrong passwords only ever lock *that username* on *that browser/address*:
# - on a browser where the user has signed in before (trusted device), only that browser's own mistakes count;
# - elsewhere, failures count per username + address, and per username across all untrusted places (slows
#   guessing from many addresses) - which never locks the user's trusted browsers.
# Other users are never affected by someone else's wrong passwords.
SOURCE_LIMIT, UNTRUSTED_USER_LIMIT = 10, 100
MAX_TRUSTED_USERS = 20  # users remembered per browser (a shared counter computer)
# The demo password and the most common passwords are refused when setting a password.
WEAK_PASSWORDS = frozenset({'admin123', 'password', 'password1', 'password123', '12345678', '123456789',
                            '1234567890', 'qwerty123', 'iloveyou', 'admin1234', 'welcome1', 'fireworks', 'abcd1234'})


def public_user(user):
    """User fields safe to send to the browser, plus their effective permissions."""
    if not user:
        return None
    safe = {key: user.get(key) for key in ('id', 'username', 'display_name', 'role', 'active', 'created_at')}
    safe['name'] = user.get('display_name') or user.get('username')
    safe['role_label'] = ROLE_LABELS.get(user.get('role'), user.get('role'))
    safe['custom_permissions'] = bool(user.get('permissions_json')) and user.get('role') != 'OWNER'
    safe['permissions'] = sorted(p.value for p in effective_permissions(user))
    return safe


class AuthService(Service):
    def __init__(self, *args, throttle, **kwargs):
        super().__init__(*args, **kwargs)
        self.throttle = throttle

    def login(self, username, password, client_ip='', device=None):
        """device: the verified trusted-device cookie of this browser, if any."""
        name = str(username or '').strip().lower()
        user = self.repos.users.get_active_by_username(str(username or ''))
        trusted = bool(user and device and user['id'] in device.get('uids', []))
        if trusted:
            keys = {f'login:{name}|device:{device["dev"]}': SOURCE_LIMIT}
        else:
            keys = {f'login:{name}|ip:{client_ip}': SOURCE_LIMIT, f'login:{name}|untrusted': UNTRUSTED_USER_LIMIT}
        if any(self.throttle.is_blocked(key, limit=limit) for key, limit in keys.items()):
            raise RateLimited(f'Too many wrong passwords for {name or "this user"}. Try again in 15 minutes, '
                              'or sign in from a device you have used before.')
        valid = verify_password(str(password or ''), user['password_hash'] if user else DUMMY_HASH)
        if not user or not valid:
            for key in keys:
                self.throttle.record_failure(key)
            raise AuthenticationError('Invalid username or password')
        self.throttle.reset(next(iter(keys)))
        return user

    def device_payload(self, user, device=None):
        """Trusted-device cookie contents: a random browser id and the users who signed in on it."""
        uids = [uid for uid in (device or {}).get('uids', []) if uid != user['id']][-(MAX_TRUSTED_USERS - 1):] + [user['id']]
        return {'kind': 'device', 'dev': (device or {}).get('dev') or secrets.token_hex(16), 'uids': uids,
                'exp': self.clock.timestamp() + 365 * 86400}

    def verify_credentials(self, username, password, purpose='approval'):
        """Check another user's password (e.g. a manager approving a discount). Throttled like logins."""
        key = f'{purpose}:{str(username or "").strip().lower()}'
        if self.throttle.is_blocked(key):
            raise RateLimited('Too many failed attempts. Try again in 15 minutes.')
        user = self.repos.users.get_active_by_username(str(username or ''))
        valid = verify_password(str(password or ''), user['password_hash'] if user else DUMMY_HASH)
        if not user or not valid:
            self.throttle.record_failure(key)
            raise ValidationError('Approver username or password is incorrect.')
        self.throttle.reset(key)
        return user

    def session_payload(self, user):
        # sid identifies this one sign-in, so logging out can revoke it without signing out the user's other devices.
        return {'uid': user['id'], 'sv': user['session_version'], 'sid': secrets.token_hex(16),
                'exp': self.clock.timestamp() + 86400 * self.config.session_days}

    def user_for_session(self, payload):
        """The active user a verified session token belongs to, or None if revoked."""
        if not payload or not isinstance(payload.get('sid'), str) or self.repos.sessions.is_revoked(payload['sid']):
            return None
        user = self.repos.users.get_active(payload.get('uid'))
        if not user or payload.get('sv', 0) != user['session_version']:
            return None
        return user

    def logout(self, payload):
        """Revoke this sign-in on the server; the cookie is also cleared in the browser."""
        if payload and isinstance(payload.get('sid'), str):
            with self.transaction():
                self.repos.sessions.revoke(payload['sid'], int(payload.get('exp', 0)), self.clock.timestamp())

    def change_password(self, actor, current_password, new_password):
        new_password = str(new_password or '')
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(f'New password must be at least {MIN_PASSWORD_LENGTH} characters.')
        if new_password.lower() in WEAK_PASSWORDS:
            raise ValidationError('That password is too easy to guess. Choose another one.')
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
