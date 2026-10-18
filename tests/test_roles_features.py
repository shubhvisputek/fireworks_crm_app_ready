"""Roles, per-user data limits, and the operational features (approvals, cash closing, suppliers, backups...)."""
import itertools
import unittest

from tests.support import ServerProcess

_n = itertools.count(1)
PROFIT_KEYS = {'gross_profit', 'gross_margin', 'cogs', 'net_profit', 'inventory_cost', 'cost_price', 'profit', 'cost'}


def keys_deep(data):
    if isinstance(data, dict):
        return set(data) | set().union(*(keys_deep(v) for v in data.values())) if data else set()
    if isinstance(data, list):
        return set().union(*(keys_deep(v) for v in data)) if data else set()
    return set()


class RoleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerProcess(env={'FIREWORKS_AUTO_BACKUP': '0'}).start()
        cls.owner = cls.server.client()
        assert cls.owner.login('admin', 'admin123').status == 200
        cls.clients = {}
        for role in ('MANAGER', 'CASHIER', 'STOCK_KEEPER', 'ACCOUNTANT'):
            cls.clients[role] = cls.user(f'{role.lower()}1', role, display_name=f'{role.title()} One')
        cls.cashier2 = cls.user('cashier2', 'CASHIER')

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    @classmethod
    def user(cls, username, role, password='password12', **extra):
        res = cls.owner.post('/api/users', {'username': username, 'password': password, 'role': role, **extra})
        assert res.status == 200, res.body
        client = cls.server.client()
        assert client.login(username, password).status == 200
        client.user_id = res.json()['id']
        return client

    @property
    def manager(self):
        return self.clients['MANAGER']

    @property
    def cashier(self):
        return self.clients['CASHIER']

    def product(self, price=100, stock=50, **extra):
        sku = f'R-{next(_n):04d}'
        res = self.owner.post('/api/products', {'sku': sku, 'name': f'Item {sku}', 'unit_price': price, 'opening_stock': stock,
                                                'cost_price': price * 0.6, **extra})
        self.assertEqual(res.status, 200, res.body)
        return res.json()['id']

    def sell(self, client, pid, qty=1, price=100, **extra):
        payments = extra.pop('payments', [{'mode': 'Cash', 'amount': price * qty - extra.get('discount', 0)}])
        return client.post('/api/sales', {'items': [{'product_id': pid, 'qty': qty}], 'payments': payments, **extra})


