"""Customer master, including customers created on the fly from bills."""
from crm.domain import validation as v
from crm.services.base import Service


class CustomerService(Service):
    def search(self, query=''):
        return self.repos.customers.search(v.text(query, 100))

    def _next_code(self):
        # Older databases used random codes, so skip any number already taken.
        while True:
            code = f"CUST-{self.repos.sequences.next('customer'):05d}"
            if not self.repos.customers.code_exists(code):
                return code

    def create(self, actor, data):
        name = v.required_text(data.get('name'), 'Customer name', 200)
        with self.transaction():
            code = v.text(data.get('customer_code'), 30) or self._next_code()
            values = {
                'customer_code': code, 'name': name, 'phone': v.optional_text(data.get('phone'), 20),
                'address': v.optional_text(data.get('address')), 
                'customer_type': v.text(data.get('customer_type'), 20).upper() or 'RETAIL',
                'credit_enabled': int(v.parse_bool(data.get('credit_enabled'))),
                'credit_limit': v.amount(data.get('credit_limit'), 'Credit limit', default=0.0),
                'state_code': v.text(data.get('state_code'), 5) or self.services.settings.get_settings().get('state_code'),
                'notes': v.optional_text(data.get('notes')), 'created_at': self.now(), 'updated_at': self.now(),
            }
            customer_id = self.repos.customers.create(values)
            self.audit(actor, 'Customer created', 'CUSTOMER', customer_id, new=values)
        return customer_id

    def resolve_for_bill(self, customer_id, name, phone):
        """Find the bill's customer by id, phone or name; create one if details were typed in.

        Returns the customer row or None for an anonymous walk-in sale.
        """
        if customer_id:
            customer = self.repos.customers.get(customer_id)
            if customer:
                return customer
        if not name and not phone:
            return None
        customer = (self.repos.customers.find_by_phone(phone) if phone else None) or (self.repos.customers.find_by_name(name) if name else None)
        if customer:
            return customer
        new_id = self.repos.customers.create({
            'customer_code': self._next_code(), 'name': name or 'Customer', 'phone': phone, 'customer_type': 'CUSTOMER',
            'credit_enabled': 0, 'credit_limit': 0, 'state_code': self.services.settings.get_settings().get('state_code'),
            'created_at': self.now(), 'updated_at': self.now(),
        })
        return self.repos.customers.get(new_id)
