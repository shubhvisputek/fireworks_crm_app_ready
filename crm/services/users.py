"""User accounts, roles and per-user permissions."""
import json
import re

from crm.domain import validation as v
from crm.domain.permissions import (ASSIGNABLE_ROLES, OWNER, PERMISSION_LABELS, ROLE_LABELS, ROLE_PERMISSIONS, Permission,
                                    effective_permissions, parse_permission_list)
from crm.errors import NotFoundError, PermissionDenied, ValidationError
from crm.security import hash_password
from crm.services.auth import MIN_PASSWORD_LENGTH, WEAK_PASSWORDS, public_user
from crm.services.base import Service

USERNAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,31}')


def _password(value, field='Password'):
    if not isinstance(value, str) or len(value) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f'{field} must be at least {MIN_PASSWORD_LENGTH} characters.')
    if value.lower() in WEAK_PASSWORDS:
        raise ValidationError(f'{field} is too easy to guess. Choose another one.')
    return value


class UserService(Service):
    def catalog(self):
        """Roles and permissions, for the user-management screen."""
        return {
            'roles': [{'role': role, 'label': ROLE_LABELS[role], 'permissions': sorted(p.value for p in ROLE_PERMISSIONS[role])}
                      for role in (OWNER, *ASSIGNABLE_ROLES)],
            'assignable_roles': list(ASSIGNABLE_ROLES),
            'permissions': [{'permission': p.value, 'label': PERMISSION_LABELS[p]} for p in Permission],
        }

    def list(self):
        return [public_user(user) for user in self.repos.users.list_public()]

    def _role(self, value):
        role = v.text(value, 20).upper()
        if role not in ASSIGNABLE_ROLES:
            raise ValidationError('Choose a valid role.')
        return role

    def _permissions_json(self, role, permissions):
        """None means 'use the role preset'; otherwise store the chosen set if it differs from the preset."""
        if permissions is None:
            return None
        if not isinstance(permissions, list):
            raise ValidationError('Permissions must be a list.')
        chosen = parse_permission_list(permissions)
        if chosen == ROLE_PERMISSIONS[role]:
            return None
        return json.dumps(sorted(p.value for p in chosen))

    @staticmethod
    def _guard_target(actor, target):
        """Only an owner may change an owner's account (otherwise "Manage users" would be a way to take over the shop)."""
        if target['role'] == OWNER and actor['role'] != OWNER:
            raise PermissionDenied("Only the owner can change the owner's account.")

    @staticmethod
    def _guard_grant(actor, user_like):
        """Nobody can give someone access they don't have themselves."""
        extra = effective_permissions(user_like) - effective_permissions(actor)
        if extra:
            names = ', '.join(sorted(PERMISSION_LABELS.get(p, p.value) for p in extra))
            raise PermissionDenied(f'You cannot give access you do not have yourself: {names}.')

    def create(self, actor, data):
        username = v.text(data.get('username'), 64)
        if not USERNAME_RE.fullmatch(username):
            raise ValidationError('Username must be 3–32 characters and use only letters, numbers, dots, dashes, or underscores.')
        password = _password(data.get('password'))
        role = self._role(data.get('role') or 'CASHIER')
        display_name = v.optional_text(data.get('display_name'), 60)
        permissions_json = self._permissions_json(role, data.get('permissions'))
        self._guard_grant(actor, {'role': role, 'permissions_json': permissions_json})
        with self.transaction():
            if self.repos.users.username_exists(username):
                raise ValidationError('That username is already in use.')
            user_id = self.repos.users.create(username, hash_password(password), role, self.now(), display_name, permissions_json)
            self.audit(actor, 'User created', 'USER', user_id, new={'username': username, 'role': role, 'display_name': display_name,
                                                                    'permissions': permissions_json})
        return user_id

    def update(self, actor, user_id, data):
        """Change a user's display name, role and permissions. Owners can only change their display name."""
        with self.transaction():
            target = self.repos.users.get(user_id)
            if not target:
                raise NotFoundError('User not found.')
            self._guard_target(actor, target)
            display_name = v.optional_text(data.get('display_name', target['display_name']), 60)
            if target['role'] == OWNER:
                if 'role' in data and str(data['role']).upper() != OWNER or data.get('permissions') is not None:
                    raise ValidationError("The owner's role and permissions cannot be changed.")
                self.repos.users.set_display_name(user_id, display_name)
            else:
                role = self._role(data.get('role', target['role']))
                permissions_json = self._permissions_json(role, data.get('permissions')) if 'permissions' in data else (
                    target['permissions_json'] if role == target['role'] else None)
                if target['id'] == actor['id'] and (role != target['role'] or permissions_json != target['permissions_json']):
                    raise PermissionDenied('You cannot change your own role or permissions. Ask the owner.')
                self._guard_grant(actor, {'role': role, 'permissions_json': permissions_json})
                self.repos.users.update_profile(user_id, role, display_name, permissions_json)
            updated = self.repos.users.get(user_id)
            self.audit(actor, 'User updated', 'USER', user_id,
                       previous={'role': target['role'], 'display_name': target['display_name'], 'permissions': sorted(p.value for p in effective_permissions(target))},
                       new={'role': updated['role'], 'display_name': updated['display_name'], 'permissions': sorted(p.value for p in effective_permissions(updated))})
        return public_user(updated)

    def reset_password(self, actor, user_id, password):
        password = _password(password, 'New password')
        with self.transaction():
            target = self.repos.users.get(user_id)
            if not target:
                raise NotFoundError('User not found.')
            if target['id'] == actor['id']:
                raise ValidationError('Use the Password button to change your own password.')
            self._guard_target(actor, target)
            self.repos.users.set_password(user_id, hash_password(password))
            self.audit(actor, 'Password reset', 'USER', user_id, new={'username': target['username']})

    def set_active(self, actor, user_id, payload):
        if 'active' not in payload:
            raise ValidationError('Active status is required.')
        active = v.strict_bool(payload['active'], 'Active status')
        with self.transaction():
            target = self.repos.users.get(user_id)
            if not target:
                raise NotFoundError('User not found.')
            self._guard_target(actor, target)
            if not active and target['id'] == actor['id']:
                raise ValidationError('You cannot deactivate your own account.')
            if not active and target['role'] == OWNER and self.repos.users.count_active_owners() <= 1:
                raise ValidationError('At least one active administrator must remain.')
            self.repos.users.set_active(user_id, active)
            self.audit(actor, 'User activated' if active else 'User deactivated', 'USER', user_id,
                       previous={'username': target['username'], 'active': target['active']},
                       new={'username': target['username'], 'active': int(active)})
        return active
