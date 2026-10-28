from crm.repositories.base import Repository

STOCK_SQL = 'COALESCE((SELECT SUM(m.qty_base) FROM inventory_movements m WHERE m.product_id=p.id), 0)'


class ProductRepository(Repository):
    def list(self, status='ACTIVE', query='', category='', limit=200):
        where, params = ['p.status=?'], [status]
        if query:
            where.append('(p.name LIKE ? OR p.sku LIKE ? OR p.barcode LIKE ? OR p.category LIKE ? OR p.brand LIKE ?)')
            params += [f'%{query}%'] * 5
        if category:
            where.append('p.category=?')
            params.append(category)
        sql = f'SELECT p.*, {STOCK_SQL} AS current_stock_base FROM products p WHERE {" AND ".join(where)} ORDER BY p.name LIMIT ?'
        return self.all(sql, params + [limit])

    def get(self, product_id):
        return self.one(f'SELECT p.*, {STOCK_SQL} AS current_stock_base FROM products p WHERE p.id=?', (product_id,))

    def get_active(self, product_id):
        return self.one(f"SELECT p.*, {STOCK_SQL} AS current_stock_base FROM products p WHERE p.id=? AND p.status='ACTIVE'", (product_id,))

    def sku_exists(self, sku):
        return self.scalar('SELECT 1 FROM products WHERE sku=?', (sku,)) is not None

    def categories(self):
        rows = self.all("SELECT DISTINCT category FROM products WHERE status='ACTIVE' AND category IS NOT NULL AND category<>'' ORDER BY category")
        return [row['category'] for row in rows]

    def create(self, values):
        return self.insert('products', values)

    def set_unit_price(self, product_id, price, updated_at):
        self.execute('UPDATE products SET default_unit_price=?, updated_at=? WHERE id=?', (price, updated_at, product_id))

    def set_cost_price(self, product_id, cost, updated_at):
        self.execute('UPDATE products SET cost_price=?, updated_at=? WHERE id=?', (cost, updated_at, product_id))

    def update(self, product_id, values):
        assignments = ', '.join(f'{column}=?' for column in values)
        self.execute(f'UPDATE products SET {assignments} WHERE id=?', (*values.values(), product_id))

    def barcode_owner(self, barcode):
        return self.scalar('SELECT id FROM products WHERE barcode=?', (barcode,))

    def set_status(self, product_id, status, updated_at):
        self.execute('UPDATE products SET status=?, updated_at=? WHERE id=?', (status, updated_at, product_id))

    def transaction_references(self, product_id):
        return self.scalar('''SELECT (SELECT COUNT(*) FROM invoice_items WHERE product_id=?)
                                   + (SELECT COUNT(*) FROM purchase_items WHERE product_id=?)
                                   + (SELECT COUNT(*) FROM return_items WHERE product_id=?)''', (product_id,) * 3, default=0)

    def delete(self, product_id):
        for table in ('stock_batches', 'inventory_movements', 'price_versions'):
            self.execute(f'DELETE FROM {table} WHERE product_id=?', (product_id,))
        self.execute('DELETE FROM products WHERE id=?', (product_id,))

    def price_history(self, product_id):
        return self.all('SELECT * FROM price_versions WHERE product_id=? ORDER BY effective_date DESC, id DESC', (product_id,))

    def last_sale_date(self, product_id):
        return self.scalar('''SELECT MAX(i.invoice_date) FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                              WHERE ii.product_id=? AND i.status='FINALIZED' ''', (product_id,))

    def last_purchase_date(self, product_id):
        return self.scalar('SELECT MAX(p.purchase_date) FROM purchase_items pi JOIN purchases p ON p.id=pi.purchase_id WHERE pi.product_id=?', (product_id,))
