"""Roles, per-user data limits, and the operational features (approvals, cash closing, suppliers, backups...)."""
import itertools
import json
import time
import unittest

from tests.support import ServerProcess, pdf_text

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
            ('GET', '/api/insights'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/invoices'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/customers'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/dues'): {'MANAGER', 'ACCOUNTANT'},
            ('GET', '/api/purchases'): {'MANAGER', 'STOCK_KEEPER'},
            ('GET', '/api/suppliers'): {'MANAGER', 'STOCK_KEEPER', 'ACCOUNTANT'},
            ('GET', '/api/reorder-plan'): {'MANAGER', 'STOCK_KEEPER'},
            ('GET', '/api/expenses'): {'MANAGER', 'CASHIER', 'ACCOUNTANT'},
            ('GET', '/api/recurring-expenses'): {'MANAGER', 'ACCOUNTANT'},
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

    def test_staff_name_only_on_the_seller_copy(self):
        """The customer copy and the 80 mm receipt go to the customer: no staff names on them."""
        pid = self.product()
        invoice_id = self.sell(self.cashier, pid).json()['invoice_id']
        pdf = self.owner.get(f'/api/invoice-pdf/{invoice_id}').body
        self.assertEqual(pdf.count(b'Billed by: Cashier One'), 1, 'once: on the seller copy only')
        self.assertIn(b'CUSTOMER COPY', pdf)
        receipt = pdf_text(self.owner.get(f'/api/invoice-receipt/{invoice_id}').body)
        self.assertIn('Bill: ', receipt, 'the receipt text can be read')
        self.assertNotIn('Cashier One', receipt)
        # An edited bill: who edited it is shown on the seller copy only.
        edited = self.owner.post(f'/api/invoices/{invoice_id}/edit', {'items': [{'product_id': pid, 'qty': 2}], 'reason': 'one more box',
                                                                      'payments': [{'mode': 'Cash', 'amount': 200}]}).json()
        pdf = self.owner.get(f"/api/invoice-pdf/{edited['invoice_id']}").body
        self.assertEqual(pdf.count(b'edited by'), 1)
        self.assertEqual(pdf.count(b'Revised from'), 2)

    def test_printed_payments_add_up_after_credit_is_collected(self):
        """Credit is money still owed, not a payment: once collected, the bill must not list it as paid as well."""
        pid = self.product(price=100)
        invoice_id = self.sell(self.cashier, pid, qty=5, payments=[{'mode': 'Cash', 'amount': 300}, {'mode': 'Credit', 'amount': 200}]).json()['invoice_id']
        receipt = pdf_text(self.owner.get(f'/api/invoice-receipt/{invoice_id}').body)
        self.assertIn('Paid Cash 300.00', receipt)
        self.assertNotIn('Paid Credit', receipt)
        self.assertIn('Credit due Rs. 200.00', receipt)
        self.assertEqual(self.owner.post('/api/payments', {'invoice_id': invoice_id, 'amount': 200, 'mode': 'UPI'}).status, 200)
        receipt = pdf_text(self.owner.get(f'/api/invoice-receipt/{invoice_id}').body)
        self.assertIn('Paid Cash 300.00 Paid UPI 200.00', receipt)
        self.assertNotIn('Credit', receipt)
        a4 = pdf_text(self.owner.get(f'/api/invoice-pdf/{invoice_id}').body)
        self.assertIn('Payment(s): Cash Rs. 300.00, UPI Rs. 200.00', a4)
        self.assertIn('Received Rs. 500.00', a4)


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


    def test_discounts_only_for_managers_setting(self):
        self.assertEqual(self.owner.get('/api/me').json()['limits']['discount_controls'], 'hidden', 'folded away by default')
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'discount_controls': 'everyone'}}).status, 400)
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'discount_controls': 'managers'}}).status, 200)
        try:
            self.assertEqual(self.cashier.get('/api/me').json()['limits']['discount_controls'], 'managers')
            pid = self.product(price=100)
            small = self.sell(self.cashier, pid, discount=5)
            self.assertEqual(small.json().get('code'), 'DISCOUNT_APPROVAL_REQUIRED', 'even a small discount needs a manager now')
            self.assertEqual(self.sell(self.cashier, pid).status, 200, 'bills without discount are unaffected')
            approved = self.sell(self.cashier, pid, discount=5, approval={'username': 'manager1', 'password': 'password12'})
            self.assertEqual(approved.status, 200, approved.body)
            self.assertEqual(self.sell(self.manager, pid, discount=5).status, 200, 'managers give discounts themselves')
        finally:
            self.owner.post('/api/settings', {'settings': {'discount_controls': 'hidden'}})
        self.assertEqual(self.sell(self.cashier, self.product(price=100), discount=5).status, 200, 'back to the 10% limit')

    def test_printouts_have_no_discount_line_without_a_discount(self):
        pid = self.product(price=100)
        plain = self.sell(self.cashier, pid).json()['invoice_id']
        for path in (f'/api/invoice-pdf/{plain}', f'/api/invoice-receipt/{plain}'):
            text = pdf_text(self.owner.get(path).body)
            self.assertNotIn('Discount', text, path)
            self.assertNotIn('Subtotal', text, path)
        given = self.sell(self.cashier, pid, discount=5).json()['invoice_id']
        self.assertIn('Discount Rs. 5.00', pdf_text(self.owner.get(f'/api/invoice-receipt/{given}').body))

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


    def test_deleted_and_edited_bills_leave_the_drawer(self):
        drawer = self.user('drawer3', 'CASHIER')
        summary = lambda: drawer.get('/api/cash-closing/summary').json()
        pid = self.product(price=100)
        kept = self.sell(drawer, pid).json()['invoice_id']
        deleted = self.sell(drawer, pid).json()['invoice_id']
        upi = self.sell(drawer, pid, payments=[{'mode': 'UPI', 'amount': 100}]).json()['invoice_id']
        self.assertEqual(summary()['expected_cash'], 200)
        self.assertEqual(self.owner.post(f'/api/invoices/{deleted}/void', {}).status, 200)
        self.assertEqual(self.owner.post(f'/api/invoices/{upi}/void', {}).status, 200)
        now = summary()
        self.assertEqual((now['expected_cash'], now['bills'], now['modes']), (100, 1, [{'mode': 'Cash', 'amount': 100, 'bills': 1}]),
                         'a bill deleted before closing is not counted at all')
        self.assertEqual(now['deleted_cash'], 0)
        # Editing a bill to 2 boxes re-issues it: only the new bill's payment counts.
        edit = self.owner.post(f'/api/invoices/{kept}/edit', {'items': [{'product_id': pid, 'qty': 2}], 'reason': 'customer took one more',
                                                               'payments': [{'mode': 'Cash', 'amount': 200}]})
        self.assertEqual(edit.status, 200, edit.body)
        self.assertEqual((summary()['bills'], summary()['expected_cash']), (0, 0),
                         'the old bill left this drawer; the owner made the edit, so the new payment is in the owner\'s drawer')
        # A bill paid before the closing and deleted after it: the cash goes back out of this drawer now.
        paid = self.sell(drawer, pid).json()['invoice_id']
        self.assertEqual(drawer.post('/api/cash-closing', {'counted_cash': 100}).json()['difference'], 0)
        time.sleep(1.1)  # times are stored to the second; the delete must come after the closing
        self.owner.post(f'/api/invoices/{paid}/void', {})
        after = summary()
        self.assertEqual((after['deleted_cash'], after['expected_cash'], after['modes']), (100, -100, []))
        self.sell(drawer, pid, qty=3)  # the day goes on: 300 taken, 100 of it already handed back
        self.assertEqual(summary()['expected_cash'], 200)
        self.assertEqual(drawer.post('/api/cash-closing', {'counted_cash': 200}).json()['difference'], 0)
        self.assertEqual(summary()['deleted_cash'], 0, 'counted once, in the period it was deleted')


