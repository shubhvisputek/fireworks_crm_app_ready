"""Regression tests for the security review: each test pins one fixed weakness."""
import json
import os
import shutil
import tempfile
import time
import unittest

from crm.config import Config
from crm.errors import ValidationError
from crm.security import LoginThrottle
from crm.web.app import Application
from crm.web.http import Request, Response
from tests.test_roles_features import PROFIT_KEYS, RoleTestCase, keys_deep


class ThrottleTests(unittest.TestCase):
    def test_flooding_junk_usernames_does_not_reset_a_real_account(self):
        throttle = LoginThrottle(10, 900)
        throttle.MAX_TRACKED = 200
        for _ in range(9):
            throttle.record_failure('login-user:admin')
        for i in range(1000):
            throttle.record_failure(f'login-user:junk{i}')
        throttle.record_failure('login-user:admin')
        self.assertTrue(throttle.is_blocked('login-user:admin'))
        self.assertLessEqual(len(throttle._failures), 200)


class InProcessTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='fwcrm-sec-')
        self.app = Application(Config(db_path=os.path.join(self.tmp, 'db.sqlite'), secret_path=os.path.join(self.tmp, '.secret'),
                                      static_dir=self.tmp, backup_dir=os.path.join(self.tmp, 'backups')))
        self.app.initialize()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, body=None, ip='10.0.0.1', headers=None):
        raw = json.dumps(body).encode() if body is not None else b''
        hdrs = {'Host': 'localhost', 'Content-Type': 'application/json', 'Content-Length': str(len(raw)), **(headers or {})}
        chunks = [raw]
        return self.app.handle(Request(method, path, hdrs, lambda n: chunks.pop() if chunks else b'', 1 << 20, client_ip=ip))

    def test_one_attacker_cannot_lock_the_owner_out_for_everyone(self):
        for i in range(12):
            self.call('POST', '/api/login', {'username': 'admin', 'password': f'wrong{i}'}, ip='203.0.113.9')
        self.assertEqual(self.call('POST', '/api/login', {'username': 'admin', 'password': 'nope'}, ip='203.0.113.9').status, 429)
        self.assertEqual(self.call('POST', '/api/login', {'username': 'admin', 'password': 'admin123'}, ip='192.168.1.20').status, 200)

    def test_one_address_cannot_guess_many_accounts(self):
        for i in range(30):
            self.call('POST', '/api/login', {'username': f'user{i}', 'password': 'x'}, ip='198.51.100.7')
        self.assertEqual(self.call('POST', '/api/login', {'username': 'admin', 'password': 'admin123'}, ip='198.51.100.7').status, 429)

    def test_unknown_usernames_take_as_long_as_wrong_passwords(self):
        def timed(username):
            start = time.perf_counter()
            self.call('POST', '/api/login', {'username': username, 'password': 'wrongpass'}, ip=f'10.1.{len(username)}.1')
            return time.perf_counter() - start
        known, unknown = timed('admin'), timed('no-such-user-here')
        self.assertGreater(unknown, known * 0.4, 'unknown usernames must also run the password hash')

    def test_restore_signs_everyone_out(self):
        login = self.call('POST', '/api/login', {'username': 'admin', 'password': 'admin123'})
        cookie = login.headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.call('GET', '/api/me', headers={'Cookie': cookie}).status, 200)
        name = self.app.backups.create('manual')
        res = self.call('POST', '/api/backups/restore', {'name': name}, headers={'Cookie': cookie, 'Origin': 'http://localhost'})
        self.assertEqual(res.status, 200, res.body)
        me = json.loads(self.call('GET', '/api/me', headers={'Cookie': cookie}).body)
        self.assertFalse(me['authenticated'], 'cookies issued before a restore stop working')


