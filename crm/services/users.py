"""Staff account management."""
import re

from crm.domain import validation as v
from crm.domain.permissions import OWNER, STAFF
from crm.errors import NotFoundError, ValidationError
from crm.security import hash_password
from crm.services.auth import MIN_PASSWORD_LENGTH
from crm.services.base import Service

USERNAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,31}')


class UserService(Service):
    def list(self):
        return self.repos.users.list_public()

    def create_staff(self, actor, username, password):
        username = v.text(username, 64)
        if not USERNAME_RE.fullmatch(username):
            raise ValidationError('Username must be 3–32 characters and use only letters, numbers, dots, dashes, or underscores.')
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
        with self.transaction():
            if self.repos.users.username_exists(username):
                raise ValidationError('That username is already in use.')
            user_id = self.repos.users.create(username, hash_password(password), STAFF, self.now())
            self.audit(actor, 'Staff user created', 'USER', user_id, new={'username': username, 'role': STAFF})
        return user_id

    def set_active(self, actor, user_id, payload):
        if 'active' not in payload:
            raise ValidationError('Active status is required.')
        active = v.strict_bool(payload['active'], 'Active status')
        with self.transaction():
            target = self.repos.users.get(user_id)
            if not target:
                raise NotFoundError('User not found.')
            if not active and target['id'] == actor['id']:
                raise ValidationError('You cannot deactivate your own account.')
            if not active and target['role'] == OWNER and self.repos.users.count_active_owners() <= 1:
                raise ValidationError('At least one active administrator must remain.')
            self.repos.users.set_active(user_id, active)
            self.audit(actor, 'User activated' if active else 'User deactivated', 'USER', user_id,
                       previous={'username': target['username'], 'active': target['active']},
                       new={'username': target['username'], 'active': int(active)})
        return active