class HeldBillAndReturnTests(RoleTestCase):
    def test_resumed_held_bill_stays_until_billed_or_held_again(self):
        pid = self.product(price=100)
        held = self.cashier.post('/api/held-bills', {'items': [{'product_id': pid, 'qty': 2}], 'customer_name': 'Park'}).json()
        peek = self.cashier.get(f"/api/held-bills/resume/{held['id']}").json()
        self.assertEqual(peek['items'], [{'product_id': pid, 'qty': 2}])
        mine = lambda: [h['ref'] for h in self.cashier.get('/api/held-bills').json()]
        self.assertIn(held['ref'], mine(), 'resuming does not remove it: a closed browser must not lose the bill')
        again = self.cashier.post('/api/held-bills', {'items': [{'product_id': pid, 'qty': 3}], 'replaces': held['ref']}).json()
        self.assertNotIn(held['ref'], mine(), 'holding it again replaces the old copy')
        self.assertIn(again['ref'], mine())
        sale = self.sell(self.cashier, pid, qty=3, held_ref=again['ref'])
        self.assertEqual(sale.status, 200, sale.body)
        self.assertNotIn(again['ref'], mine(), 'billed, so it leaves Held Bills')
        # Someone else's held bill is left alone, and an old ref never removes a newer bill.
        other = self.cashier2.post('/api/held-bills', {'items': [{'product_id': pid, 'qty': 1}]}).json()
        self.assertEqual(self.sell(self.cashier, pid, held_ref=other['ref']).status, 200)
        self.assertEqual(self.sell(self.cashier2, pid, held_ref=held['ref']).status, 200)
        self.assertIn(other['ref'], [h['ref'] for h in self.cashier2.get('/api/held-bills').json()])

    def test_return_on_credit_bill_comes_off_what_is_owed(self):
        pid = self.product(price=100)
        sale = self.sell(self.cashier, pid, qty=4, payments=[{'mode': 'Cash', 'amount': 100}, {'mode': 'Credit', 'amount': 300}],
                         customer_name='Owes Money', customer_phone='9876512345').json()
        item = self.manager.get(f"/api/invoices/{sale['invoice_id']}").json()['items'][0]
        refunds_before = self.manager.get('/api/cash-closing/summary').json()['refunds']
        first = self.manager.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': item['id'], 'qty': 2}]}).json()
        self.assertEqual((first['refund'], first['credit_adjusted'], first['paid_back']), (200, 200, 0))
        invoice = self.owner.get(f"/api/invoices/{sale['invoice_id']}").json()['invoice']
        self.assertEqual((invoice['outstanding'], invoice['returned_amount']), (100, 200))
        dues = next(c for c in self.owner.get('/api/dues').json()['customers'] if c['name'] == 'Owes Money')
        self.assertEqual(dues['total_due'], 100)
        second = self.manager.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': item['id'], 'qty': 2}]}).json()
        self.assertEqual((second['credit_adjusted'], second['paid_back']), (100, 100), 'the last 100 owed is cleared, the paid 100 goes back')
        self.assertEqual(self.owner.get(f"/api/invoices/{sale['invoice_id']}").json()['invoice']['outstanding'], 0)
        self.assertEqual(self.manager.get('/api/cash-closing/summary').json()['refunds'] - refunds_before, 100,
                         'only money actually paid back leaves the drawer')
        detail = self.manager.get(f"/api/invoices/{sale['invoice_id']}").json()
        self.assertEqual(detail['items'][0]['returned_qty'], 4)

    def test_returns_come_off_sales_and_profit(self):
        seller = self.user('netseller', 'CASHIER')  # a fresh cashier, so their own figures hold only this bill
        pid = self.product(price=100)  # cost price 60
        kpi = lambda: self.owner.get('/api/insights?preset=today').json()['sales']['kpi']
        sale = self.sell(seller, pid, qty=3).json()
        before = kpi()
        item = self.manager.get(f"/api/invoices/{sale['invoice_id']}").json()['items'][0]
        self.manager.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': item['id'], 'qty': 1}]})
        after = kpi()
        self.assertAlmostEqual(before['sales'] - after['sales'], 100)
        self.assertAlmostEqual(before['cogs'] - after['cogs'], 60)
        self.assertAlmostEqual(before['gross_profit'] - after['gross_profit'], 40)
        self.assertAlmostEqual(before['items'] - after['items'], 1)
        self.assertAlmostEqual(after['returns'] - before['returns'], 100)
        self.assertAlmostEqual(self.owner.get('/api/dashboard').json()['today']['sales'], after['sales'], msg='dashboard and analytics agree')
        own = seller.get('/api/insights?preset=today').json()
        self.assertEqual((own['sales']['kpi']['sales'], own['sales']['kpi']['items']), (200, 2), "the seller's own figures net the return too")
        self.assertEqual([(p['qty'], p['revenue']) for p in own['products']['top']], [(2, 200)])  # cashiers don't see profit
        self.assertEqual(sum(day['sales'] for day in own['sales']['trend']), 200)


