"""Roles and permissions.

Every API route declares the permission it needs; roles are just named sets of
permissions. Adding a role (e.g. Manager, Cashier) means adding an entry to
ROLE_PERMISSIONS, not touching routes.
"""
from enum import Enum


class Permission(str, Enum):
    DASHBOARD_VIEW = 'dashboard.view'
    ANALYTICS_VIEW = 'analytics.view'
    BILLING_CREATE = 'billing.create'
    HELD_BILLS_USE = 'held_bills.use'
    HELD_BILLS_DELETE = 'held_bills.delete'
    INVOICE_PRINT = 'invoices.print'
    SALES_VIEW = 'sales.view'
    SALES_MANAGE = 'sales.manage'
    PRODUCTS_LIST = 'products.list'
    CATALOG_MANAGE = 'catalog.manage'
    INVENTORY_MANAGE = 'inventory.manage'
    CUSTOMERS_MANAGE = 'customers.manage'
    EXPENSES_VIEW = 'expenses.view'
    EXPENSES_CREATE = 'expenses.create'
    RECURRING_EXPENSES_VIEW = 'recurring_expenses.view'
    REPORTS_EXPORT = 'reports.export'
    BACKUP_DOWNLOAD = 'backup.download'
    SETTINGS_MANAGE = 'settings.manage'
    USERS_MANAGE = 'users.manage'


OWNER = 'OWNER'
STAFF = 'STAFF'

ROLE_PERMISSIONS = {
    OWNER: frozenset(Permission),
    STAFF: frozenset({
        Permission.DASHBOARD_VIEW, Permission.ANALYTICS_VIEW, Permission.BILLING_CREATE,
        Permission.HELD_BILLS_USE, Permission.INVOICE_PRINT, Permission.PRODUCTS_LIST,
        Permission.EXPENSES_VIEW, Permission.EXPENSES_CREATE, Permission.REPORTS_EXPORT,
        Permission.BACKUP_DOWNLOAD,
    }),
}

ROLE_LABELS = {OWNER: 'Administrator', STAFF: 'Staff'}


def permissions_for(role):
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(user, permission):
    return bool(user) and permission in permissions_for(user.get('role'))
