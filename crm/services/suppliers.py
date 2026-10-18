"""Suppliers, what is owed to them, and payments made to them."""
from crm.domain import validation as v
from crm.domain.money import money
from crm.errors import NotFoundError, ValidationError
from crm.services.base import Service


class SupplierService(Service):
    def list(self):
        return self.repos.suppliers.list()

    def create(self, actor, data):
        name = v.required_text(data.get('name'), 'Supplier name', 200)
        with self.transaction():
            if self.repos.suppliers.find_by_name(name):
                raise ValidationError(f'Supplier {name} already exists.')
            values = {'name': name, 'phone': v.optional_text(data.get('phone'), 20), 'gstin': v.optional_text(data.get('gstin'), 20),
                      'address': v.optional_text(data.get('address')), 'notes': v.optional_text(data.get('notes')), 'created_at': self.now()}
            supplier_id = self.repos.suppliers.create(values)
            self.audit(actor, 'Supplier created', 'SUPPLIER', supplier_id, new=values)
        return supplier_id

    def resolve(self, actor, supplier_id, supplier_name):
        """(id, name) for a purchase: an existing supplier by id or name, or a new one created from the typed name."""
        if supplier_id:
            supplier = self.repos.suppliers.get(v.integer_id(supplier_id, 'Supplier'))
            if not supplier:
                raise ValidationError('Supplier not found.')
            return supplier['id'], supplier['name']
        name = v.text(supplier_name, 200)
        if not name:
            return None, None
        existing = self.repos.suppliers.find_by_name(name)
        if existing:
            return existing['id'], existing['name']
        return self.create(actor, {'name': name}), name

    def ledger(self, supplier_id):
        supplier = self.repos.suppliers.get(supplier_id)
        if not supplier:
            raise NotFoundError('Supplier not found.')
        return {'supplier': supplier, 'purchases': self.repos.suppliers.purchases(supplier_id), 'payments': self.repos.suppliers.payments(supplier_id)}

    def record_payment(self, actor, supplier_id, data):
        amount = v.positive(data.get('amount'), 'Amount')
        with self.transaction():
            supplier = self.repos.suppliers.get(supplier_id)
            if not supplier:
                raise NotFoundError('Supplier not found.')
            values = {'supplier_id': supplier_id, 'payment_date': v.iso_date(data.get('payment_date'), 'Payment date') or self.today(),
                      'mode': v.text(data.get('mode'), 20) or 'Cash', 'amount': money(amount), 'reference': v.optional_text(data.get('reference'), 100),
                      'notes': v.optional_text(data.get('notes')), 'user_id': actor['id'], 'created_at': self.now()}
            payment_id = self.repos.suppliers.add_payment(values)
            self.audit(actor, 'Supplier payment', 'SUPPLIER', supplier_id, new=values)
        return {'payment_id': payment_id, 'balance': money(self.repos.suppliers.get(supplier_id)['balance'])}