class FindingBillsAndCustomersTests(RoleTestCase):
    def test_credit_bills_can_be_listed_and_searched(self):
        pid = self.product(price=100)
        credit = self.sell(self.cashier, pid, payments=[{'mode': 'Credit', 'amount': 100}], customer_name='Lata Credit',
                           customer_phone='9812300001').json()
        self.sell(self.cashier, pid)
        listed = lambda client, **q: client.get('/api/invoices?start=1900-01-01&end=2999-12-31&' +
                                                '&'.join(f'{k}={v}' for k, v in q.items())).json()
        due = listed(self.owner, credit='1')
        self.assertIn(credit['invoice_id'], [b['id'] for b in due])
        self.assertTrue(all(b['outstanding'] > 0 for b in due), 'credit filter shows only bills with money due')
        for term in (credit['invoice_number'], 'Lata', '98123'):
            with self.subTest(term=term):
                self.assertEqual([b['id'] for b in listed(self.owner, q=term)], [credit['invoice_id']])
        self.assertEqual(listed(self.cashier2, q='Lata'), [], "a cashier's search still covers only their own bills")
        self.assertEqual(listed(self.owner, q='no-such-bill'), [])

    def test_customer_list_is_complete_with_totals(self):
        for n in range(105):
            self.owner.post('/api/customers', {'name': f'Zz Bulk {n:03d}'})
        pid = self.product(price=100)
        self.sell(self.cashier, pid, qty=2, payments=[{'mode': 'Cash', 'amount': 50}, {'mode': 'Credit', 'amount': 150}],
                  customer_name='Zz Bulk 104')
        everyone = self.owner.get('/api/customers/all').json()
        names = [c['name'] for c in everyone]
        self.assertGreaterEqual(len(names), 105, 'not cut off at 100')
        self.assertIn('Zz Bulk 104', names)
        last = next(c for c in everyone if c['name'] == 'Zz Bulk 104')
        self.assertEqual((last['bills'], last['total_bought'], last['outstanding']), (1, 200, 150))
        self.assertEqual(self.manager.get('/api/customers/all').status, 200)

    def test_dues_say_which_bills_can_be_edited(self):
        pid = self.product(price=100)
        sale = self.sell(self.cashier, pid, qty=2, payments=[{'mode': 'Credit', 'amount': 200}], customer_name='Edit Me').json()
        bill = lambda: next(b for c in self.owner.get('/api/dues').json()['customers'] for b in c['bills'] if b['id'] == sale['invoice_id'])
        self.assertEqual(bill()['returned_amount'], 0)
        item = self.manager.get(f"/api/invoices/{sale['invoice_id']}").json()['items'][0]
        self.manager.post('/api/returns', {'invoice_id': sale['invoice_id'], 'items': [{'invoice_item_id': item['id'], 'qty': 1}]})
        self.assertEqual(bill()['returned_amount'], 100, 'a bill with a return is marked, so Edit is not offered')


