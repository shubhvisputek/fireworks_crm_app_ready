from crm.repositories.base import Repository


class CustomerRepository(Repository):
    def search(self, query='', limit=100):
        like = f'%{query}%'
        return self.all('SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? OR customer_code LIKE ? ORDER BY name LIMIT ?',
                        (like, like, like, limit))

    def get(self, customer_id):
        return self.one('SELECT * FROM customers WHERE id=?', (customer_id,))

    def find_by_phone(self, phone):
        return self.one('SELECT * FROM customers WHERE phone=? ORDER BY id LIMIT 1', (phone,))

    def find_by_name(self, name):
        return self.one('SELECT * FROM customers WHERE name=? ORDER BY id LIMIT 1', (name,))

    def code_exists(self, code):
        return self.scalar('SELECT 1 FROM customers WHERE customer_code=?', (code,)) is not None

    def create(self, values):
        return self.insert('customers', values)
