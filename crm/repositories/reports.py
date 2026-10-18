from crm.repositories.base import Repository
from crm.repositories.products import STOCK_SQL

FINALIZED_IN_RANGE = "i.invoice_date BETWEEN ? AND ? AND i.status='FINALIZED'"


class ReportRepository(Repository):
    def sales_totals(self, start, end):
        return self.one(f'''SELECT COALESCE(SUM(grand_total), 0) AS sales, COUNT(*) AS bills, COALESCE(AVG(grand_total), 0) AS avg_bill,
                                   COALESCE(SUM(discount), 0) AS discounts, COALESCE(SUM(amount_received), 0) AS received,
                                   COALESCE(SUM(outstanding), 0) AS credit
                            FROM invoices i WHERE {FINALIZED_IN_RANGE}''', (start, end))

    def cost_of_goods(self, start, end):
        return self.scalar(f'''SELECT COALESCE(SUM(ii.cost_snapshot * ii.qty_input), 0)
                               FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE {FINALIZED_IN_RANGE}''', (start, end), default=0)

    def hourly(self, start, end):
        return self.all(f'''SELECT substr(i.finalized_at, 12, 2) AS hr, ROUND(SUM(i.grand_total), 2) AS sales, COUNT(*) AS bills,
                                   ROUND(AVG(i.grand_total), 2) AS avg_bill
                            FROM invoices i WHERE {FINALIZED_IN_RANGE} GROUP BY hr ORDER BY hr''', (start, end))

    def top_products(self, start, end, limit=20):
        return self.all(f'''SELECT ii.product_name_snapshot AS name, ii.sku_snapshot AS sku, ROUND(SUM(ii.qty_input), 2) AS qty,
                                   ROUND(SUM(ii.taxable_amount), 2) AS revenue,
                                   ROUND(SUM(ii.taxable_amount - ii.cost_snapshot * ii.qty_input), 2) AS profit
                            FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE {FINALIZED_IN_RANGE}
                            GROUP BY ii.product_id ORDER BY revenue DESC LIMIT ?''', (start, end, limit))

    def categories(self, start, end):
        return self.all(f'''SELECT COALESCE(NULLIF(p.category, ''), 'Uncategorised') AS category, ROUND(SUM(ii.taxable_amount), 2) AS revenue,
                                   ROUND(SUM(ii.qty_input), 2) AS qty, ROUND(SUM(ii.taxable_amount - ii.cost_snapshot * ii.qty_input), 2) AS profit
                            FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id JOIN products p ON p.id=ii.product_id
                            WHERE {FINALIZED_IN_RANGE} GROUP BY 1 ORDER BY revenue DESC''', (start, end))

    def payment_mix(self, start, end):
        return self.all(f'''SELECT pa.mode, ROUND(SUM(pa.amount), 2) AS amount FROM payments pa JOIN invoices i ON i.id=pa.invoice_id
                            WHERE {FINALIZED_IN_RANGE} GROUP BY pa.mode ORDER BY amount DESC''', (start, end))

    def customer_mix(self, start, end):
        return self.all(f'''SELECT i.customer_type_snapshot AS customer_type, ROUND(SUM(i.grand_total), 2) AS revenue, COUNT(*) AS bills,
                                   COUNT(DISTINCT i.customer_id) AS customers
                            FROM invoices i WHERE {FINALIZED_IN_RANGE} GROUP BY i.customer_type_snapshot''', (start, end))

    def slow_movers(self, start, end, limit=20):
        return self.all(f'''SELECT p.name, p.sku, ROUND({STOCK_SQL}, 2) AS stock,
                                   (SELECT MAX(i.invoice_date) FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                                    WHERE ii.product_id=p.id AND i.status='FINALIZED') AS last_sale,
                                   (SELECT COALESCE(SUM(ii.qty_input), 0) FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                                    WHERE ii.product_id=p.id AND {FINALIZED_IN_RANGE}) AS qty_sold
                            FROM products p WHERE p.status='ACTIVE' ORDER BY qty_sold ASC, stock DESC LIMIT ?''', (start, end, limit))

    def discounts(self, start, end):
        return self.one(f'''SELECT ROUND(COALESCE(SUM(discount), 0), 2) AS total_discount,
                                   ROUND(CASE WHEN COALESCE(SUM(subtotal), 0)=0 THEN 0 ELSE SUM(discount) / SUM(subtotal) * 100 END, 2) AS avg_discount
                            FROM invoices i WHERE {FINALIZED_IN_RANGE}''', (start, end))

    def low_stock(self, limit=10):
        rows = self.all(f'''SELECT p.name, p.sku, ROUND({STOCK_SQL}, 2) AS stock, ROUND(p.reorder_level, 2) AS reorder_level
                            FROM products p WHERE p.status='ACTIVE' AND {STOCK_SQL} <= p.reorder_level
                            ORDER BY stock ASC, p.name''')
        return len(rows), rows[:limit]

    def inventory_cost(self):
        return self.scalar(f"SELECT COALESCE(SUM(p.cost_price * {STOCK_SQL}), 0) FROM products p WHERE p.status='ACTIVE'", default=0)

    def dues(self):
        """Finalized bills with credit still outstanding, oldest first."""
        return self.all('''SELECT i.id, i.invoice_number, i.invoice_date, i.customer_id, i.customer_name_snapshot, c.phone AS customer_phone,
                                  i.grand_total, i.amount_received, i.outstanding
                           FROM invoices i LEFT JOIN customers c ON c.id=i.customer_id
                           WHERE i.status='FINALIZED' AND i.outstanding > 0.009 ORDER BY i.invoice_date, i.id''')

    def quantity_sold_by_product(self, start, end):
        rows = self.all(f'''SELECT ii.product_id, SUM(ii.qty_input) AS qty FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                            WHERE {FINALIZED_IN_RANGE} GROUP BY ii.product_id''', (start, end))
        return {row['product_id']: row['qty'] for row in rows}

    def stored_explosive_kg(self):
        return self.scalar(f"SELECT COALESCE(SUM(p.explosive_kg * MAX({STOCK_SQL}, 0)), 0) FROM products p", default=0)
