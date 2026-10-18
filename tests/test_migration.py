"""An existing database written by the previous single-file server must open cleanly."""
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

from tests.support import ROOT, ServerProcess

LEGACY_COMMIT = '504d2be'  # last commit of the single-file server.py


def legacy_server_source():
    try:
        return subprocess.run(['git', 'show', f'{LEGACY_COMMIT}:server.py'], cwd=ROOT, capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


@unittest.skipUnless(legacy_server_source(), 'legacy server.py not available in git history')
class LegacyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='fwcrm-legacy-')
        self.db = os.path.join(self.tmp, 'fireworks.db')
        legacy_dir = os.path.join(self.tmp, 'legacy')
        os.makedirs(legacy_dir)
        with open(os.path.join(legacy_dir, 'legacy_server.py'), 'wb') as handle:
            handle.write(legacy_server_source())
        # Build a database with the old code: schema, admin, demo products, sales, payments and returns.
        script = (
            'import os, legacy_server as s\n'
            's.init_db(); s.seed_demo()\n'
        )
        env = {**os.environ, 'FIREWORKS_DB': self.db, 'FIREWORKS_SECRET': os.path.join(self.tmp, '.secret')}
        subprocess.run(['python3', '-c', script], cwd=legacy_dir, env=env, check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_server_reads_legacy_data(self):
        conn = sqlite3.connect(self.db)
        old_invoices = conn.execute("SELECT COUNT(*) FROM invoices WHERE status='FINALIZED'").fetchone()[0]
        old_products = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        conn.close()
        self.assertGreater(old_invoices, 0)

        server = ServerProcess(env={'FIREWORKS_DB': self.db, 'FIREWORKS_SECRET': os.path.join(self.tmp, '.secret')}).start()
        try:
            admin = server.client()
            self.assertEqual(admin.login('admin', 'admin123').status, 200)
            invoices = admin.get('/api/invoices?start=1900-01-01&end=2999-12-31').json()
            self.assertEqual(len(invoices), min(old_invoices, 500))
            self.assertTrue(all(i['billed_by_name'] == 'admin' for i in invoices))
            products = admin.get('/api/products?limit=500').json()
            self.assertEqual(len(products), old_products)
            self.assertTrue(all(p['default_unit_price'] > 0 for p in products))
            detail = admin.get(f"/api/invoices/{invoices[0]['id']}").json()
            self.assertTrue(detail['items'])
            self.assertEqual(admin.get(f"/api/invoice-pdf/{invoices[0]['id']}").status, 200)
            self.assertEqual(admin.get('/api/analytics?preset=month').status, 200)
            sale = admin.post('/api/sales', {'items': [{'product_id': products[0]['id'], 'qty': 1}],
                                             'payments': [{'mode': 'Cash', 'amount': products[0]['default_unit_price']}]})
            self.assertEqual(sale.status, 200, sale.body)
        finally:
            server.stop()
        conn = sqlite3.connect(self.db)
        versions = [row[0] for row in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
        conn.close()
        self.assertEqual(versions, [1, 2, 3, 4])


if __name__ == '__main__':
    unittest.main()