class ListExportTests(RoleTestCase):
    BODY = {'title': 'Customers', 'headers': ['Customer', 'Phone', 'Due'],
            'rows': [['Asha', '9800000001', 150.5], ['=HYPERLINK("http://evil")', '', 0]]}

    def post_export(self, client, body=None):
        return client.request('POST', '/api/export/list.xlsx', raw=json.dumps(body or self.BODY).encode(),
                              headers={'Content-Type': 'application/json'})

    def test_only_people_with_the_permission_can_export(self):
        for role, client in self.clients.items():
            with self.subTest(role=role):
                expected = 200 if role == 'OWNER' else 403  # only the owner by default; given to others per person
                self.assertEqual(self.post_export(client).status, expected)
        # The owner can give it to one person, of any role.
        extra = self.user('exportcashier', 'CASHIER')
        preset = set(extra.get('/api/me').json()['user']['permissions'])
        self.assertEqual(self.post_export(extra).status, 403)
        self.owner.post(f'/api/users/{extra.user_id}', {'permissions': sorted(preset | {'lists.export'})})
        extra.login('exportcashier', 'password12')
        self.assertEqual(self.post_export(extra).status, 200)

    def test_export_is_a_real_sheet_with_text_kept_as_text(self):
        import io
        from openpyxl import load_workbook
        res = self.post_export(self.owner)
        self.assertEqual(res.status, 200, res.body)
        self.assertIn('customers-', res.headers.get('Content-Disposition', ''))
        sheet = load_workbook(io.BytesIO(res.body)).active
        rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
        self.assertEqual(rows[0], ['Customer', 'Phone', 'Due'])
        self.assertEqual(rows[1], ['Asha', '9800000001', 150.5], 'amounts stay numbers')
        self.assertTrue(str(rows[2][0]).startswith("'="), 'a formula-looking cell is written as text')
        audit = self.owner.get('/api/audit?start=1900-01-01&end=2999-12-31').json()
        entries = audit if isinstance(audit, list) else audit.get('entries', [])
        self.assertTrue(any(e['action'] == 'List exported' for e in entries), 'exports are audit-logged')

    def test_bad_or_huge_exports_are_refused(self):
        self.assertEqual(self.post_export(self.owner, {'title': 'x', 'headers': [], 'rows': []}).status, 400)
        self.assertEqual(self.post_export(self.owner, {'title': 'x', 'headers': ['a'] * 41, 'rows': []}).status, 400)

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

    def test_theme_setting(self):
        self.assertEqual(self.cashier.get('/api/me').json()['limits']['theme'], 'classic')
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'theme': 'neon'}}).status, 400)
        self.assertEqual(self.manager.post('/api/settings', {'settings': {'theme': 'royal'}}).status, 403)
        self.assertEqual(self.owner.post('/api/settings', {'settings': {'theme': 'Royal'}}).status, 200)
        self.assertEqual(self.cashier.get('/api/me').json()['limits']['theme'], 'royal')
        self.owner.post('/api/settings', {'settings': {'theme': 'classic'}})


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



