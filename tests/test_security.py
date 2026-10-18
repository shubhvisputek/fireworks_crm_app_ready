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

    @staticmethod
    def cookies(res, name):
        values = res.headers.get('Set-Cookie', [])
        return next((c.split(';')[0] for c in values if c.startswith(name + '=')), None)

    def login(self, username, password, ip='10.0.0.1', device_cookie=None):
        return self.call('POST', '/api/login', {'username': username, 'password': password}, ip=ip,
                         headers={'Cookie': device_cookie} if device_cookie else None)

    def test_wrong_passwords_never_lock_other_users(self):
        """Someone mistyping (or guessing) one account, on the same computer, must not lock anyone else."""
        self.call('POST', '/api/users', {'username': 'cashierA', 'password': 'goodpass99', 'role': 'CASHIER'},
                  headers={'Cookie': self.cookies(self.login('admin', 'admin123'), 'fw_session'), 'Origin': 'http://localhost'})
        for i in range(40):
            self.login('cashierA', f'wrong{i}', ip='192.168.1.50')
        self.assertEqual(self.login('cashierA', 'goodpass99', ip='192.168.1.50').status, 429, 'that account is paused on that computer')
        self.assertEqual(self.login('admin', 'admin123', ip='192.168.1.50').status, 200, 'other users on the same computer can sign in')
        self.assertEqual(self.login('cashierA', 'goodpass99', ip='192.168.1.60').status, 200, 'and on other computers too')

    def test_trusted_browser_not_locked_by_guessing_in_another_window(self):
        """The owner's normal browser keeps working while someone in an incognito window guesses the password."""
        owner_browser = self.cookies(self.login('admin', 'admin123', ip='192.168.1.10'), 'fw_device')
        self.assertTrue(owner_browser)
        for i in range(15):
            self.login('admin', f'guess{i}', ip='192.168.1.10')  # incognito window: no device cookie
        self.assertEqual(self.login('admin', 'admin123', ip='192.168.1.10').status, 429, 'the incognito window is paused')
        self.assertEqual(self.login('admin', 'admin123', ip='192.168.1.10', device_cookie=owner_browser).status, 200,
                         'the browser the owner normally uses still signs in')

    def test_a_trusted_browser_is_paused_by_its_own_mistakes(self):
        device = self.cookies(self.login('admin', 'admin123'), 'fw_device')
        for i in range(10):
            self.login('admin', f'typo{i}', device_cookie=device)
        self.assertEqual(self.login('admin', 'admin123', device_cookie=device).status, 429)

    def test_device_cookie_of_another_user_does_not_help(self):
        self.call('POST', '/api/users', {'username': 'cashierB', 'password': 'goodpass99', 'role': 'CASHIER'},
                  headers={'Cookie': self.cookies(self.login('admin', 'admin123', ip='10.9.9.9'), 'fw_session'), 'Origin': 'http://localhost'})
        attacker_device = self.cookies(self.login('cashierB', 'goodpass99', ip='203.0.113.5'), 'fw_device')
        for i in range(10):
            self.login('admin', f'guess{i}', ip='203.0.113.5', device_cookie=attacker_device)
        self.assertEqual(self.login('admin', 'admin123', ip='203.0.113.5', device_cookie=attacker_device).status, 429)

    def admin_headers(self):
        return {'Cookie': self.cookies(self.login('admin', 'admin123', ip='10.200.0.1'), 'fw_session'), 'Origin': 'http://localhost'}

    def test_admin_can_unlock_a_locked_user(self):
        admin = self.admin_headers()
        self.call('POST', '/api/users', {'username': 'cashierC', 'password': 'goodpass99', 'role': 'CASHIER'}, headers=admin)
        for i in range(12):
            self.login('cashierC', f'wrong{i}', ip='192.168.1.70')
        self.assertEqual(self.login('cashierC', 'goodpass99', ip='192.168.1.70').status, 429)
        users = json.loads(self.call('GET', '/api/users', headers=admin).body)
        target = next(u for u in users if u['username'] == 'cashierC')
        self.assertTrue(target['locked'], 'the Users page shows who is locked')
        self.assertFalse(next(u for u in users if u['username'] == 'admin')['locked'])
        self.assertEqual(self.call('POST', f"/api/users/{target['id']}/unlock", {}, headers=admin).status, 200)
        self.assertEqual(self.login('cashierC', 'goodpass99', ip='192.168.1.70').status, 200, 'unlocked straight away')
        users = json.loads(self.call('GET', '/api/users', headers=admin).body)
        self.assertFalse(next(u for u in users if u['username'] == 'cashierC')['locked'])

    def test_unlock_needs_manage_users(self):
        admin = self.admin_headers()
        self.call('POST', '/api/users', {'username': 'cashierD', 'password': 'goodpass99', 'role': 'CASHIER'}, headers=admin)
        cashier = {'Cookie': self.cookies(self.login('cashierD', 'goodpass99'), 'fw_session'), 'Origin': 'http://localhost'}
        self.assertEqual(self.call('POST', '/api/users/1/unlock', {}, headers=cashier).status, 403)

    def test_password_reset_also_unlocks(self):
        admin = self.admin_headers()
        self.call('POST', '/api/users', {'username': 'cashierE', 'password': 'goodpass99', 'role': 'CASHIER'}, headers=admin)
        for i in range(12):
            self.login('cashierE', f'wrong{i}', ip='192.168.1.80')
        uid = next(u['id'] for u in json.loads(self.call('GET', '/api/users', headers=admin).body) if u['username'] == 'cashierE')
        self.call('POST', f'/api/users/{uid}/password', {'password': 'newgoodpass77'}, headers=admin)
        self.assertEqual(self.login('cashierE', 'newgoodpass77', ip='192.168.1.80').status, 200)

    def test_lockout_can_be_switched_off(self):
        admin = self.admin_headers()
        res = self.call('POST', '/api/settings', {'settings': {'login_lockout': False}}, headers=admin)
        self.assertEqual(res.status, 200, res.body)
        for i in range(30):
            self.assertEqual(self.login('admin', f'wrong{i}', ip='192.168.1.90').status, 401, 'wrong passwords are still refused')
        self.assertEqual(self.login('admin', 'admin123', ip='192.168.1.90').status, 200, 'but nobody is ever locked out')
        self.call('POST', '/api/settings', {'settings': {'login_lockout': True}}, headers=admin)
        for i in range(10):
            self.login('admin', f'again{i}', ip='192.168.1.91')
        self.assertEqual(self.login('admin', 'admin123', ip='192.168.1.91').status, 429, 'switching it back on restores the protection')

    def test_unknown_usernames_take_as_long_as_wrong_passwords(self):
        def timed(username):
            start = time.perf_counter()
            self.call('POST', '/api/login', {'username': username, 'password': 'wrongpass'}, ip=f'10.1.{len(username)}.1')
            return time.perf_counter() - start
        known, unknown = timed('admin'), timed('no-such-user-here')
        self.assertGreater(unknown, known * 0.4, 'unknown usernames must also run the password hash')

    def test_restore_signs_everyone_out(self):
        cookie = self.cookies(self.login('admin', 'admin123'), 'fw_session')
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
