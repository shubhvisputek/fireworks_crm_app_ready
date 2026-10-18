"""Database schema and forward-only migrations.

The base schema matches the original single-file app so existing databases keep
working. Later changes are numbered migrations recorded in schema_migrations.
Several product pricing columns are legacy (from an earlier tax/tiered-price
design); they are kept so old data stays readable but are no longer used.
"""
import json

BASE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'OWNER', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS business_settings (
  id INTEGER PRIMARY KEY CHECK(id=1), data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT, subcategory TEXT,
  unit TEXT NOT NULL DEFAULT 'piece', units_per_box REAL NOT NULL DEFAULT 1, boxes_per_carton REAL NOT NULL DEFAULT 1,
  units_per_carton REAL NOT NULL DEFAULT 1, brand TEXT, hsn TEXT, gst_rate REAL NOT NULL DEFAULT 0,
  cess_rate REAL NOT NULL DEFAULT 0, reorder_level REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
  barcode TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_versions (
  id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), effective_date TEXT NOT NULL,
  mrp REAL NOT NULL DEFAULT 0, retail_price REAL NOT NULL DEFAULT 0, wholesale_price REAL NOT NULL DEFAULT 0,
  cost_price REAL NOT NULL DEFAULT 0, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_product_date ON price_versions(product_id, effective_date, id);
CREATE TABLE IF NOT EXISTS stock_batches (
  id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), batch_number TEXT, supplier TEXT,
  manufacturer TEXT, manufacture_date TEXT, purchase_date TEXT, qty_base REAL NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0, location TEXT, notes TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_movements (
  id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), movement_type TEXT NOT NULL,
  qty_base REAL NOT NULL, unit_cost REAL, ref_type TEXT, ref_id INTEGER, reason TEXT, user_id INTEGER,
  batch_id INTEGER REFERENCES stock_batches(id), created_at TEXT NOT NULL, notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_product_date ON inventory_movements(product_id, created_at);
CREATE TABLE IF NOT EXISTS suppliers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT, gstin TEXT, address TEXT, notes TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY, purchase_number TEXT UNIQUE NOT NULL, purchase_date TEXT NOT NULL, supplier_id INTEGER REFERENCES suppliers(id),
  supplier_name TEXT, invoice_number TEXT, subtotal REAL NOT NULL DEFAULT 0, gst REAL NOT NULL DEFAULT 0,
  freight REAL NOT NULL DEFAULT 0, total REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'POSTED', user_id INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_items (
  id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL REFERENCES purchases(id), product_id INTEGER NOT NULL REFERENCES products(id),
  qty_input REAL NOT NULL, sell_unit TEXT NOT NULL, qty_base REAL NOT NULL, cost_price REAL NOT NULL, gst_rate REAL NOT NULL,
  gst_amount REAL NOT NULL, batch_number TEXT, batch_id INTEGER REFERENCES stock_batches(id)
);
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY, customer_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, phone TEXT, address TEXT, gstin TEXT,
  customer_type TEXT NOT NULL DEFAULT 'RETAIL', credit_enabled INTEGER NOT NULL DEFAULT 0, credit_limit REAL NOT NULL DEFAULT 0,
  state_code TEXT, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_customer_phone ON customers(phone);
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY, invoice_number TEXT UNIQUE, invoice_date TEXT NOT NULL, customer_id INTEGER REFERENCES customers(id),
  customer_name_snapshot TEXT NOT NULL, customer_type_snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT',
  pricing_mode TEXT NOT NULL DEFAULT 'RETAIL', subtotal REAL NOT NULL DEFAULT 0, discount REAL NOT NULL DEFAULT 0,
  taxable_amount REAL NOT NULL DEFAULT 0, cgst REAL NOT NULL DEFAULT 0, sgst REAL NOT NULL DEFAULT 0, igst REAL NOT NULL DEFAULT 0,
  cess REAL NOT NULL DEFAULT 0, grand_total REAL NOT NULL DEFAULT 0, amount_received REAL NOT NULL DEFAULT 0,
  outstanding REAL NOT NULL DEFAULT 0, user_id INTEGER, notes TEXT, created_at TEXT NOT NULL, finalized_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_invoice_date_status ON invoices(invoice_date, status);
CREATE TABLE IF NOT EXISTS invoice_items (
  id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id), product_id INTEGER NOT NULL REFERENCES products(id),
  sku_snapshot TEXT NOT NULL, product_name_snapshot TEXT NOT NULL, hsn_snapshot TEXT, qty_input REAL NOT NULL, sell_unit TEXT NOT NULL,
  qty_base REAL NOT NULL, unit_price REAL NOT NULL, original_price REAL NOT NULL, discount REAL NOT NULL,
  taxable_amount REAL NOT NULL, gst_rate REAL NOT NULL, cess_rate REAL NOT NULL, gst_amount REAL NOT NULL,
  cost_snapshot REAL NOT NULL, manual_override_reason TEXT
);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id), customer_id INTEGER REFERENCES customers(id),
  payment_date TEXT NOT NULL, mode TEXT NOT NULL, amount REAL NOT NULL, reference TEXT, notes TEXT, user_id INTEGER, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
