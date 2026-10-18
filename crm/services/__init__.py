"""Service container: one instance per request, bound to one database connection."""
from functools import cached_property

from crm.repositories import Repositories
from crm.services.audit_log import AuditLogService
from crm.services.auth import AuthService
from crm.services.cash_closing import CashClosingService
from crm.services.catalog import CatalogService
from crm.services.customers import CustomerService
from crm.services.demo import DemoService
from crm.services.expenses import ExpenseService
from crm.services.exports import ExportService
from crm.services.held_bills import HeldBillService
from crm.services.inventory import InventoryService
from crm.services.product_import import ProductImportService
from crm.services.reports import ReportService
from crm.services.sales import SalesService
from crm.services.settings import SettingsService
from crm.services.suppliers import SupplierService
from crm.services.users import UserService


class Services:
    def __init__(self, conn, clock, config, throttle, backups=None):
        self.repos = Repositories(conn)
        self.clock = clock
        self.config = config
        self.throttle = throttle
        self.backups = backups  # BackupManager (file snapshots); shared by the whole application

    def _make(self, cls, **extra):
        return cls(self.repos, self.clock, self.config, services=self, **extra)

    @cached_property
    def auth(self):
        return self._make(AuthService, throttle=self.throttle)

    @cached_property
    def users(self):
        return self._make(UserService)

    @cached_property
    def catalog(self):
        return self._make(CatalogService)

    @cached_property
    def product_import(self):
        return self._make(ProductImportService)

    @cached_property
    def inventory(self):
        return self._make(InventoryService)

    @cached_property
    def customers(self):
        return self._make(CustomerService)

    @cached_property
    def sales(self):
        return self._make(SalesService)

    @cached_property
    def held_bills(self):
        return self._make(HeldBillService)

    @cached_property
    def expenses(self):
        return self._make(ExpenseService)

    @cached_property
    def settings(self):
        return self._make(SettingsService)

    @cached_property
    def reports(self):
        return self._make(ReportService)

    @cached_property
    def exports(self):
        return self._make(ExportService)

    @cached_property
    def demo(self):
        return self._make(DemoService)

    @cached_property
    def suppliers(self):
        return self._make(SupplierService)

    @cached_property
    def cash_closing(self):
        return self._make(CashClosingService)

    @cached_property
    def audit_log(self):
        return self._make(AuditLogService)