class AccessTests(RoleTestCase):
    def test_manage_users_cannot_take_over_the_owner(self):
        owner_id = self.owner.get('/api/me').json()['user']['id']
        helper = self.user('helper1', 'MANAGER')
        preset = set(self.owner.get('/api/users/catalog').json()['roles'][1]['permissions'])
        self.assertEqual(self.owner.post(f'/api/users/{helper.user_id}', {'permissions': sorted(preset | {'users.manage'})}).status, 200)
        helper = self.server.client()
        helper.login('helper1', 'password12')
        self.assertEqual(helper.post(f'/api/users/{owner_id}/password', {'password': 'takeover123'}).status, 403)
        self.assertEqual(helper.post(f'/api/users/{owner_id}/status', {'active': False}).status, 403)
        me = helper.get('/api/me').json()['user']
        res = helper.post(f"/api/users/{me['id']}", {'permissions': me['permissions'] + ['backup.restore', 'profit.view']})
        self.assertEqual(res.status, 403, 'cannot raise own access')
        res = helper.post('/api/users', {'username': 'sidekick', 'password': 'goodpass99', 'role': 'ACCOUNTANT'})
        self.assertEqual(res.status, 403, 'cannot create a user with access the creator lacks (profit)')
        self.assertEqual(helper.post('/api/users', {'username': 'sidekick', 'password': 'goodpass99', 'role': 'CASHIER'}).status, 200)

    def test_restore_is_owner_only(self):
        preset = set(self.owner.get('/api/users/catalog').json()['roles'][1]['permissions'])
        restorer = self.user('restorer1', 'MANAGER')
        self.owner.post(f'/api/users/{restorer.user_id}', {'permissions': sorted(preset | {'backup.restore'})})
        restorer = self.server.client()
        restorer.login('restorer1', 'password12')
        self.assertEqual(restorer.post('/api/backups/restore', {'name': 'x.db'}).status, 403)

    def test_stock_ledger_hides_cost_without_profit_permission(self):
        pid = self.product(price=100, stock=10)
        ledger = self.manager.get(f'/api/inventory/ledger?product_id={pid}').json()
        self.assertTrue(ledger)
        self.assertFalse(keys_deep(ledger) & (PROFIT_KEYS | {'unit_cost'}))

    def test_staff_no_longer_gets_the_full_backup_and_audit_json_is_stripped(self):
        staff = self.user('legacy1', 'STAFF')
        self.assertEqual(staff.get('/api/backup').status, 403)
        preset = set(self.owner.get('/api/users/catalog').json()['roles'][1]['permissions'])
        self.owner.post(f'/api/users/{self.manager.user_id}', {'permissions': sorted(preset | {'backup.download'})})
        manager = self.server.client()
        manager.login('manager1', 'password12')
        self.product(price=100, stock=5)
        dump = manager.get('/api/backup').json()
        audit_text = json.dumps(dump.get('audit_logs'))
        self.assertNotIn('cost_price', audit_text)
        self.assertFalse(keys_deep(dump) & PROFIT_KEYS)

    def test_huge_insights_range_rejected_fast(self):
        start = time.perf_counter()
        res = self.cashier.get('/api/insights?start=0001-01-01&end=9999-12-31')
        self.assertEqual(res.status, 400)
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_cashier_dashboard_counts_only_own_bills(self):
        pid = self.product(price=100, stock=20)
        self.sell(self.owner, pid, qty=3, price=100)
        self.sell(self.cashier, pid, qty=1, price=100)
        dash = self.cashier.get('/api/dashboard').json()
        self.assertEqual(dash['scope'], 'own')
        self.assertEqual((dash['today']['sales'], dash['today']['bills']), (100, 1))
        self.assertEqual(self.owner.get('/api/dashboard').json()['scope'], 'all')

    def test_bill_actions_limited_to_visible_bills(self):
        pid = self.product(price=100, stock=20)
        bill = self.sell(self.owner, pid, qty=1, price=100, payments=[{'mode': 'Credit', 'amount': 100}]).json()['invoice_id']
        preset = set(self.owner.get('/api/users/catalog').json()['roles'][2]['permissions'])
        collector = self.user('collector1', 'CASHIER')
        self.owner.post(f'/api/users/{collector.user_id}', {'permissions': sorted(preset | {'payments.collect'})})
        collector = self.server.client()
        collector.login('collector1', 'password12')
        res = collector.post('/api/payments', {'invoice_id': bill, 'mode': 'Cash', 'amount': 100})
        self.assertEqual(res.status, 404, 'a bill this user cannot see cannot be acted on')

    def test_weak_passwords_refused(self):
        res = self.owner.post('/api/users', {'username': 'weakling', 'password': 'admin123', 'role': 'CASHIER'})
        self.assertEqual(res.status, 400)
        res = self.cashier.post('/api/password', {'current_password': 'password12', 'new_password': 'admin123'})
        self.assertEqual(res.status, 400)


class SmallFixTests(unittest.TestCase):
    def test_download_filename_cannot_inject_headers(self):
        res = Response.download('FW-1\r\nSet-Cookie: x=1".pdf', b'%PDF', 'application/pdf')
        self.assertNotIn('\r', res.headers['Content-Disposition'])
        self.assertNotIn('\n', res.headers['Content-Disposition'])
        self.assertEqual(res.headers['Content-Disposition'].count('"'), 2)

    def test_xlsx_zip_bomb_rejected_before_unpacking(self):
        import io
        import zipfile
        from crm.services.product_import import check_xlsx_size
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('xl/worksheets/sheet1.xml', b'0' * (210 * 1024 * 1024))
        self.assertLess(len(buffer.getvalue()), 1024 * 1024)
        with self.assertRaises(ValidationError):
            check_xlsx_size(buffer.getvalue())

    def test_import_mapping_must_be_an_object(self):
        from crm.services.product_import import ProductImportService
        upload = {'filename': 'p.csv', 'content': b'Product ID,Name,Price\nA1,Rocket,10\n'}
        with self.assertRaises(ValidationError):
            ProductImportService._load(ProductImportService.__new__(ProductImportService), upload, '["sku"]')

if __name__ == '__main__':
    unittest.main()
