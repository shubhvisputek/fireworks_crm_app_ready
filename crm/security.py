"""Password hashing, signed session tokens and login throttling."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

PBKDF2_ROUNDS = 120_000


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ROUNDS)
    return f'{PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}'


def verify_password(password, stored):
    try:
        rounds, salt_b64, hash_b64 = stored.split('$')
        digest = hashlib.pbkdf2_hmac('sha256', str(password).encode(), base64.b64decode(salt_b64), int(rounds))
        return hmac.compare_digest(base64.b64encode(digest).decode(), hash_b64)
    except (ValueError, TypeError, AttributeError):
        return False


class SecretStore:
    """Signing key kept in a file next to the database; created on first use."""

    def __init__(self, path):
        self.path = path
        self._key = None
        self._lock = threading.Lock()

    def key(self):
        with self._lock:
            if self._key is None:
                if not os.path.exists(self.path):
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'wb') as handle:
                        handle.write(secrets.token_bytes(32))
                with open(self.path, 'rb') as handle:
                    self._key = handle.read()
            return self._key

    def rotate(self):
        """Replace the key: every session signed with the old one stops working."""
        with self._lock:
            tmp = f'{self.path}.new'
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(secrets.token_bytes(32))
            os.replace(tmp, self.path)
            self._key = None


class TokenSigner:
    """HMAC-signed, expiring JSON tokens used as session cookies."""

    def __init__(self, secret_store):
        self.secrets = secret_store

    def _sign(self, raw):
        return hmac.new(self.secrets.key(), raw.encode(), hashlib.sha256).hexdigest()

    def sign(self, payload):
        raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
        return f'{raw}.{self._sign(raw)}'

    def verify(self, token, now=None):
        try:
            raw, signature = token.split('.', 1)
            if not hmac.compare_digest(signature, self._sign(raw)):
                return None
            payload = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        except (ValueError, TypeError, AttributeError):
            return None
        if not isinstance(payload, dict) or payload.get('exp', 0) < (now or time.time()):
            return None
        return payload


# Checked when a username doesn't exist, so a wrong username takes as long as a wrong password
# (otherwise response times reveal which usernames are real).
DUMMY_HASH = hash_password(secrets.token_hex(16))


class LoginThrottle:
    """Counts failed logins per key (e.g. username+IP, IP, username) within a time window."""

    MAX_TRACKED = 10_000

    def __init__(self, max_failures, window_seconds):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        attempts = [t for t in self._failures.get(key, []) if now - t < self.window]
        if attempts:
            self._failures[key] = attempts
        else:
            self._failures.pop(key, None)
        return attempts

    def is_blocked(self, key, now=None, limit=None):
        with self._lock:
            return len(self._recent(key, now or time.time())) >= (limit or self.max_failures)

    def record_failure(self, key, now=None):
        now = now or time.time()
        with self._lock:
            if len(self._failures) >= self.MAX_TRACKED:
                self._evict(now)
            self._failures.setdefault(key, []).append(now)

    def _evict(self, now):
        """Make room without forgetting the keys that matter: expired entries go first, then the keys
        with the fewest recent failures. (Clearing everything would let a flood of junk usernames
        wipe the count for a real account that is being guessed.)"""
        for key in list(self._failures):
            self._recent(key, now)
        if len(self._failures) >= self.MAX_TRACKED:
            by_weight = sorted(self._failures, key=lambda k: (len(self._failures[k]), self._failures[k][-1]))
            for key in by_weight[:len(self._failures) - int(self.MAX_TRACKED * 0.9)]:
                del self._failures[key]

    def reset(self, key):
        with self._lock:
            self._failures.pop(key, None)