CREATE TABLE IF NOT EXISTS returns (
  id INTEGER PRIMARY KEY, return_number TEXT UNIQUE NOT NULL, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  customer_id INTEGER REFERENCES customers(id), return_date TEXT NOT NULL, reason TEXT, total_refund REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'POSTED', user_id INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS return_items (
  id INTEGER PRIMARY KEY, return_id INTEGER NOT NULL REFERENCES returns(id), invoice_item_id INTEGER NOT NULL REFERENCES invoice_items(id),
  product_id INTEGER NOT NULL REFERENCES products(id), qty_input REAL NOT NULL, qty_base REAL NOT NULL, refund_amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY, expense_date TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, payment_mode TEXT NOT NULL,
  vendor TEXT, notes TEXT, attachment_name TEXT, recurring INTEGER NOT NULL DEFAULT 0, user_id INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recurring_expenses (
  id INTEGER PRIMARY KEY, category TEXT NOT NULL, amount REAL NOT NULL, payment_mode TEXT NOT NULL, vendor TEXT,
  frequency TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT, active INTEGER NOT NULL DEFAULT 1, notes TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS held_bills (
  id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, customer_id INTEGER REFERENCES customers(id), customer_name TEXT,
  pricing_mode TEXT NOT NULL, items_json TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL, user_id INTEGER
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, entity_type TEXT, entity_id INTEGER,
  previous_json TEXT, new_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS targets (
  id INTEGER PRIMARY KEY CHECK(id=1), daily REAL DEFAULT 500000, weekly REAL DEFAULT 3000000,
  monthly REAL DEFAULT 10000000, seasonal REAL DEFAULT 30000000, season_start TEXT, season_end TEXT
);
CREATE TABLE IF NOT EXISTS sequence (
  key TEXT PRIMARY KEY, value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
'''


def _columns(conn, table):
    return {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _add_missing_columns(conn, table, columns):
    existing = _columns(conn, table)
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def _m1_product_prices(conn):
    """Flat product prices; backfill from the latest legacy price version."""
    _add_missing_columns(conn, 'products', {
        'cost_price': 'REAL NOT NULL DEFAULT 0', 'mrp': 'REAL NOT NULL DEFAULT 0',
        'retail_selling_price': 'REAL NOT NULL DEFAULT 0', 'wholesale_selling_price': 'REAL NOT NULL DEFAULT 0',
        'default_unit_price': 'REAL NOT NULL DEFAULT 0',
    })
    latest = 'SELECT {col} FROM price_versions pv WHERE pv.product_id=products.id ORDER BY effective_date DESC, id DESC LIMIT 1'
    conn.execute(f'''
        UPDATE products SET
          cost_price=COALESCE(({latest.format(col='cost_price')}),0),
          mrp=COALESCE(({latest.format(col='mrp')}),0),
          retail_selling_price=COALESCE(({latest.format(col='retail_price')}),0),
          wholesale_selling_price=COALESCE(({latest.format(col='wholesale_price')}),0),
          default_unit_price=COALESCE(({latest.format(col='retail_price')}),0)
        WHERE cost_price=0 AND mrp=0 AND retail_selling_price=0 AND wholesale_selling_price=0 AND default_unit_price=0
    ''')


def _m2_session_versions(conn):
    _add_missing_columns(conn, 'users', {'session_version': 'INTEGER NOT NULL DEFAULT 0'})


def _m3_invoice_revisions(conn):
    _add_missing_columns(conn, 'invoices', {
        'revised_from_id': 'INTEGER', 'revised_to_id': 'INTEGER', 'revision_reason': 'TEXT',
        'edited_by': 'INTEGER', 'edited_at': 'TEXT', 'voided_by': 'INTEGER', 'voided_at': 'TEXT',
    })


def _m4_indexes(conn):
    conn.execute('CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_invoice_items_product ON invoice_items(product_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_return_items_item ON return_items(invoice_item_id)')


MIGRATIONS = [(1, _m1_product_prices), (2, _m2_session_versions), (3, _m3_invoice_revisions), (4, _m4_indexes)]

DEFAULT_SETTINGS = {
    'business_name': 'Shree Ganesh Fireworks', 'address': 'Pune, Maharashtra, India', 'gstin': '', 'license_number': '',
    'phone': '', 'email': '', 'logo': '', 'state': 'Maharashtra', 'state_code': '27', 'invoice_prefix': 'FW',
    'negative_stock_allowed': False, 'batch_tracking': True, 'default_gst_rate': 0, 'default_cess_rate': 0,
    'invoice_footer': 'Thank you for shopping with us.', 'walk_in_name': 'Walk-in Customer',
}


def migrate(conn, now_iso, today):
    """Create the schema, apply pending migrations and seed singleton rows."""
    conn.executescript(BASE_SCHEMA)
    applied = {row['version'] for row in conn.execute('SELECT version FROM schema_migrations').fetchall()}
    for version, step in MIGRATIONS:
        if version in applied:
            continue
        conn.execute('BEGIN IMMEDIATE')
        try:
            step(conn)
            conn.execute('INSERT INTO schema_migrations(version, applied_at) VALUES(?,?)', (version, now_iso))
            conn.execute('COMMIT')
        except BaseException:
            conn.execute('ROLLBACK')
            raise
    if not conn.execute('SELECT 1 FROM business_settings WHERE id=1').fetchone():
        conn.execute('INSERT INTO business_settings(id, data_json) VALUES(1, ?)', (json.dumps(DEFAULT_SETTINGS),))
    if not conn.execute('SELECT 1 FROM targets WHERE id=1').fetchone():
        conn.execute('INSERT INTO targets(id, daily, weekly, monthly, seasonal, season_start, season_end) VALUES(1, 500000, 3000000, 10000000, 30000000, ?, ?)',
                     (f'{today.year}-10-01', f'{today.year}-10-31'))
    for key in ('invoice', 'purchase', 'return', 'customer'):
        conn.execute('INSERT OR IGNORE INTO sequence(key, value) VALUES(?, 0)', (key,))
