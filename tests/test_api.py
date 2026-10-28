"""Black-box API tests. They start the real server and exercise it over HTTP."""
import http.cookiejar
import itertools
import os
import unittest

from tests.support import ServerProcess

ADMIN = ('admin', 'admin123')
_sku = itertools.count(1)


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ServerProcess().start()
        cls.admin = cls.server.client()
        assert cls.admin.login(*ADMIN).status == 200
        cls.staff = cls.make_staff('staff_' + cls.__name__.lower()[:20])

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    @classmethod
    def make_staff(cls, username, password='staffpass1', role='STAFF'):
        assert cls.admin.post('/api/users', {'username': username, 'password': password, 'role': role}).status == 200
        client = cls.server.client()
        assert client.login(username, password).status == 200
        return client

    def make_product(self, price=100, stock=50, **extra):
        sku = f'T-{next(_sku):04d}'
        res = self.admin.post('/api/products', {'sku': sku, 'name': f'Product {sku}', 'unit': 'Box', 'unit_price': price, 'opening_stock': stock, **extra})
        self.assertEqual(res.status, 200, res.body)
        return res.json()['id']

    def stock_of(self, product_id):
        return self.admin.get(f'/api/products/{product_id}').json()['stock']

    def sell(self, client, items, payments, **extra):
        return client.post('/api/sales', {'items': items, 'payments': payments, **extra})