class RoleMatrixTests(RoleTestCase):
    def test_catalog_and_presets(self):
        catalog = self.owner.get('/api/users/catalog').json()
        roles = {r['role']: set(r['permissions']) for r in catalog['roles']}
        self.assertEqual(catalog['assignable_roles'], ['MANAGER', 'CASHIER', 'STOCK_KEEPER', 'ACCOUNTANT', 'STAFF'])
        for role, client in self.clients.items():
            with self.subTest(role=role):
                me = client.get('/api/me').json()['user']
                self.assertEqual(set(me['permissions']), roles[role])
                self.assertEqual(me['name'], f'{role.title()} One')

    def access(self, client, method, path, body=None):
        return (client.get(path) if method == 'GET' else client.post(path, body or {})).status

    def test_route_access_by_role(self):
        expectations = {
            # path: roles allowed (owner always)
            ('GET', '/api/dashboard'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/analytics'): {'MANAGER', 'ACCOUNTANT'},
            ('GET', '/api/invoices'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/customers'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/dues'): {'MANAGER', 'ACCOUNTANT'},
            ('GET', '/api/purchases'): {'MANAGER', 'STOCK_KEEPER'},
            ('GET', '/api/suppliers'): {'MANAGER', 'STOCK_KEEPER', 'ACCOUNTANT'},
            ('GET', '/api/reorder-plan'): {'MANAGER', 'STOCK_KEEPER'},
            ('GET', '/api/expenses'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/recurring-expenses'): {'ACCOUNTANT'},
            ('GET', '/api/cash-closing/summary'): {'MANAGER', 'CASHIER'},
            ('GET', '/api/cash-closings'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/export/sales.xlsx'): {'MANAGER', 'ACCOUNTANT'},
            ('GET', '/api/backup'): set(),
            ('GET', '/api/backups'): set(),
            ('GET', '/api/audit'): set(),
            ('GET', '/api/settings'): set(),
            ('GET', '/api/users'): set(),
            ('GET', '/api/categories'): {'MANAGER', 'STOCK_KEEPER'},
        }
        for (method, path), allowed in expectations.items():
            for role, client in self.clients.items():
                with self.subTest(path=path, role=role):
                    status = self.access(client, method, path)
                    self.assertEqual(status == 200, role in allowed, f'{role} {path} -> {status}')
            self.assertEqual(self.access(self.owner, method, path), 200, path)

    def test_write_access_by_role(self):
        pid = self.product()
        for role, client in self.clients.items():
            with self.subTest(role=role, action='pricing'):
                status = client.post('/api/pricing', {'product_id': pid, 'unit_price': 100}).status
                self.assertEqual(status, 403, role)  # only the owner changes prices
            with self.subTest(role=role, action='billing'):
                self.assertEqual(self.sell(client, pid).status == 200, role in ('MANAGER', 'CASHIER'), role)
            with self.subTest(role=role, action='add product'):
                res = client.post('/api/products', {'sku': f'W-{role}', 'name': 'x', 'unit_price': 1})
                self.assertEqual(res.status == 200, role in ('MANAGER', 'STOCK_KEEPER'), role)

    def test_profit_hidden_without_permission(self):
        pid = self.product(price=100)
        self.sell(self.owner, pid)
        for role in ('MANAGER', 'CASHIER'):
            with self.subTest(role=role):
                self.assertFalse(keys_deep(self.clients[role].get('/api/dashboard').json()) & PROFIT_KEYS)
        self.assertFalse(keys_deep(self.manager.get('/api/analytics?preset=today').json()) & PROFIT_KEYS)
        self.assertFalse(keys_deep(self.manager.get(f'/api/products/{pid}').json()) & PROFIT_KEYS)
        self.assertIn('gross_profit', self.clients['ACCOUNTANT'].get('/api/analytics?preset=today').json()['kpi'])
        self.assertIn('cost_price', self.owner.get(f'/api/products/{pid}').json()['product'])

    def test_cashier_sees_only_own_bills(self):
        pid = self.product()
        mine = self.sell(self.cashier, pid).json()['invoice_id']
        theirs = self.sell(self.cashier2, pid).json()['invoice_id']
        listed = [i['id'] for i in self.cashier.get('/api/invoices?start=1900-01-01&end=2999-12-31').json()]
        self.assertIn(mine, listed)
        self.assertNotIn(theirs, listed)
        self.assertEqual(self.cashier.get(f'/api/invoices/{theirs}').status, 404)
        self.assertEqual(self.cashier.get(f'/api/invoice-pdf/{theirs}').status, 404)
        self.assertEqual(self.cashier.get(f'/api/invoice-pdf/{mine}').status, 200)
        self.assertIn(theirs, [i['id'] for i in self.manager.get('/api/invoices?start=1900-01-01&end=2999-12-31').json()])

    def test_held_bills_and_expenses_are_private(self):
        pid = self.product()
        held = self.cashier2.post('/api/held-bills', {'items': [{'product_id': pid, 'qty': 1}]}).json()['id']
        self.assertNotIn(held, [h['id'] for h in self.cashier.get('/api/held-bills').json()])
        self.assertEqual(self.cashier.post(f'/api/held-bills/resume/{held}').status, 404)
        self.assertIn(held, [h['id'] for h in self.manager.get('/api/held-bills').json()])
        self.cashier2.post('/api/expenses', {'category': 'Tea', 'amount': 30})
        self.cashier.post('/api/expenses', {'category': 'Snacks', 'amount': 40})
        mine = {e['category'] for e in self.cashier.get('/api/expenses?start=1900-01-01&end=2999-12-31').json()}
        self.assertIn('Snacks', mine)
        self.assertNotIn('Tea', mine)

    def test_custom_permissions_and_session_refresh(self):
        client = self.user('custom1', 'CASHIER')
        cashier_preset = set(client.get('/api/me').json()['user']['permissions'])
        res = self.owner.post(f'/api/users/{client.user_id}', {'permissions': sorted(cashier_preset | {'analytics.view'})})
        self.assertEqual(res.status, 200, res.body)
        self.assertTrue(res.json()['user']['custom_permissions'])
        self.assertFalse(client.get('/api/me').json()['authenticated'])  # changed access ends open sessions
        client.login('custom1', 'password12')
        self.assertEqual(client.get('/api/analytics').status, 200)
        self.owner.post(f'/api/users/{client.user_id}', {'permissions': None})  # back to the role preset
        client.login('custom1', 'password12')
        self.assertEqual(client.get('/api/analytics').status, 403)

    def test_role_change_and_owner_protection(self):
        client = self.user('promote1', 'CASHIER')
        self.owner.post(f'/api/users/{client.user_id}', {'role': 'MANAGER', 'display_name': 'Promoted'})
        client.login('promote1', 'password12')
        me = client.get('/api/me').json()['user']
        self.assertEqual((me['role'], me['name']), ('MANAGER', 'Promoted'))
        owner_id = self.owner.get('/api/me').json()['user']['id']
        self.assertEqual(self.owner.post(f'/api/users/{owner_id}', {'role': 'CASHIER'}).status, 400)
        self.assertEqual(self.owner.post('/api/users', {'username': 'boss2', 'password': 'password12', 'role': 'OWNER'}).status, 400)
        self.assertEqual(self.owner.post(f'/api/users/{owner_id}', {'display_name': 'Shop Owner'}).status, 200)

    def test_reset_password(self):
        client = self.user('forgetful', 'CASHIER')
        self.assertEqual(self.owner.post(f'/api/users/{client.user_id}/password', {'password': 'short'}).status, 400)
        self.assertEqual(self.owner.post(f'/api/users/{client.user_id}/password', {'password': 'brandnew123'}).status, 200)
        self.assertFalse(client.get('/api/me').json()['authenticated'])
        self.assertEqual(self.server.client().login('forgetful', 'brandnew123').status, 200)

    def test_display_name_shown_as_billed_by(self):
        pid = self.product()
        sale = self.sell(self.cashier, pid).json()
        inv = self.owner.get(f"/api/invoices/{sale['invoice_id']}").json()['invoice']
        self.assertEqual(inv['billed_by_name'], 'Cashier One')


class DiscountApprovalTests(RoleTestCase):
    def test_large_discount_needs_manager(self):
        pid = self.product(price=100)
        small = self.sell(self.cashier, pid, discount=10)
        self.assertEqual(small.status, 200, small.body)
        big = self.sell(self.cashier, pid, discount=20)
        self.assertEqual(big.status, 400)
        self.assertEqual(big.json()['code'], 'DISCOUNT_APPROVAL_REQUIRED')
        self.assertEqual(big.json()['max_discount_pct'], 10)
        wrong = self.sell(self.cashier, pid, discount=20, approval={'username': 'manager1', 'password': 'nope'})
        self.assertIn('incorrect', wrong.json()['error'])
        not_allowed = self.sell(self.cashier, pid, discount=20, approval={'username': 'cashier2', 'password': 'password12'})
        self.assertIn('not allowed', not_allowed.json()['error'])
        ok = self.sell(self.cashier, pid, discount=20, approval={'username': 'manager1', 'password': 'password12'})
        self.assertEqual(ok.status, 200, ok.body)
        inv = self.owner.get(f"/api/invoices/{ok.json()['invoice_id']}").json()['invoice']
        self.assertEqual(inv['discount_approved_by_name'], 'Manager One')
        self.assertEqual(self.sell(self.manager, pid, discount=50).status, 200)  # managers may give any discount


class CashClosingTests(RoleTestCase):
    def test_close_drawer(self):
        pid = self.product(price=100)
        self.sell(self.cashier, pid, payments=[{'mode': 'Cash', 'amount': 100}])
        self.sell(self.cashier, pid, payments=[{'mode': 'UPI', 'amount': 60}, {'mode': 'Cash', 'amount': 40}])
        self.sell(self.cashier, pid, payments=[{'mode': 'Credit', 'amount': 100}])
        self.cashier.post('/api/expenses', {'category': 'Tea', 'amount': 15, 'payment_mode': 'Cash'})
        summary = self.cashier.get('/api/cash-closing/summary').json()
        modes = {m['mode']: m['amount'] for m in summary['modes']}
        self.assertEqual(modes, {'Cash': 140, 'UPI': 60})
        self.assertEqual(summary['expected_cash'], 125)
        res = self.cashier.post('/api/cash-closing', {'counted_cash': 120, 'counted': {'UPI': 60}, 'notes': 'short by 5'})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()['difference'], -5)
        self.assertEqual(self.cashier.get('/api/cash-closing/summary').json()['modes'], [])
        self.assertEqual(self.cashier.post('/api/cash-closing', {'counted_cash': 0}).status, 400)
        own = self.cashier.get('/api/cash-closings').json()
        self.assertEqual([c['difference'] for c in own], [-5])
        self.assertIn('Cashier One', [c['user_name'] for c in self.manager.get('/api/cash-closings').json()])
        self.assertEqual(self.cashier2.get('/api/cash-closings').json(), [])


class AuditAndDuesTests(RoleTestCase):
    def test_audit_log(self):
        pid = self.product()
        self.sell(self.cashier, pid)
        self.owner.post(f'/api/users/{self.cashier2.user_id}/password', {'password': 'secretpass99'})
        data = self.owner.get('/api/audit?start=1900-01-01&end=2999-12-31').json()
        actions = [e['action'] for e in data['entries']]
        self.assertIn('Invoice finalized', actions)
        self.assertIn('Password reset', actions)
        self.assertNotIn('secretpass99', str(data))
        self.assertIn('INVOICE', data['entity_types'])
        filtered = self.owner.get('/api/audit?start=1900-01-01&end=2999-12-31&entity=USER').json()['entries']
        self.assertTrue(filtered and all(e['entity_type'] == 'USER' for e in filtered))

    def test_dues_list_and_collection(self):
        pid = self.product(price=100)
        sale = self.sell(self.owner, pid, customer_name='Due Customer', customer_phone='9123456780',
                         payments=[{'mode': 'Cash', 'amount': 30}, {'mode': 'Credit', 'amount': 70}]).json()
        dues = self.clients['ACCOUNTANT'].get('/api/dues').json()
        entry = next(c for c in dues['customers'] if c['name'] == 'Due Customer')
        self.assertEqual((entry['total_due'], entry['phone']), (70, '9123456780'))
        self.assertEqual(self.clients['ACCOUNTANT'].post('/api/payments', {'invoice_id': sale['invoice_id'], 'amount': 70}).status, 200)
        self.assertNotIn('Due Customer', [c['name'] for c in self.owner.get('/api/dues').json()['customers']])


class ProductFeatureTests(RoleTestCase):
    def test_barcode_and_product_edit(self):
        pid = self.product(barcode='8901234567890')
        self.assertEqual(self.owner.post('/api/products', {'sku': 'DUPBC', 'name': 'x', 'unit_price': 1, 'barcode': '8901234567890'}).status, 400)
        self.assertEqual([p['id'] for p in self.cashier.get('/api/products?q=8901234567890').json()], [pid])
        res = self.manager.post(f'/api/products/{pid}', {'name': 'Renamed', 'barcode': '111', 'cost_price': 1})
        self.assertEqual(res.status, 200, res.body)
        detail = self.owner.get(f'/api/products/{pid}').json()['product']
        self.assertEqual((detail['name'], detail['barcode']), ('Renamed', '111'))
        self.assertEqual(detail['cost_price'], 60)  # manager cannot change cost (no profit permission)

    def test_thermal_receipt(self):
        pid = self.product()
        sale = self.sell(self.cashier, pid).json()
        res = self.cashier.get(f"/api/invoice-receipt/{sale['invoice_id']}")
        self.assertEqual(res.status, 200)
        self.assertIn(b'/MediaBox [ 0 0 226.7717', res.body)  # 80 mm wide

    def test_storage_limit(self):
        self.owner.post('/api/settings', {'settings': {'storage_limit_kg': 10}})
        pid = self.product(stock=0, explosive_kg=1)
        self.assertEqual(self.owner.post('/api/purchases', {'items': [{'product_id': pid, 'qty': 8}]}).status, 200)
        over = self.owner.post('/api/purchases', {'items': [{'product_id': pid, 'qty': 5}]})
        self.assertEqual(over.status, 400)
        self.assertEqual((over.json()['code'], over.json()['after_kg'], over.json()['limit_kg']), ('STORAGE_LIMIT', 13, 10))
        self.assertEqual(self.owner.post('/api/purchases', {'items': [{'product_id': pid, 'qty': 5}], 'allow_over_limit': True}).status, 200)
        storage = self.owner.get('/api/dashboard').json()['storage']
        self.assertTrue(storage['over'])
        self.owner.post('/api/settings', {'settings': {'storage_limit_kg': 0}})


class SupplierTests(RoleTestCase):
    def test_supplier_ledger_and_payments(self):
        keeper = self.clients['STOCK_KEEPER']
        supplier_id = keeper.post('/api/suppliers', {'name': 'Sivakasi Traders', 'phone': '9000011111'}).json()['id']
        self.assertEqual(keeper.post('/api/suppliers', {'name': 'sivakasi traders'}).status, 400)
        pid = self.product(stock=0)
        self.assertEqual(keeper.post('/api/purchases', {'supplier_id': supplier_id, 'items': [{'product_id': pid, 'qty': 10, 'cost_price': 50}]}).status, 200)
        ledger = keeper.get(f'/api/suppliers/{supplier_id}').json()
        self.assertEqual(ledger['supplier']['balance'], 500)
        paid = keeper.post(f'/api/suppliers/{supplier_id}/payments', {'amount': 200, 'mode': 'UPI'})
        self.assertEqual(paid.json()['balance'], 300)
        keeper.post('/api/purchases', {'supplier_name': 'New Wholesaler', 'items': [{'product_id': pid, 'qty': 1, 'cost_price': 10}]})
        names = {s['name']: s for s in keeper.get('/api/suppliers').json()}
        self.assertEqual(names['New Wholesaler']['balance'], 10)


class ReorderPlanTests(RoleTestCase):
    def test_reorder_plan(self):
        pid = self.product(price=10, stock=15)
        for _ in range(2):
            self.sell(self.owner, pid, qty=5, price=10)
        plan = self.owner.get('/api/reorder-plan?start=1900-01-01&end=2999-12-31&growth=10').json()
        row = next(r for r in plan['rows'] if r['product_id'] == pid)
        self.assertEqual((row['sold_last_season'], row['stock'], row['target'], row['suggested']), (10, 5, 11, 6))
        self.assertEqual(row['cost'], 36)
        hidden = self.manager.get('/api/reorder-plan?start=1900-01-01&end=2999-12-31').json()
        self.assertFalse(keys_deep(hidden) & {'cost', 'total_cost'})


class SettingsTests(RoleTestCase):
    def test_new_settings_validation(self):
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'max_discount_pct': 150}}).status, 400)
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'receipt_format': 'A5'}}).status, 400)
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'receipt_format': '80mm', 'backup_keep_days': 7}}).status, 200)
        limits = self.cashier.get('/api/me').json()['limits']
        self.assertEqual((limits['receipt_format'], limits['max_discount_pct']), ('80mm', 10))
        self.owner.post('/api/settings', {'settings': {'receipt_format': 'A4'}})


