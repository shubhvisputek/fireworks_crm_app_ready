"""Roles and permissions.

Every API route declares the permission it needs. A role is a named preset of
permissions; the Owner can also customise any non-owner user's permissions,
which are then stored on the user (users.permissions_json).
"""
import json
from enum import Enum


class Permission(str, Enum):
    DASHBOARD_VIEW = 'dashboard.view'
    ANALYTICS_VIEW = 'analytics.view'
    PROFIT_VIEW = 'profit.view'                    # cost prices, gross profit, margins, stock value
    BILLING_CREATE = 'billing.create'
    HELD_BILLS_USE = 'held_bills.use'
    HELD_BILLS_DELETE = 'held_bills.delete'
    INVOICE_PRINT = 'invoices.print'
    SALES_VIEW_OWN = 'sales.view_own'              # own bills only
    SALES_VIEW = 'sales.view'                      # everyone's bills
    SALES_EDIT = 'sales.edit'
    SALES_VOID = 'sales.void'
    RETURNS_CREATE = 'returns.create'
    PAYMENTS_COLLECT = 'payments.collect'
    DISCOUNT_APPROVE = 'discount.approve'          # any discount, and approving others' big discounts
    PRODUCTS_LIST = 'products.list'
    CATALOG_MANAGE = 'catalog.manage'
    PRICING_MANAGE = 'pricing.manage'
    INVENTORY_MANAGE = 'inventory.manage'
    PURCHASES_MANAGE = 'purchases.manage'
    SUPPLIERS_MANAGE = 'suppliers.manage'
    CUSTOMERS_VIEW = 'customers.view'
    CUSTOMERS_MANAGE = 'customers.manage'
    DUES_VIEW = 'dues.view'
    EXPENSES_VIEW = 'expenses.view'                # everyone's expenses
    EXPENSES_CREATE = 'expenses.create'
    RECURRING_EXPENSES_VIEW = 'recurring_expenses.view'
    CASH_CLOSING_OWN = 'cash_closing.own'
    CASH_CLOSING_VIEW_ALL = 'cash_closing.view_all'
    REPORTS_EXPORT = 'reports.export'
    BACKUP_DOWNLOAD = 'backup.download'
    BACKUP_RESTORE = 'backup.restore'
    SETTINGS_MANAGE = 'settings.manage'
    USERS_MANAGE = 'users.manage'
    AUDIT_VIEW = 'audit.view'


P = Permission

PERMISSION_LABELS = {
    P.DASHBOARD_VIEW: 'Dashboard', P.ANALYTICS_VIEW: 'Sales analytics', P.PROFIT_VIEW: 'See cost, profit and margins',
    P.BILLING_CREATE: 'Create bills', P.HELD_BILLS_USE: 'Hold and resume own bills', P.HELD_BILLS_DELETE: 'See and delete everyone\'s held bills',
    P.INVOICE_PRINT: 'Print invoices', P.SALES_VIEW_OWN: 'See own bills', P.SALES_VIEW: 'See all bills',
    P.SALES_EDIT: 'Edit bills', P.SALES_VOID: 'Delete (void) bills', P.RETURNS_CREATE: 'Process returns',
    P.PAYMENTS_COLLECT: 'Collect credit payments', P.DISCOUNT_APPROVE: 'Give or approve any discount',
    P.PRODUCTS_LIST: 'Look up products', P.CATALOG_MANAGE: 'Manage products', P.PRICING_MANAGE: 'Change prices',
    P.INVENTORY_MANAGE: 'Stock adjustments and reorder plan', P.PURCHASES_MANAGE: 'Record purchases (GRN)',
    P.SUPPLIERS_MANAGE: 'Suppliers and supplier payments', P.CUSTOMERS_VIEW: 'See customers', P.CUSTOMERS_MANAGE: 'Add customers',
    P.DUES_VIEW: 'Credit dues list', P.EXPENSES_VIEW: 'See all expenses', P.EXPENSES_CREATE: 'Add expenses',
    P.RECURRING_EXPENSES_VIEW: 'See recurring expenses', P.CASH_CLOSING_OWN: 'Close own cash drawer',
    P.CASH_CLOSING_VIEW_ALL: 'See everyone\'s cash closings', P.REPORTS_EXPORT: 'Excel and PDF reports',
    P.BACKUP_DOWNLOAD: 'Download backups', P.BACKUP_RESTORE: 'Restore backups', P.SETTINGS_MANAGE: 'Business settings',
    P.USERS_MANAGE: 'Manage users', P.AUDIT_VIEW: 'Audit log',
}