class AuthAndSecurityTests(ApiTestCase):
    def test_me_requires_login(self):
        anon = self.server.client()
        self.assertEqual(anon.get('/api/me').json(), {'authenticated': False, 'user': None, 'limits': None})
        self.assertEqual(anon.get('/api/dashboard').status, 401)

    def test_login_failure_and_success(self):
        anon = self.server.client()
        self.assertEqual(anon.login('admin', 'wrong').status, 401)
        res = anon.login(*ADMIN)
        self.assertEqual(res.status, 200)
        user = res.json()['user']
        self.assertEqual(user['username'], 'admin')
        self.assertNotIn('password_hash', user)
        self.assertTrue(anon.get('/api/me').json()['authenticated'])

    def test_logout_clears_cookie(self):
        client = self.server.client()
        client.login(*ADMIN)
        self.assertEqual(client.post('/api/logout').status, 200)
        self.assertFalse(client.get('/api/me').json()['authenticated'])

    def test_logout_revokes_the_session_on_the_server(self):
        client = self.server.client()
        client.login(*ADMIN)
        copied = {c.name: c.value for c in client.jar}  # e.g. a cookie copied off a shared computer
        thief = self.server.client()
        for name, value in copied.items():
            thief.jar.set_cookie(http.cookiejar.Cookie(0, name, value, None, False, '127.0.0.1', False, False, '/', True,
                                                       False, None, False, None, None, {}))
        self.assertTrue(thief.get('/api/me').json()['authenticated'])
        self.assertEqual(client.post('/api/logout').status, 200)
        self.assertFalse(thief.get('/api/me').json()['authenticated'])
        self.assertEqual(thief.get('/api/products').status, 401)
        other = self.server.client()
        other.login(*ADMIN)
        self.assertTrue(other.get('/api/me').json()['authenticated'], 'other sign-ins of the same user stay valid')

    def test_unknown_host_names_rejected(self):
        # A hostile site pointing its own domain at this server (DNS rebinding) must get nowhere.
        res = self.admin.get('/api/me', headers={'Host': 'evil.example'})
        self.assertEqual(res.status, 400)
        self.assertEqual(self.server.client().get('/', headers={'Host': 'evil.example:80'}).status, 400)
        for host in ('localhost', '192.168.1.25:8000', 'shop-pc', 'shop-pc.local:8000', '[::1]:8000'):
            self.assertEqual(self.server.client().get('/', headers={'Host': host}).status, 200, host)

    def test_post_without_origin_from_another_site_rejected(self):
        res = self.admin.post('/api/customers', {'name': 'Evil'}, headers={'Referer': 'https://evil.example/page'})
        self.assertEqual(res.status, 403)
        res = self.admin.request('POST', '/api/customers', raw=b'name=Evil', headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(res.status, 403)

    def test_login_throttled_after_repeated_failures(self):
        anon = self.server.client()
        codes = [anon.login('throttle-me', 'x').status for _ in range(11)]
        self.assertEqual(codes[:10], [401] * 10)
        self.assertEqual(codes[10], 429)

    def test_static_files_and_traversal(self):
        anon = self.server.client()
        index = anon.get('/')
        self.assertEqual(index.status, 200)
        self.assertIn(b'<html', index.body)
        self.assertEqual(anon.get('/static/..%2f..%2fserver.py').status, 404)
        self.assertEqual(anon.get('/static/nope.js').status, 404)

    def test_security_headers(self):
        res = self.server.client().get('/')
        self.assertEqual(res.headers['X-Frame-Options'], 'DENY')
        self.assertEqual(res.headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("frame-ancestors 'none'", res.headers['Content-Security-Policy'])

    def test_cross_origin_post_rejected(self):
        res = self.admin.post('/api/customers', {'name': 'Evil'}, headers={'Origin': 'https://evil.example'})
        self.assertEqual(res.status, 403)

    def test_oversized_body_rejected(self):
        res = self.admin.request('POST', '/api/expenses', raw=b'{}', headers={'Content-Type': 'application/json', 'Content-Length': '999999999'})
        self.assertEqual(res.status, 400)
        self.assertIn('too large', res.json()['error'])

    def test_password_change_revokes_other_sessions(self):
        self.make_staff('pwchanger', 'firstpass1')
        a, b = self.server.client(), self.server.client()
        a.login('pwchanger', 'firstpass1'); b.login('pwchanger', 'firstpass1')
        self.assertEqual(a.post('/api/password', {'current_password': 'wrong', 'new_password': 'secondpass2'}).status, 400)
        self.assertEqual(a.post('/api/password', {'current_password': 'firstpass1', 'new_password': 'secondpass2'}).status, 200)
        self.assertTrue(a.get('/api/me').json()['authenticated'])
        self.assertFalse(b.get('/api/me').json()['authenticated'])


class PermissionTests(ApiTestCase):
    STAFF_ALLOWED_GET = ['/api/dashboard', '/api/analytics', '/api/expenses', '/api/products', '/api/held-bills',
                         '/api/export/sales.xlsx', '/api/export/sales-detailed.xlsx', '/api/export/sales.pdf']
    STAFF_DENIED_GET = ['/api/settings', '/api/users', '/api/customers', '/api/purchases', '/api/categories',
                        '/api/recurring-expenses', '/api/inventory/ledger?product_id=1', '/api/backup']
    STAFF_DENIED_POST = ['/api/users', '/api/products', '/api/customers', '/api/settings', '/api/pricing', '/api/inventory/adjust',
                         '/api/inventory/remove', '/api/purchases', '/api/returns', '/api/payments', '/api/invoices/1/void',
                         '/api/invoices/1/edit', '/api/held-bills/delete/1', '/api/products/1/remove', '/api/recurring-expenses/1/edit',
                         '/api/recurring-expenses/1/delete']

    def test_staff_allowed_reads(self):
        for path in self.STAFF_ALLOWED_GET:
            with self.subTest(path=path):
                self.assertEqual(self.staff.get(path).status, 200)

    def test_staff_denied_reads(self):
        for path in self.STAFF_DENIED_GET:
            with self.subTest(path=path):
                self.assertEqual(self.staff.get(path).status, 403)

    def test_staff_denied_writes(self):
        for path in self.STAFF_DENIED_POST:
            with self.subTest(path=path):
                self.assertEqual(self.staff.post(path, {}).status, 403)

    def test_staff_can_change_own_password(self):
        self.make_staff('selfservice', 'firstpass1')
        c = self.server.client(); c.login('selfservice', 'firstpass1')
        self.assertEqual(c.post('/api/password', {'current_password': 'firstpass1', 'new_password': 'otherpass2'}).status, 200)

    def test_unknown_api_route(self):
        self.assertEqual(self.admin.get('/api/does-not-exist').status, 404)


class UserTests(ApiTestCase):
    def test_create_validation(self):
        self.assertEqual(self.admin.post('/api/users', {'username': 'x', 'password': 'longenough'}).status, 400)
        self.assertEqual(self.admin.post('/api/users', {'username': 'validname', 'password': 'short'}).status, 400)
        self.assertEqual(self.admin.post('/api/users', {'username': 'dupuser', 'password': 'longenough'}).status, 200)
        self.assertEqual(self.admin.post('/api/users', {'username': 'dupuser', 'password': 'longenough'}).status, 400)

    def test_list_hides_hashes(self):
        users = self.admin.get('/api/users').json()
        self.assertTrue(users)
        self.assertTrue(all('password_hash' not in u for u in users))

    def test_deactivate_and_reactivate(self):
        self.make_staff('tobedisabled')
        user_id = next(u['id'] for u in self.admin.get('/api/users').json() if u['username'] == 'tobedisabled')
        c = self.server.client(); c.login('tobedisabled', 'staffpass1')
        self.assertEqual(self.admin.post(f'/api/users/{user_id}/status', {'active': False}).status, 200)
        self.assertFalse(c.get('/api/me').json()['authenticated'])
        self.assertEqual(self.server.client().login('tobedisabled', 'staffpass1').status, 401)
        self.assertEqual(self.admin.post(f'/api/users/{user_id}/status', {'active': True}).status, 200)
        self.assertEqual(self.server.client().login('tobedisabled', 'staffpass1').status, 200)

    def test_cannot_deactivate_self(self):
        me = self.admin.get('/api/me').json()['user']
        res = self.admin.post(f"/api/users/{me['id']}/status", {'active': False})
        self.assertEqual(res.status, 400)

    def test_status_validation_and_missing_user(self):
        self.assertEqual(self.admin.post('/api/users/99999/status', {'active': False}).status, 404)
        self.make_staff('statusval')
        user_id = next(u['id'] for u in self.admin.get('/api/users').json() if u['username'] == 'statusval')
        self.assertEqual(self.admin.post(f'/api/users/{user_id}/status', {}).status, 400)
        self.assertEqual(self.admin.post(f'/api/users/{user_id}/status', {'active': 'maybe'}).status, 400)


class ProductTests(ApiTestCase):
    def test_create_list_detail(self):
        pid = self.make_product(price=120, stock=7, category='Rockets')
        products = self.admin.get('/api/products').json()
        row = next(p for p in products if p['id'] == pid)
        self.assertEqual(row['default_unit_price'], 120)
        self.assertEqual(row['current_stock_base'], 7)
        self.assertEqual(row['price'], {'unit_price': 120})
        detail = self.admin.get(f'/api/products/{pid}').json()
        self.assertEqual(detail['stock'], 7)
        self.assertEqual(detail['product']['sku'], row['sku'])
        self.assertIn('Rockets', self.admin.get('/api/categories').json())

    def test_search_and_missing(self):
        pid = self.make_product()
        sku = self.admin.get(f'/api/products/{pid}').json()['product']['sku']
        found = self.admin.get('/api/products?q=' + sku).json()
        self.assertEqual([p['id'] for p in found], [pid])
        self.assertEqual(self.admin.get('/api/products/99999').status, 404)

    def test_validation(self):
        self.assertEqual(self.admin.post('/api/products', {'sku': '', 'name': 'x', 'unit_price': 1}).status, 400)
        self.assertEqual(self.admin.post('/api/products', {'sku': 'NEG-1', 'name': 'x', 'unit_price': -1}).status, 400)
        self.assertEqual(self.admin.post('/api/products', {'sku': 'NEG-2', 'name': 'x', 'unit_price': 1, 'opening_stock': -5}).status, 400)

    def test_duplicate_sku_rejected_with_clear_message(self):
        self.admin.post('/api/products', {'sku': 'DUP-1', 'name': 'One', 'unit_price': 1})
        res = self.admin.post('/api/products', {'sku': 'DUP-1', 'name': 'Two', 'unit_price': 1})
        self.assertEqual(res.status, 400)
        self.assertIn('DUP-1', res.json()['error'])

    def test_remove_unused_deletes_used_archives(self):
        unused = self.make_product()
        res = self.admin.post(f'/api/products/{unused}/remove')
        self.assertEqual(res.json()['action'], 'product removed')
        self.assertEqual(self.admin.get(f'/api/products/{unused}').status, 404)
        used = self.make_product()
        self.sell(self.admin, [{'product_id': used, 'qty': 1}], [{'mode': 'Cash', 'amount': 100}])
        res = self.admin.post(f'/api/products/{used}/remove')
        self.assertEqual(res.json()['action'], 'product deactivated')
        self.assertEqual(self.admin.get(f'/api/products/{used}').json()['product']['status'], 'INACTIVE')

    def test_set_unit_price(self):
        pid = self.make_product(price=10)
        self.assertEqual(self.admin.post('/api/pricing', {'product_id': pid, 'unit_price': 15}).status, 200)
        self.assertEqual(self.admin.get(f'/api/products/{pid}').json()['product']['default_unit_price'], 15)
        self.assertEqual(self.admin.post('/api/pricing', {'product_id': pid, 'unit_price': -1}).status, 400)
        self.assertEqual(self.admin.post('/api/pricing', {'product_id': 99999, 'unit_price': 1}).status, 400)


class ImportTests(ApiTestCase):
    CSV = b'Product ID,Product Name,Unit Price,Opening Stock,Category,Unit\nIMP-1,Imported One,25,10,Sparklers,Box\nIMP-2,Imported Two,40,0,Rockets,Box\n'

    def test_preview_then_import(self):
        res = self.admin.upload('/api/import/products', {'mode': 'preview'}, 'master.csv', self.CSV)
        self.assertEqual(res.status, 200, res.body)
        preview = res.json()
        self.assertEqual(preview['count'], 2)
        self.assertEqual(preview['mapping']['sku'], 'Product ID')
        self.assertEqual(preview['errors'], [])
        res = self.admin.upload('/api/import/products', {}, 'master.csv', self.CSV)
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()['imported'], 2)
        products = {p['sku']: p for p in self.admin.get('/api/products').json()}
        self.assertEqual(products['IMP-1']['current_stock_base'], 10)
        self.assertEqual(products['IMP-2']['default_unit_price'], 40)
        again = self.admin.upload('/api/import/products', {}, 'master.csv', self.CSV)
        self.assertEqual(again.status, 400)
        self.assertEqual(again.json()['duplicate_rows'], 2)

    def import_file(self, filename, content):
        preview = self.admin.upload('/api/import/products', {'mode': 'preview'}, filename, content)
        self.assertEqual(preview.status, 200, preview.body)
        self.assertEqual(preview.json()['errors'], [])
        res = self.admin.upload('/api/import/products', {}, filename, content)
        self.assertEqual(res.status, 200, res.body)
        return preview.json(), res.json()

    def test_repository_templates_import(self):
        """The Product_Master_Template files shipped in the repository import cleanly, with every used column mapped."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # The .xlsx goes in as it is; the CSV holds the same products, so its SKUs and barcode are renamed to stay unique.
        for name, sku in (('Product_Master_Template.xlsx', 'SKU-001'), ('Product_Master_Template.csv', 'CSV-001')):
            with self.subTest(name):
                with open(os.path.join(root, name), 'rb') as handle:
                    content = handle.read()
                if name.endswith('.csv'):
                    content = content.replace(b'SKU-', b'CSV-').replace(b'8901234500017', b'8901234500024')
                preview, result = self.import_file(name, content)
                self.assertEqual(result['imported'], 5)
                mapping = preview['mapping']
                self.assertEqual((mapping['sku'], mapping['unit_price'], mapping['cost_price']),
                                 ('Product Code / SKU', 'Retail Selling Price', 'Cost Price'))
                self.assertEqual((mapping['barcode'], mapping['explosive_kg']), ('Barcode', 'Net Explosive Content (kg)'))
                self.assertNotIn('', preview['headers'])
                self.assertFalse(any('gst' in h.lower() or 'hsn' in h.lower() or 'cess' in h.lower() for h in preview['headers']))
                product = next(p for p in self.admin.get('/api/products').json() if p['sku'] == sku)
                self.assertEqual((product['default_unit_price'], product['current_stock_base'], product['explosive_kg']), (99, 50, 0.05))
                self.assertTrue(product['barcode'].startswith('89012345000'), 'barcode kept as text, not a number')
                detail = self.admin.get(f"/api/products/{product['id']}").json()['product']
                self.assertEqual(detail['cost_price'], 45)

    def test_old_template_with_tax_columns_still_imports(self):
        """Spreadsheets made from the earlier template (with GST/cess/HSN columns) import; those columns are ignored."""
        old = ('Product Code / SKU,Product Name,Category,Unit,Cost Price,MRP,Retail Selling Price,GST Rate,Compensation Cess Rate,'
               'HSN Code,Opening Stock,Product Status\nOLD-1,Old Sparkler,Sparklers,Box,45,135,99,18,0,3604,50,ACTIVE\n').encode()
        _preview, result = self.import_file('old.csv', old)
        self.assertEqual(result['imported'], 1)
        product = next(p for p in self.admin.get('/api/products').json() if p['sku'] == 'OLD-1')
        self.assertEqual((product['default_unit_price'], product['current_stock_base']), (99, 50))

    def test_missing_columns(self):
        res = self.admin.upload('/api/import/products', {}, 'bad.csv', b'Foo,Bar\n1,2\n')
        self.assertEqual(res.status, 400)
        self.assertIn('Mandatory columns missing', res.json()['error'])

    def test_requires_file(self):
        res = self.admin.upload('/api/import/products', {'mode': 'preview'}, '', b'')
        self.assertEqual(res.status, 400)


class BrandTests(ApiTestCase):
    """Same-named products from different companies must stay apart on bills, in search and in reports."""

    def test_brand_in_search_bill_and_exports(self):
        a = self.make_product(price=100, name='Rocket Pack', brand='Standard Fireworks')
        b = self.make_product(price=150, name='Rocket Pack', brand='Cock Brand')
        found = {r['id'] for r in self.admin.get('/api/products?q=Cock').json()}
        self.assertIn(b, found)
        self.assertNotIn(a, found)
        res = self.sell(self.admin, [{'product_id': a, 'qty': 1}, {'product_id': b, 'qty': 2}], [{'mode': 'Cash', 'amount': 400}])
        self.assertEqual(res.status, 200, res.body)
        items = self.admin.get(f"/api/invoices/{res.json()['invoice_id']}").json()['items']
        self.assertEqual([(i['product_name_snapshot'], i['brand_snapshot']) for i in items],
                         [('Rocket Pack', 'Standard Fireworks'), ('Rocket Pack', 'Cock Brand')])
        top = self.admin.get('/api/analytics?preset=today').json()['top_products']
        self.assertIn(('Rocket Pack', 'Cock Brand'), {(t['name'], t.get('brand')) for t in top})
        for path in ('/api/export/sales-detailed.xlsx', '/api/export/sales.pdf', f"/api/invoice-pdf/{res.json()['invoice_id']}", f"/api/invoice-receipt/{res.json()['invoice_id']}"):
            with self.subTest(path=path):
                self.assertEqual(self.admin.get(path).status, 200)


class SalesTests(ApiTestCase):
    def test_sale_flow_and_invoice_detail(self):
        pid = self.make_product(price=100, stock=10)
        res = self.sell(self.staff, [{'product_id': pid, 'qty': 3}], [{'mode': 'Cash', 'amount': 200}, {'mode': 'Credit', 'amount': 90}],
                        discount=10, customer_name='Asha', customer_phone='9876543210')
        self.assertEqual(res.status, 200, res.body)
        sale = res.json()
        self.assertTrue(sale['invoice_number'].startswith('FW-'))
        self.assertEqual(self.stock_of(pid), 7)
        detail = self.admin.get(f"/api/invoices/{sale['invoice_id']}").json()
        inv = detail['invoice']
        self.assertEqual((inv['subtotal'], inv['discount'], inv['grand_total'], inv['amount_received'], inv['outstanding']), (300, 10, 290, 200, 90))
        self.assertEqual(inv['customer_name_snapshot'], 'Asha')
        self.assertEqual(inv['customer_phone'], '9876543210')
        self.assertTrue(inv['billed_by_name'].startswith('staff_'))
        self.assertEqual(len(detail['items']), 1)
        self.assertEqual(len(detail['payments']), 2)
        listed = self.admin.get('/api/invoices?start=1900-01-01&end=2999-12-31').json()
        self.assertIn(sale['invoice_id'], [i['id'] for i in listed])

    def test_server_ignores_client_price(self):
        pid = self.make_product(price=20, stock=5)
        res = self.sell(self.admin, [{'product_id': pid, 'qty': 1, 'unit_price': 1}], [{'mode': 'Cash', 'amount': 1}])
        self.assertEqual(res.status, 400)
        res = self.sell(self.admin, [{'product_id': pid, 'qty': 1, 'unit_price': 1}], [{'mode': 'Cash', 'amount': 20}])
        self.assertEqual(res.status, 200)

    def test_sale_validation(self):
        pid = self.make_product(price=10, stock=2)
        cases = [
            ({'items': [], 'payments': []}, 'at least one product'),
            ({'items': [{'product_id': pid, 'qty': 5}], 'payments': [{'mode': 'Cash', 'amount': 50}]}, 'Insufficient stock'),
            ({'items': [{'product_id': pid, 'qty': 0}], 'payments': []}, 'Invalid quantity'),
            ({'items': [{'product_id': pid, 'qty': 1}], 'payments': [{'mode': 'Cash', 'amount': 5}]}, 'equal the invoice total'),
            ({'items': [{'product_id': pid, 'qty': 1}], 'payments': [{'mode': 'Cash', 'amount': 10}], 'discount': 11}, 'subtotal'),
            ({'items': [{'product_id': pid, 'qty': 1}], 'payments': [{'mode': 'Cash', 'amount': 10}], 'customer_phone': '123'}, '10 digits'),
            ({'items': [{'product_id': 99999, 'qty': 1}], 'payments': []}, 'not found'),
        ]
        for body, message in cases:
            with self.subTest(message=message):
                res = self.admin.post('/api/sales', body)
                self.assertEqual(res.status, 400)
                self.assertIn(message, res.json()['error'])
        self.assertEqual(self.stock_of(pid), 2)

    def test_invoice_pdf(self):
        pid = self.make_product()
        sale = self.sell(self.staff, [{'product_id': pid, 'qty': 1}], [{'mode': 'UPI', 'amount': 100}]).json()
        pdf = self.staff.get(f"/api/invoice-pdf/{sale['invoice_id']}")
        self.assertEqual(pdf.status, 200)
        self.assertEqual(pdf.headers['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.body.startswith(b'%PDF'))
        self.assertEqual(self.admin.get('/api/invoice-pdf/99999').status, 404)
        self.assertEqual(self.admin.get('/api/invoices/99999').status, 404)

    def test_void_restores_stock(self):
        pid = self.make_product(stock=5)
        sale = self.sell(self.admin, [{'product_id': pid, 'qty': 2}], [{'mode': 'Cash', 'amount': 200}]).json()
        self.assertEqual(self.admin.post(f"/api/invoices/{sale['invoice_id']}/void").status, 200)
        self.assertEqual(self.stock_of(pid), 5)
        self.assertEqual(self.admin.post(f"/api/invoices/{sale['invoice_id']}/void").status, 400)
        voided = self.admin.get('/api/invoices?start=1900-01-01&end=2999-12-31&status=VOID').json()
        row = next(i for i in voided if i['id'] == sale['invoice_id'])
        self.assertEqual(row['voided_by_name'], 'admin')
        self.assertTrue(row['voided_at'])

    def test_edit_bill(self):
        pid = self.make_product(price=50, stock=10)
        sale = self.sell(self.staff, [{'product_id': pid, 'qty': 2}], [{'mode': 'Cash', 'amount': 100}]).json()
        body = {'items': [{'product_id': pid, 'qty': 3}], 'payments': [{'mode': 'UPI', 'amount': 150}]}
        self.assertEqual(self.admin.post(f"/api/invoices/{sale['invoice_id']}/edit", body).status, 400)
        res = self.admin.post(f"/api/invoices/{sale['invoice_id']}/edit", {**body, 'reason': 'Added a box'})
        self.assertEqual(res.status, 200, res.body)
        edited = res.json()
        self.assertEqual(edited['previous_invoice_number'], sale['invoice_number'])
        self.assertEqual(self.stock_of(pid), 7)
        inv = self.admin.get(f"/api/invoices/{edited['invoice_id']}").json()['invoice']
        self.assertEqual(inv['grand_total'], 150)
        self.assertEqual(inv['revised_from_number'], sale['invoice_number'])
        self.assertEqual(inv['edited_by_name'], 'admin')
        self.assertTrue(inv['billed_by_name'].startswith('staff_'))
        self.assertEqual(inv['revision_reason'], 'Added a box')
        old = self.admin.get(f"/api/invoices/{sale['invoice_id']}").json()['invoice']
        self.assertEqual((old['status'], old['revised_to_number']), ('VOID', edited['invoice_number']))
        too_much = self.admin.post(f"/api/invoices/{edited['invoice_id']}/edit", {'items': [{'product_id': pid, 'qty': 99}], 'payments': [{'mode': 'Cash', 'amount': 4950}], 'reason': 'too many'})
        self.assertEqual(too_much.status, 400)
        self.assertEqual(self.stock_of(pid), 7)
        still = self.admin.get(f"/api/invoices/{edited['invoice_id']}").json()['invoice']
        self.assertEqual(still['status'], 'FINALIZED')

    def test_returns(self):
        pid = self.make_product(price=30, stock=10)
        sale = self.sell(self.admin, [{'product_id': pid, 'qty': 4}], [{'mode': 'Cash', 'amount': 120}]).json()
        item_id = self.admin.get(f"/api/invoices/{sale['invoice_id']}").json()['items'][0]['id']
        res = self.admin.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': item_id, 'qty': 1}], 'reason': 'damaged'})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()['refund'], 30)
        self.assertEqual(self.stock_of(pid), 7)
        over = self.admin.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': item_id, 'qty': 4}]})
        self.assertEqual(over.status, 400)
        bad_item = self.admin.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': 99999, 'qty': 1}]})
        self.assertEqual(bad_item.status, 400)
        self.assertEqual(self.admin.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': []}).status, 400)
        self.assertEqual(self.admin.post(f"/api/invoices/{sale['invoice_id']}/void").status, 400)
        self.assertEqual(self.admin.post(f"/api/invoices/{sale['invoice_id']}/edit", {'items': [{'product_id': pid, 'qty': 1}], 'payments': [{'mode': 'Cash', 'amount': 30}], 'reason': 'after return'}).status, 400)

    def test_collect_credit_payment(self):
        pid = self.make_product(price=100)
        sale = self.sell(self.admin, [{'product_id': pid, 'qty': 1}], [{'mode': 'Credit', 'amount': 100}]).json()
        self.assertEqual(self.admin.post('/api/payments', {'invoice_id': sale['invoice_id'], 'amount': 150, 'mode': 'Cash'}).status, 400)
        res = self.admin.post('/api/payments', {'invoice_id': sale['invoice_id'], 'amount': 60, 'mode': 'Cash'})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()['outstanding'], 40)
        inv = self.admin.get(f"/api/invoices/{sale['invoice_id']}").json()['invoice']
        self.assertEqual((inv['amount_received'], inv['outstanding']), (60, 40))

    def test_no_payment_on_voided_bill(self):
        pid = self.make_product(price=100)
        sale = self.sell(self.admin, [{'product_id': pid, 'qty': 1}], [{'mode': 'Credit', 'amount': 100}]).json()
        self.admin.post(f"/api/invoices/{sale['invoice_id']}/void")
        self.assertEqual(self.admin.post('/api/payments', {'invoice_id': sale['invoice_id'], 'amount': 10, 'mode': 'Cash'}).status, 400)


class HeldBillTests(ApiTestCase):
    def test_hold_list_resume_delete(self):
        pid = self.make_product()
        res = self.staff.post('/api/held-bills', {'customer_name': 'Ravi', 'customer_phone': '9999999999', 'items': [{'product_id': pid, 'qty': 2}], 'discount': 5})
        self.assertEqual(res.status, 200, res.body)
        held_id = res.json()['id']
        self.assertTrue(res.json()['ref'].startswith('HOLD-'))
        listed = self.staff.get('/api/held-bills').json()
        row = next(h for h in listed if h['id'] == held_id)
        self.assertEqual((row['items'], row['discount'], row['customer_phone']), ([{'product_id': pid, 'qty': 2}], 5, '9999999999'))
        peek = self.staff.get(f'/api/held-bills/resume/{held_id}').json()
        self.assertEqual(peek['items'], [{'product_id': pid, 'qty': 2}])
        resumed = self.staff.post(f'/api/held-bills/resume/{held_id}').json()
        self.assertEqual(resumed['bill']['customer_name'], 'Ravi')
        self.assertEqual(self.staff.post(f'/api/held-bills/resume/{held_id}').status, 404)
        other = self.staff.post('/api/held-bills', {'items': [{'product_id': pid, 'qty': 1}]}).json()['id']
        self.assertEqual(self.admin.post(f'/api/held-bills/delete/{other}').status, 200)
        self.assertNotIn(other, [h['id'] for h in self.staff.get('/api/held-bills').json()])


class InventoryTests(ApiTestCase):
    def test_adjust_remove_ledger(self):
        pid = self.make_product(stock=10)
        self.assertEqual(self.admin.post('/api/inventory/adjust', {'product_id': pid, 'qty': 3, 'type': 'DAMAGE'}).status, 200)
        self.assertEqual(self.stock_of(pid), 7)
        self.assertEqual(self.admin.post('/api/inventory/adjust', {'product_id': pid, 'qty': 2, 'type': 'FOUND'}).status, 200)
        self.assertEqual(self.stock_of(pid), 9)
        self.assertEqual(self.admin.post('/api/inventory/adjust', {'product_id': pid, 'qty': 50, 'type': 'DAMAGE'}).status, 400)
        self.assertEqual(self.admin.post('/api/inventory/remove', {'product_id': pid, 'qty': 4, 'reason': 'Damage'}).status, 200)
        self.assertEqual(self.stock_of(pid), 5)
        self.assertEqual(self.admin.post('/api/inventory/remove', {'product_id': pid, 'qty': 0}).status, 400)
        self.assertEqual(self.admin.post('/api/inventory/remove', {'product_id': pid, 'qty': 99}).status, 400)
        ledger = self.admin.get(f'/api/inventory/ledger?product_id={pid}&start=1900-01-01&end=2999-12-31').json()
        self.assertEqual([m['movement_type'] for m in ledger], ['OPENING', 'ADJUSTMENT', 'ADJUSTMENT', 'STOCK_REMOVAL'])

    def test_adjust_unknown_product(self):
        self.assertEqual(self.admin.post('/api/inventory/adjust', {'product_id': 99999, 'qty': 1, 'type': 'FOUND'}).status, 400)

    def test_purchase_adds_stock(self):
        pid = self.make_product(stock=0)
        res = self.admin.post('/api/purchases', {'supplier_name': 'Sivakasi Co', 'purchase_date': '2026-10-01', 'freight': 50,
                                                 'items': [{'product_id': pid, 'qty': 12, 'cost_price': 40, 'batch_number': 'B1'}]})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(res.json()['total'], 530)
        self.assertEqual(self.stock_of(pid), 12)
        purchases = self.admin.get('/api/purchases').json()
        self.assertEqual(purchases[0]['purchase_number'], res.json()['purchase_number'])

    def test_purchase_validation(self):
        self.assertEqual(self.admin.post('/api/purchases', {'items': [{'product_id': 99999, 'qty': 1}]}).status, 400)


class CustomerTests(ApiTestCase):
    def test_create_and_list(self):
        res = self.admin.post('/api/customers', {'name': 'Mahalaxmi Traders', 'phone': '9876500012', 'customer_type': 'WHOLESALE'})
        self.assertEqual(res.status, 200, res.body)
        rows = self.admin.get('/api/customers?q=Mahalaxmi').json()
        self.assertEqual(rows[0]['phone'], '9876500012')
        self.assertTrue(rows[0]['customer_code'].startswith('CUST-'))

    def test_name_required(self):
        self.assertEqual(self.admin.post('/api/customers', {'phone': '1'}).status, 400)

    def test_sale_creates_customer_from_phone(self):
        pid = self.make_product(price=10)
        self.sell(self.admin, [{'product_id': pid, 'qty': 1}], [{'mode': 'Cash', 'amount': 10}], customer_name='Walk Buyer', customer_phone='9000000001')
        rows = self.admin.get('/api/customers?q=9000000001').json()
        self.assertEqual(rows[0]['name'], 'Walk Buyer')


class ExpenseTests(ApiTestCase):
    def test_create_and_list(self):
        res = self.staff.post('/api/expenses', {'expense_date': '2026-10-05', 'category': 'Rent', 'amount': 2500, 'payment_mode': 'UPI'})
        self.assertEqual(res.status, 200, res.body)
        rows = self.staff.get('/api/expenses?start=2026-10-01&end=2026-10-31').json()
        self.assertEqual([(r['category'], r['amount']) for r in rows], [('Rent', 2500)])

    def test_validation(self):
        self.assertEqual(self.staff.post('/api/expenses', {'category': 'X', 'amount': 0}).status, 400)
        self.assertEqual(self.staff.post('/api/expenses', {'category': 'X', 'amount': 5, 'expense_date': 'not-a-date'}).status, 400)

    def test_recurring(self):
        self.assertEqual(self.staff.post('/api/recurring-expenses', {'category': 'Rent', 'amount': 100}).status, 400)
        res = self.staff.post('/api/recurring-expenses', {'category': 'Rent', 'amount': 100, 'frequency': 'Monthly', 'start_date': '2026-10-01'})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual(self.admin.get('/api/recurring-expenses').json()[0]['category'], 'Rent')

    def test_edit_and_delete_own(self):
        eid = self.staff.post('/api/expenses', {'expense_date': '2026-10-05', 'category': 'Rent', 'amount': 2500}).json()['id']
        self.assertEqual(self.staff.get(f'/api/expenses/{eid}').json()['category'], 'Rent')
        res = self.staff.post(f'/api/expenses/{eid}/edit', {'expense_date': '2026-10-06', 'category': 'Tea', 'amount': 30, 'payment_mode': 'UPI', 'vendor': 'Chai Stall'})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual((res.json()['expense']['category'], res.json()['expense']['amount'], res.json()['expense']['vendor']), ('Tea', 30, 'Chai Stall'))
        self.assertEqual(self.staff.post(f'/api/expenses/{eid}/edit', {'category': 'Tea', 'amount': 0}).status, 400)
        self.assertEqual(self.staff.post(f'/api/expenses/{eid}/delete', {}).status, 200)
        self.assertEqual(self.staff.get(f'/api/expenses/{eid}').status, 404)
        self.assertEqual(self.staff.post(f'/api/expenses/{eid}/delete', {}).status, 404)
        self.assertNotIn(eid, [r['id'] for r in self.staff.get('/api/expenses?start=2026-10-01&end=2026-10-31').json()])
        actions = [a['action'] for a in self.admin.get('/api/audit?start=1900-01-01&end=2999-12-31&entity=EXPENSE').json()['entries']]
        for action in ('Expense added', 'Expense edited', 'Expense deleted'):
            self.assertIn(action, actions)

    def test_only_owner_or_manager_changes_others_expenses(self):
        eid = self.admin.post('/api/expenses', {'category': 'Rent', 'amount': 2500}).json()['id']
        self.assertEqual(self.staff.post(f'/api/expenses/{eid}/edit', {'category': 'Rent', 'amount': 1}).status, 403)
        self.assertEqual(self.staff.post(f'/api/expenses/{eid}/delete', {}).status, 403)
        self.assertEqual(self.admin.get(f'/api/expenses/{eid}').json()['amount'], 2500)
        staff_eid = self.staff.post('/api/expenses', {'category': 'Tea', 'amount': 20}).json()['id']
        self.assertEqual(self.admin.post(f'/api/expenses/{staff_eid}/edit', {'category': 'Tea', 'amount': 25}).status, 200)
        self.assertEqual(self.admin.post(f'/api/expenses/{staff_eid}/delete', {}).status, 200)

    def test_recurring_edit_pause_delete(self):
        rid = self.admin.post('/api/recurring-expenses', {'category': 'Rent', 'amount': 100, 'frequency': 'Monthly', 'start_date': '2026-10-01'}).json()['id']
        self.assertEqual(self.staff.post(f'/api/recurring-expenses/{rid}/edit', {'category': 'Rent', 'amount': 1, 'frequency': 'Monthly', 'start_date': '2026-10-01'}).status, 403)
        self.assertEqual(self.staff.post(f'/api/recurring-expenses/{rid}/delete', {}).status, 403)
        res = self.admin.post(f'/api/recurring-expenses/{rid}/edit', {'category': 'Shop rent', 'amount': 120, 'frequency': 'Yearly', 'start_date': '2026-10-01', 'end_date': '2027-09-30'})
        self.assertEqual(res.status, 200, res.body)
        self.assertEqual((res.json()['recurring']['category'], res.json()['recurring']['amount'], res.json()['recurring']['frequency']), ('Shop rent', 120, 'Yearly'))
        self.assertEqual(self.admin.post(f'/api/recurring-expenses/{rid}/edit', {'category': 'X', 'amount': 1, 'frequency': 'Weekly', 'start_date': '2026-10-01', 'end_date': '2026-01-01'}).status, 400)
        self.assertEqual(self.admin.post(f'/api/recurring-expenses/{rid}/active', {'active': False}).json()['recurring']['active'], 0)
        self.assertEqual(self.admin.post(f'/api/recurring-expenses/{rid}/active', {'active': True}).json()['recurring']['active'], 1)
        self.assertEqual(self.admin.post(f'/api/recurring-expenses/{rid}/delete', {}).status, 200)
        self.assertNotIn(rid, [r['id'] for r in self.admin.get('/api/recurring-expenses').json()])
        self.assertEqual(self.admin.post(f'/api/recurring-expenses/{rid}/delete', {}).status, 404)


class SettingsTests(ApiTestCase):
    def test_get_and_update(self):
        data = self.admin.get('/api/settings').json()
        self.assertIn('business_name', data['settings'])
        self.assertIn('daily', data['targets'])
        new_settings = {**data['settings'], 'business_name': 'Diwali Depot', 'invoice_footer': 'Visit again'}
        targets = {**data['targets'], 'daily': 12345}
        self.assertEqual(self.admin.post('/api/settings', {'settings': new_settings, 'targets': targets}).status, 200)
        again = self.admin.get('/api/settings').json()
        self.assertEqual(again['settings']['business_name'], 'Diwali Depot')
        self.assertEqual(again['targets']['daily'], 12345)
        self.assertEqual(again['settings']['walk_in_name'], data['settings']['walk_in_name'])


class ReportTests(ApiTestCase):
    def test_dashboard_and_analytics_shape(self):
        pid = self.make_product(price=100, stock=3, reorder_level=5)
        self.sell(self.admin, [{'product_id': pid, 'qty': 1}], [{'mode': 'Cash', 'amount': 100}])
        d = self.staff.get('/api/dashboard').json()
        for key in ('today', 'yesterday', 'last_week', 'expenses', 'low_stock', 'inventory_cost', 'target', 'attention'):
            self.assertIn(key, d)
        self.assertGreaterEqual(d['today']['bills'], 1)
        self.assertGreaterEqual(d['low_stock'], 1)
        for preset in ('today', 'yesterday', '7d', 'month', 'season'):
            with self.subTest(preset=preset):
                a = self.staff.get('/api/analytics?preset=' + preset).json()
                for key in ('period', 'kpi', 'expenses', 'net_profit', 'hourly', 'top_products', 'categories', 'payments', 'customers', 'slow_movers', 'bottom_products', 'discounts', 'target'):
                    self.assertIn(key, a)

    def test_backup_has_no_credentials(self):
        data = self.admin.get('/api/backup')
        self.assertEqual(data.status, 200)
        self.assertIn('attachment', data.headers['Content-Disposition'])
        users = data.json()['users']
        self.assertTrue(users)
        self.assertTrue(all('password_hash' not in u for u in users))

    def test_exports(self):
        pid = self.make_product(price=10)
        self.sell(self.admin, [{'product_id': pid, 'qty': 1}], [{'mode': 'Cash', 'amount': 10}], customer_name='=HYPERLINK("x")')
        for path, ctype in (('/api/export/sales.xlsx', 'spreadsheetml'), ('/api/export/sales-detailed.xlsx', 'spreadsheetml'), ('/api/export/sales.pdf', 'application/pdf')):
            with self.subTest(path=path):
                res = self.staff.get(path)
                self.assertEqual(res.status, 200)
                self.assertIn(ctype, res.headers['Content-Type'])
                self.assertIn('attachment', res.headers['Content-Disposition'])
        import io
        from openpyxl import load_workbook
        sheet = load_workbook(io.BytesIO(self.staff.get('/api/export/sales.xlsx').body)).active
        names = [c.value for c in sheet['C']]
        self.assertIn('\'=HYPERLINK("x")', names)


if __name__ == '__main__':
    unittest.main()