class BackupTests(RoleTestCase):
    def test_backup_download_and_restore(self):
        self.assertEqual(self.manager.get('/api/backups').status, 403)
        name = self.owner.post('/api/backups').json()['name']
        self.assertIn(name, [b['name'] for b in self.owner.get('/api/backups').json()['backups']])
        file = self.owner.get('/api/backups/download?name=' + name)
        self.assertTrue(file.body.startswith(b'SQLite format 3'))
        self.assertEqual(self.owner.get('/api/backups/download?name=../fireworks.db').status, 404)
        pid = self.product()
        res = self.owner.post('/api/backups/restore', {'name': name})
        self.assertEqual(res.status, 200, res.body)
        self.assertTrue(res.json()['relogin'])
        self.assertTrue(res.json()['safety_backup'].endswith('-prerestore.sqlite'))
        self.assertFalse(self.owner.get('/api/me').json()['authenticated'])
        self.owner.login('admin', 'admin123')
        self.assertEqual(self.owner.get(f'/api/products/{pid}').status, 404)  # product added after the backup is gone
        junk = self.owner.upload('/api/backups/restore', {}, 'junk.sqlite', b'not a database')
        self.assertEqual(junk.status, 400)
        uploaded = self.owner.upload('/api/backups/restore', {}, name, file.body)
        self.assertEqual(uploaded.status, 200, uploaded.body)


if __name__ == '__main__':
    unittest.main()