OWNER, MANAGER, CASHIER, STOCK_KEEPER, ACCOUNTANT, STAFF = 'OWNER', 'MANAGER', 'CASHIER', 'STOCK_KEEPER', 'ACCOUNTANT', 'STAFF'

ROLE_PERMISSIONS = {
    OWNER: frozenset(Permission),
    MANAGER: frozenset({
        P.DASHBOARD_VIEW, P.ANALYTICS_VIEW, P.BILLING_CREATE, P.HELD_BILLS_USE, P.HELD_BILLS_DELETE, P.INVOICE_PRINT,
        P.SALES_VIEW_OWN, P.SALES_VIEW, P.SALES_EDIT, P.SALES_VOID, P.RETURNS_CREATE, P.PAYMENTS_COLLECT, P.DISCOUNT_APPROVE,
        P.PRODUCTS_LIST, P.CATALOG_MANAGE, P.INVENTORY_MANAGE, P.PURCHASES_MANAGE, P.SUPPLIERS_MANAGE,
        P.CUSTOMERS_VIEW, P.CUSTOMERS_MANAGE, P.DUES_VIEW, P.EXPENSES_VIEW, P.EXPENSES_CREATE, P.REPORTS_EXPORT,
        P.CASH_CLOSING_OWN, P.CASH_CLOSING_VIEW_ALL,
    }),
    CASHIER: frozenset({
        P.DASHBOARD_VIEW, P.BILLING_CREATE, P.HELD_BILLS_USE, P.INVOICE_PRINT, P.SALES_VIEW_OWN, P.PRODUCTS_LIST,
        P.CUSTOMERS_VIEW, P.EXPENSES_CREATE, P.CASH_CLOSING_OWN,
    }),
    STOCK_KEEPER: frozenset({
        P.PRODUCTS_LIST, P.CATALOG_MANAGE, P.INVENTORY_MANAGE, P.PURCHASES_MANAGE, P.SUPPLIERS_MANAGE,
    }),
    ACCOUNTANT: frozenset({
        P.DASHBOARD_VIEW, P.ANALYTICS_VIEW, P.PROFIT_VIEW, P.INVOICE_PRINT, P.SALES_VIEW_OWN, P.SALES_VIEW,
        P.PAYMENTS_COLLECT, P.PRODUCTS_LIST, P.CUSTOMERS_VIEW, P.DUES_VIEW, P.EXPENSES_VIEW, P.EXPENSES_CREATE,
        P.RECURRING_EXPENSES_VIEW, P.REPORTS_EXPORT, P.CASH_CLOSING_VIEW_ALL, P.SUPPLIERS_MANAGE,
    }),
    # Accounts created before roles existed keep exactly the access they had.
    STAFF: frozenset({
        P.DASHBOARD_VIEW, P.ANALYTICS_VIEW, P.PROFIT_VIEW, P.BILLING_CREATE, P.HELD_BILLS_USE, P.INVOICE_PRINT,
        P.SALES_VIEW_OWN, P.PRODUCTS_LIST, P.EXPENSES_VIEW, P.EXPENSES_CREATE, P.REPORTS_EXPORT, P.BACKUP_DOWNLOAD,
        P.CASH_CLOSING_OWN,
    }),
}

ROLE_LABELS = {OWNER: 'Owner', MANAGER: 'Manager', CASHIER: 'Cashier', STOCK_KEEPER: 'Stock keeper',
               ACCOUNTANT: 'Accountant', STAFF: 'Staff (legacy)'}
ASSIGNABLE_ROLES = (MANAGER, CASHIER, STOCK_KEEPER, ACCOUNTANT, STAFF)


def parse_permission_list(values):
    """Valid Permission members from a list of strings; unknown names are dropped."""
    known = {p.value: p for p in Permission}
    return frozenset(known[v] for v in values or [] if v in known)


def effective_permissions(user):
    if not user:
        return frozenset()
    role = user.get('role')
    if role == OWNER:
        return ROLE_PERMISSIONS[OWNER]
    custom = user.get('permissions_json')
    if custom:
        try:
            return parse_permission_list(json.loads(custom))
        except (ValueError, TypeError):
            pass
    return ROLE_PERMISSIONS.get(role, frozenset())


# Kept for callers that only know the role.
def permissions_for(role):
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(user, permission):
    return permission in effective_permissions(user)