class InsightTests(RoleTestCase):
    """The dashboard's analytics: sections by permission, own-bills scope, profit hiding, period handling."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        owner_client = cls.owner
        res = owner_client.post('/api/products', {'sku': 'INS-1', 'name': 'Insight Rocket', 'category': 'Rockets', 'unit_price': 100,
                                                  'opening_stock': 100, 'cost_price': 60})
        cls.pid = res.json()['id']
        # Never sold, with a lot of stock: must top the slow-movers list.
        cls.dud = owner_client.post('/api/products', {'sku': 'INS-DUD', 'name': 'Insight Dud', 'category': 'Rockets', 'unit_price': 50,
                                                      'opening_stock': 1000, 'cost_price': 30}).json()['id']
        for client, qty in ((cls.clients['CASHIER'], 2), (cls.clients['CASHIER'], 1), (cls.cashier2, 4), (cls.owner, 3)):
            sale = client.post('/api/sales', {'items': [{'product_id': cls.pid, 'qty': qty}], 'payments': [{'mode': 'UPI', 'amount': 100 * qty}]})
            assert sale.status == 200, sale.body

    def test_owner_sees_every_section(self):
        d = self.owner.get('/api/insights?preset=today').json()
        self.assertEqual(d['scope'], 'all')
        self.assertEqual(set(d) - {'period', 'scope'}, {'sales', 'products', 'customers', 'team', 'stock', 'finance'})
        k = d['sales']['kpi']
        self.assertEqual((k['sales'], k['bills'], k['items']), (1000, 4, 10))
        self.assertEqual((k['cogs'], k['gross_profit'], k['gross_margin']), (600, 400, 40))
        self.assertEqual(d['period']['days'], 1)
        self.assertEqual(len(d['sales']['hourly']), 24)
        self.assertEqual(sum(h['sales'] for h in d['sales']['hourly']), 1000)
        self.assertEqual(sum(c['bills'] for c in d['sales']['heatmap']), 4)
        self.assertEqual(d['sales']['payments'], [{'mode': 'UPI', 'amount': 1000, 'bills': 4}])
        self.assertEqual(sum(b['bills'] for b in d['sales']['bill_sizes']), 4)
        self.assertEqual(d['products']['top'][0]['category'], 'Rockets')
        self.assertEqual(d['products']['categories'][0]['share'], 100)
        staff = {row['name']: row for row in d['team']['staff']}
        self.assertEqual(staff['Cashier One']['sales'], 300)
        self.assertEqual(staff['cashier2']['bills'], 1)
        self.assertEqual(d['finance']['pnl']['net_profit'], 400 - d['finance']['pnl']['expenses'])
        self.assertEqual([t['key'] for t in d['finance']['targets']], ['daily', 'weekly', 'monthly', 'seasonal'])
        self.assertIn('dues_aging', d['customers'])
        self.assertIn('inventory_cost', d['stock']['totals'])

    def test_slow_movers_include_unsold_products(self):
        slow = self.owner.get('/api/insights?preset=today').json()['products']['slow_movers']
        self.assertEqual(slow[0]['sku'], 'INS-DUD')
        self.assertEqual((slow[0]['qty'], slow[0]['stock'], slow[0]['last_sale']), (0, 1000, None))
        sold = [row['qty'] for row in slow]
        self.assertEqual(sold, sorted(sold))  # fewest sold first
        self.assertEqual({row['qty'] for row in slow if row['sku'] == 'INS-1'} - {10}, set())
        # A cashier's view counts only their own bills, and the unsold product still tops the list.
        own = self.cashier.get('/api/insights?preset=today').json()['products']['slow_movers']
        self.assertEqual(own[0]['sku'], 'INS-DUD')
        self.assertEqual({row['qty'] for row in own if row['sku'] == 'INS-1'} - {3}, set())

    def test_trend_is_filled_and_compared(self):
        d = self.owner.get('/api/insights?preset=7d').json()
        trend = d['sales']['trend']
        self.assertEqual(len(trend), 7)
        self.assertEqual(trend[-1]['sales'], 1000)
        self.assertEqual(sum(t['sales'] for t in trend[:-1]), 0)
        self.assertEqual(trend[0]['prev_day'], d['period']['prev_start'])
        self.assertEqual(d['sales']['previous']['sales'], 0)

    def test_cashier_sees_only_own_bills(self):
        d = self.cashier.get('/api/insights?preset=7d').json()
        self.assertEqual(d['scope'], 'own')
        self.assertEqual(set(d) - {'period', 'scope'}, {'sales', 'products'})
        self.assertEqual((d['sales']['kpi']['sales'], d['sales']['kpi']['bills']), (300, 2))
        self.assertEqual(d['products']['top'][0]['qty'], 3)
        self.assertFalse(keys_deep(d) & PROFIT_KEYS)

    def test_manager_gets_team_but_no_profit(self):
        d = self.manager.get('/api/insights?preset=month').json()
        self.assertIn('team', d)
        self.assertEqual(d['sales']['kpi']['sales'], 1000)
        self.assertFalse(keys_deep(d) & PROFIT_KEYS)
        self.assertNotIn('cogs', d['finance']['pnl'])
        accountant = self.clients['ACCOUNTANT'].get('/api/insights?preset=month').json()
        self.assertEqual(accountant['finance']['pnl']['gross_profit'], 400)

    def test_periods(self):
        for preset in ('today', 'yesterday', '7d', '30d', 'month', 'last_month', 'season'):
            with self.subTest(preset=preset):
                d = self.owner.get(f'/api/insights?preset={preset}').json()
                self.assertLessEqual(d['period']['start'], d['period']['end'])
                self.assertLess(d['period']['prev_end'], d['period']['start'])
                self.assertEqual(len(d['sales']['trend']), d['period']['days'])
        custom = self.owner.get('/api/insights?start=2024-01-01&end=2024-01-31').json()
        self.assertEqual((custom['period']['days'], custom['period']['prev_start'], custom['period']['prev_end']), (31, '2023-12-01', '2023-12-31'))
        self.assertEqual(self.owner.get('/api/insights?preset=forever').status, 400)
        self.assertEqual(self.owner.get('/api/insights?start=2024-02-01&end=2024-01-01').status, 400)
        self.assertEqual(self.owner.get('/api/insights?start=2020-01-01&end=2024-01-01').status, 400)
        self.assertEqual(self.owner.get('/api/insights?start=nope').status, 400)
        self.assertEqual(self.clients['STOCK_KEEPER'].get('/api/insights').status, 403)


if __name__ == '__main__':
    unittest.main()
