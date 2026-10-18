"""In-process tests of business rules, using a throwaway database."""
import datetime as dt
import os
import shutil
import tempfile
import unittest

from crm.clock import Clock, resolve_timezone
from crm.config import Config
from crm.domain.money import allocate_discount, money
from crm.errors import ValidationError
from crm.web.app import Application


class FixedClock(Clock):
    def __init__(self, moment):
        super().__init__('Asia/Kolkata')
        self.moment = moment

    def now(self):
        return self.moment.astimezone(self.tz)


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='fwcrm-unit-')
        config = Config(db_path=os.path.join(self.tmp, 'db.sqlite'), secret_path=os.path.join(self.tmp, '.secret'),
                        static_dir=self.tmp)
        self.app = Application(config)
        self.app.initialize()
        self.conn = self.app.db.connect()
        self.services = self.app.services(self.conn)
        self.admin = self.services.repos.users.get_active_by_username('admin')

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def product(self, price=100, stock=10, cost=0, **extra):
        sku = extra.pop('sku', f'P-{len(self.services.catalog.list_products(limit=500)) + 1}')
        return self.services.catalog.create_product(self.admin, {'sku': sku, 'name': sku, 'unit_price': price, 'opening_stock': stock,
                                                                 'cost_price': cost, **extra})

    def sell(self, items, payments, **extra):
        return self.services.sales.create_sale(self.admin, {'items': items, 'payments': payments, **extra})


class MoneyTests(unittest.TestCase):
    def test_rounding_half_up(self):
        self.assertEqual(money(2.675), 2.68)
        self.assertEqual(money(None), 0.0)

    def test_discount_shares_add_up_exactly(self):
        shares = allocate_discount(10, [33.33, 33.33, 33.34])
        self.assertAlmostEqual(sum(shares), 10.0, places=9)
        self.assertEqual(allocate_discount(0, [10, 20]), [0.0, 0.0])
        self.assertEqual(allocate_discount(5, [0, 0]), [0.0, 0.0])


class ClockTests(unittest.TestCase):
    def test_business_day_uses_shop_timezone(self):
        # 20:00 UTC on 1 Oct is 01:30 on 2 Oct in India: the bill belongs to 2 Oct.
        clock = FixedClock(dt.datetime(2026, 10, 1, 20, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(clock.today_iso(), '2026-10-02')
        self.assertTrue(clock.now_iso().endswith('+05:30'))

    def test_unknown_timezone_falls_back_safely(self):
        self.assertEqual(resolve_timezone('Not/AZone'), dt.timezone.utc)


class SalesRuleTests(ServiceTestCase):
    def test_cost_of_goods_and_profit(self):
        pid = self.product(price=100, stock=10, cost=60)
        self.sell([{'product_id': pid, 'qty': 2}], [{'mode': 'Cash', 'amount': 200}])
        kpi = self.services.reports.sales_kpis(self.services.sales.today(), self.services.sales.today())
        self.assertEqual((kpi['sales'], kpi['cogs'], kpi['gross_profit'], kpi['gross_margin']), (200, 120, 80, 40))

    def test_purchase_updates_cost_price(self):
        pid = self.product(price=100, stock=0, cost=50)
        self.services.inventory.record_purchase(self.admin, {'items': [{'product_id': pid, 'qty': 5, 'cost_price': 70}]})
        self.assertEqual(self.services.catalog.product_detail(pid)['product']['cost_price'], 70)

    def test_same_product_on_two_lines_cannot_oversell(self):
        pid = self.product(price=10, stock=3)
        with self.assertRaisesRegex(ValidationError, 'Insufficient stock'):
            self.sell([{'product_id': pid, 'qty': 2}, {'product_id': pid, 'qty': 2}], [{'mode': 'Cash', 'amount': 40}])
        self.assertEqual(self.services.repos.inventory.stock(pid), 3)

    def test_invoice_prefix_setting_is_used(self):
        self.services.settings.update(self.admin, {'settings': {'invoice_prefix': 'sg/fw'}})
        pid = self.product()
        _id, number = self.sell([{'product_id': pid, 'qty': 1}], [{'mode': 'Cash', 'amount': 100}])
        self.assertTrue(number.startswith('SGFW-'), number)

    def test_failed_sale_leaves_no_trace(self):
        pid = self.product(price=10, stock=5)
        with self.assertRaises(ValidationError):
            self.sell([{'product_id': pid, 'qty': 1}], [{'mode': 'Cash', 'amount': 10}], customer_name='Ghost', customer_phone='9999999999',
                      discount=50)
        self.assertEqual(self.services.customers.search('Ghost'), [])
        self.assertEqual(self.services.repos.invoices.list('1900-01-01', '2999-12-31'), [])

    def test_customer_codes_are_sequential_and_skip_taken(self):
        self.services.customers.create(self.admin, {'name': 'Legacy', 'customer_code': 'CUST-00001'})
        new_id = self.services.customers.create(self.admin, {'name': 'New'})
        self.assertEqual(self.services.repos.customers.get(new_id)['customer_code'], 'CUST-00002')


class SettingsRuleTests(ServiceTestCase):
    def test_unknown_keys_ignored_and_types_enforced(self):
        self.services.settings.update(self.admin, {'settings': {'business_name': 'A', 'evil_key': 'x', 'negative_stock_allowed': 'yes'}})
        settings = self.services.settings.get_settings()
        self.assertNotIn('evil_key', settings)
        self.assertIs(settings['negative_stock_allowed'], True)
        with self.assertRaises(ValidationError):
            self.services.settings.update(self.admin, {'settings': {'business_name': ''}})
        with self.assertRaises(ValidationError):
            self.services.settings.update(self.admin, {'targets': {'season_start': '2026-10-31', 'season_end': '2026-10-01'}})

    def test_season_preset_follows_targets(self):
        self.services.settings.update(self.admin, {'targets': {'season_start': '2026-10-10', 'season_end': '2026-11-05'}})
        self.assertEqual(self.services.reports.resolve_preset('season'), ('2026-10-10', '2026-11-05'))


class DemoSeedTests(ServiceTestCase):
    def test_demo_seed_builds_consistent_data(self):
        self.services.demo.seed()
        products = self.services.catalog.list_products(limit=500)
        self.assertEqual(len(products), 35)
        self.assertTrue(all(p['current_stock_base'] >= 0 for p in products))
        today = self.services.sales.today()
        self.assertGreater(self.services.reports.sales_kpis(today, today)['gross_profit'], 0)


if __name__ == '__main__':
    unittest.main()
