"""Smaller repositories: held bills, purchases, expenses, settings, audit, sequences, backup."""
import json

from crm.repositories.base import Repository


class HeldBillRepository(Repository):
    def create(self, values):
        return self.insert('held_bills', values)

    def list(self):
        return self.all('SELECT * FROM held_bills ORDER BY created_at DESC, id DESC')

    def get(self, held_id):
        return self.one('SELECT * FROM held_bills WHERE id=?', (held_id,))

    def delete(self, held_id):
        return self.execute('DELETE FROM held_bills WHERE id=?', (held_id,)).rowcount


class PurchaseRepository(Repository):
    def create(self, values):
        return self.insert('purchases', values)

    def add_item(self, values):
        return self.insert('purchase_items', values)

    def set_totals(self, purchase_id, subtotal, total):
        self.execute('UPDATE purchases SET subtotal=?, total=? WHERE id=?', (subtotal, total, purchase_id))

    def list(self, limit=200):
        return self.all('SELECT p.*, s.name AS supplier FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC LIMIT ?', (limit,))


class ExpenseRepository(Repository):
    def create(self, values):
        return self.insert('expenses', values)

    def list(self, start, end):
        return self.all('SELECT * FROM expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date DESC, id DESC', (start, end))

    def total(self, start, end):
        return self.scalar('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE expense_date BETWEEN ? AND ?', (start, end), default=0)

    def create_recurring(self, values):
        return self.insert('recurring_expenses', values)

    def list_recurring(self):
        return self.all('SELECT * FROM recurring_expenses ORDER BY id DESC')


class SettingsRepository(Repository):
    def settings(self):
        return json.loads(self.scalar('SELECT data_json FROM business_settings WHERE id=1', default='{}'))

    def save_settings(self, data):
        self.execute('UPDATE business_settings SET data_json=? WHERE id=1', (json.dumps(data),))

    def targets(self):
        return self.one('SELECT * FROM targets WHERE id=1') or {}

    def save_targets(self, targets):
        self.execute('UPDATE targets SET daily=?, weekly=?, monthly=?, seasonal=?, season_start=?, season_end=? WHERE id=1',
                     (targets['daily'], targets['weekly'], targets['monthly'], targets['seasonal'], targets['season_start'], targets['season_end']))


class AuditRepository(Repository):
    def log(self, user_id, action, entity_type, entity_id, at, previous=None, new=None):
        self.insert('audit_logs', {
            'user_id': user_id, 'action': action, 'entity_type': entity_type, 'entity_id': entity_id,
            'previous_json': json.dumps(previous, default=str) if previous else None,
            'new_json': json.dumps(new, default=str) if new else None, 'created_at': at,
        })


class SequenceRepository(Repository):
    def next(self, key):
        self.execute('INSERT INTO sequence(key, value) VALUES(?, 1) ON CONFLICT(key) DO UPDATE SET value=value+1', (key,))
        return self.scalar('SELECT value FROM sequence WHERE key=?', (key,))


class BackupRepository(Repository):
    def dump(self):
        tables = [row['name'] for row in self.all("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table: self.all(f'SELECT * FROM "{table}"') for table in tables}
