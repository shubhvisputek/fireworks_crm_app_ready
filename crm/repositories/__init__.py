from crm.repositories.customers import CustomerRepository
from crm.repositories.inventory import InventoryRepository
from crm.repositories.invoices import InvoiceRepository
from crm.repositories.misc import (AuditRepository, BackupRepository, ExpenseRepository, HeldBillRepository,
                                   PurchaseRepository, SequenceRepository, SettingsRepository)
from crm.repositories.products import ProductRepository
from crm.repositories.reports import ReportRepository
from crm.repositories.users import UserRepository


class Repositories:
    """All repositories bound to one connection."""

    def __init__(self, conn):
        self.conn = conn
        self.users = UserRepository(conn)
        self.products = ProductRepository(conn)
        self.inventory = InventoryRepository(conn)
        self.customers = CustomerRepository(conn)
        self.invoices = InvoiceRepository(conn)
        self.held_bills = HeldBillRepository(conn)
        self.purchases = PurchaseRepository(conn)
        self.expenses = ExpenseRepository(conn)
        self.settings = SettingsRepository(conn)
        self.audit = AuditRepository(conn)
        self.sequences = SequenceRepository(conn)
        self.reports = ReportRepository(conn)
        self.backup = BackupRepository(conn)
