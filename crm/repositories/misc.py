"""Smaller repositories: held bills, purchases, expenses, settings, audit, sequences, backup."""
import json

from crm.repositories.base import Repository


class HeldBillRepository(Repository):
    def create(self, values):
        return self.insert('held_bills', values)

    def list(self, user_id=None):
        if user_id:
            return self.all('SELECT * FROM held_bills WHERE user_id=? ORDER BY created_at DESC, id DESC', (user_id,))
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

    def list(self, start, end, user_id=None):
        if user_id:
            return self.all('SELECT * FROM expenses WHERE expense_date BETWEEN ? AND ? AND user_id=? ORDER BY expense_date DESC, id DESC',
                            (start, end, user_id))
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


class SessionRepository(Repository):
    def revoke(self, sid, expires_at, now):
        self.execute('INSERT OR IGNORE INTO revoked_sessions(sid, expires_at) VALUES(?, ?)', (sid, expires_at))
        self.execute('DELETE FROM revoked_sessions WHERE expires_at < ?', (now,))

    def is_revoked(self, sid):
        return self.scalar('SELECT 1 FROM revoked_sessions WHERE sid=?', (sid,)) is not None


class SequenceRepository(Repository):
    def next(self, key):
        self.execute('INSERT INTO sequence(key, value) VALUES(?, 1) ON CONFLICT(key) DO UPDATE SET value=value+1', (key,))
        return self.scalar('SELECT value FROM sequence WHERE key=?', (key,))


class BackupRepository(Repository):
    def dump(self):
        tables = [row['name'] for row in self.all("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {table: self.all(f'SELECT * FROM "{table}"') for table in tables}


class SupplierRepository(Repository):
    BALANCE_SQL = '''COALESCE((SELECT SUM(total) FROM purchases p WHERE p.supplier_id=s.id), 0)
                   - COALESCE((SELECT SUM(amount) FROM supplier_payments sp WHERE sp.supplier_id=s.id), 0)'''

    def list(self):
        return self.all(f'''SELECT s.*, COALESCE((SELECT SUM(total) FROM purchases p WHERE p.supplier_id=s.id), 0) AS purchased,
                                   COALESCE((SELECT SUM(amount) FROM supplier_payments sp WHERE sp.supplier_id=s.id), 0) AS paid,
                                   ({self.BALANCE_SQL}) AS balance
                            FROM suppliers s ORDER BY s.name''')

    def get(self, supplier_id):
        return self.one(f'SELECT s.*, ({self.BALANCE_SQL}) AS balance FROM suppliers s WHERE s.id=?', (supplier_id,))

    def find_by_name(self, name):
        return self.one('SELECT * FROM suppliers WHERE lower(name)=lower(?) ORDER BY id LIMIT 1', (name,))

    def create(self, values):
        return self.insert('suppliers', values)

    def purchases(self, supplier_id):
        return self.all('SELECT * FROM purchases WHERE supplier_id=? ORDER BY purchase_date DESC, id DESC', (supplier_id,))

    def payments(self, supplier_id):
        return self.all('SELECT * FROM supplier_payments WHERE supplier_id=? ORDER BY payment_date DESC, id DESC', (supplier_id,))

    def add_payment(self, values):
        return self.insert('supplier_payments', values)


class CashClosingRepository(Repository):
    def last_for_user(self, user_id):
        return self.one('SELECT * FROM cash_closings WHERE user_id=? ORDER BY closed_at DESC, id DESC LIMIT 1', (user_id,))

    def create(self, values):
        return self.insert('cash_closings', values)

    def list(self, user_id=None, limit=200):
        own = 'WHERE c.user_id=?' if user_id else ''
        params = ((user_id,) if user_id else ()) + (limit,)
        return self.all(f'''SELECT c.*, COALESCE(u.display_name, u.username) AS user_name FROM cash_closings c
                            JOIN users u ON u.id=c.user_id {own} ORDER BY c.closed_at DESC, c.id DESC LIMIT ?''', params)

    def payments_by_mode(self, user_id, since, until):
        """Money this user took on bills (excluding Credit), by payment mode, in a time window.
        Bills deleted (or replaced by an edit) are left out: that money went back to the customer."""
        return self.all('''SELECT p.mode, ROUND(SUM(p.amount), 2) AS amount, COUNT(DISTINCT p.invoice_id) AS bills
                           FROM payments p JOIN invoices i ON i.id=p.invoice_id
                           WHERE p.user_id=? AND p.created_at>? AND p.created_at<=? AND upper(p.mode)<>'CREDIT'
                                 AND i.status<>'VOID'
                           GROUP BY p.mode ORDER BY p.mode''', (user_id, since, until))

    def voided_earlier_payments(self, user_id, since, until):
        """Payments this user took before the window on bills deleted inside it: handed back now, by mode."""
        return self.all('''SELECT p.mode, ROUND(SUM(p.amount), 2) AS amount, COUNT(DISTINCT p.invoice_id) AS bills
                           FROM payments p JOIN invoices i ON i.id=p.invoice_id
                           WHERE p.user_id=? AND p.created_at<=? AND i.status='VOID' AND i.voided_at>? AND i.voided_at<=?
                                 AND upper(p.mode)<>'CREDIT'
                           GROUP BY p.mode ORDER BY p.mode''', (user_id, since, since, until))

    def refunds(self, user_id, since, until):
        return self.scalar('SELECT COALESCE(SUM(total_refund), 0) FROM returns WHERE user_id=? AND created_at>? AND created_at<=?',
                           (user_id, since, until), default=0)

    def cash_expenses(self, user_id, since, until):
        return self.scalar("""SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id=? AND created_at>? AND created_at<=?
                              AND upper(payment_mode)='CASH'""", (user_id, since, until), default=0)


class AuditQueryRepository(Repository):
    def search(self, start, end, user_id=None, entity_type=None, text=None, limit=300):
        where, params = ['date(a.created_at) BETWEEN ? AND ?'], [start, end]
        if user_id:
            where.append('a.user_id=?')
            params.append(user_id)
        if entity_type:
            where.append('a.entity_type=?')
            params.append(entity_type)
        if text:
            where.append('(a.action LIKE ? OR a.new_json LIKE ? OR a.previous_json LIKE ?)')
            params += [f'%{text}%'] * 3
        return self.all(f'''SELECT a.*, COALESCE(u.display_name, u.username) AS user_name FROM audit_logs a
                            LEFT JOIN users u ON u.id=a.user_id WHERE {' AND '.join(where)}
                            ORDER BY a.created_at DESC, a.id DESC LIMIT ?''', params + [limit])

    def entity_types(self):
        return [row['entity_type'] for row in self.all('SELECT DISTINCT entity_type FROM audit_logs WHERE entity_type IS NOT NULL ORDER BY 1')]
