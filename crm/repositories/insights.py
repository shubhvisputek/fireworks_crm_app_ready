"""Read-only queries behind the dashboard's analytics views.

Every sales query takes an optional ``user_id``: when given, only bills made by
that user count, so a cashier's dashboard shows their own performance.
"""
from crm.repositories.base import Repository
from crm.repositories.products import STOCK_SQL

BILL_SIZE_BUCKETS = [(0, 500, 'Under ₹500'), (500, 1000, '₹500–1k'), (1000, 2500, '₹1k–2.5k'),
                     (2500, 5000, '₹2.5k–5k'), (5000, 10000, '₹5k–10k'), (10000, None, '₹10k+')]


def _scope(start, end, user_id, alias='i'):
    sql = f"{alias}.invoice_date BETWEEN ? AND ? AND {alias}.status='FINALIZED'"
    params = [start, end]
    if user_id is not None:
        sql += f' AND {alias}.user_id=?'
        params.append(user_id)
    return sql, params


class InsightRepository(Repository):
    # ---- sales -------------------------------------------------------------
    def totals(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        row = self.one(f'''SELECT COALESCE(SUM(i.grand_total), 0) AS sales, COUNT(*) AS bills, COALESCE(AVG(i.grand_total), 0) AS avg_bill,
                                  COALESCE(SUM(i.discount), 0) AS discounts, COALESCE(SUM(i.subtotal), 0) AS gross_sales,
                                  COALESCE(SUM(i.outstanding), 0) AS credit, COUNT(DISTINCT i.customer_id) AS customers
                           FROM invoices i WHERE {where}''', params)
        row['cogs'] = self.scalar(f'''SELECT COALESCE(SUM(ii.cost_snapshot * ii.qty_input), 0) FROM invoice_items ii
                                      JOIN invoices i ON i.id=ii.invoice_id WHERE {where}''', params, default=0)
        row['items'] = self.scalar(f'''SELECT COALESCE(SUM(ii.qty_input), 0) FROM invoice_items ii
                                       JOIN invoices i ON i.id=ii.invoice_id WHERE {where}''', params, default=0)
        return row

    def daily(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT i.invoice_date AS day, ROUND(SUM(i.grand_total), 2) AS sales, COUNT(*) AS bills,
                                   ROUND(COALESCE(SUM((SELECT SUM(ii.cost_snapshot * ii.qty_input) FROM invoice_items ii
                                                       WHERE ii.invoice_id=i.id)), 0), 2) AS cogs
                            FROM invoices i WHERE {where} GROUP BY i.invoice_date ORDER BY i.invoice_date''', params)

    def weekday_hour(self, start, end, user_id=None):
        """Sales by weekday (0 = Sunday) and hour of finalisation."""
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT CAST(strftime('%w', i.invoice_date) AS INTEGER) AS weekday,
                                   CAST(substr(i.finalized_at, 12, 2) AS INTEGER) AS hour,
                                   ROUND(SUM(i.grand_total), 2) AS sales, COUNT(*) AS bills
                            FROM invoices i WHERE {where} AND i.finalized_at IS NOT NULL GROUP BY 1, 2''', params)

    def bill_sizes(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        cases = ' '.join(f"WHEN i.grand_total < {high} THEN {n}" for n, (_, high, _) in enumerate(BILL_SIZE_BUCKETS) if high)
        rows = self.all(f'''SELECT CASE {cases} ELSE {len(BILL_SIZE_BUCKETS) - 1} END AS bucket, COUNT(*) AS bills,
                                   ROUND(SUM(i.grand_total), 2) AS sales
                            FROM invoices i WHERE {where} GROUP BY 1''', params)
        found = {row['bucket']: row for row in rows}
        return [{'label': label, 'bills': found.get(n, {}).get('bills', 0), 'sales': found.get(n, {}).get('sales', 0)}
                for n, (_, _, label) in enumerate(BILL_SIZE_BUCKETS)]

    def payments(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT pa.mode, ROUND(SUM(pa.amount), 2) AS amount, COUNT(DISTINCT pa.invoice_id) AS bills
                            FROM payments pa JOIN invoices i ON i.id=pa.invoice_id
                            WHERE {where} GROUP BY pa.mode ORDER BY amount DESC''', params)

    # ---- products ----------------------------------------------------------
    def products(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT ii.product_id, ii.product_name_snapshot AS name, ii.sku_snapshot AS sku,
                                   COALESCE(NULLIF(p.category, ''), 'Uncategorised') AS category,
                                   ROUND(SUM(ii.qty_input), 2) AS qty, ROUND(SUM(ii.taxable_amount), 2) AS revenue,
                                   ROUND(SUM(ii.taxable_amount - ii.cost_snapshot * ii.qty_input), 2) AS profit,
                                   COUNT(DISTINCT i.id) AS bills
                            FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id LEFT JOIN products p ON p.id=ii.product_id
                            WHERE {where} GROUP BY ii.product_id ORDER BY revenue DESC''', params)

    def categories(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT COALESCE(NULLIF(p.category, ''), 'Uncategorised') AS category, ROUND(SUM(ii.taxable_amount), 2) AS revenue,
                                   ROUND(SUM(ii.qty_input), 2) AS qty, ROUND(SUM(ii.taxable_amount - ii.cost_snapshot * ii.qty_input), 2) AS profit
                            FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id LEFT JOIN products p ON p.id=ii.product_id
                            WHERE {where} GROUP BY 1 ORDER BY revenue DESC''', params)

    # ---- customers ---------------------------------------------------------
    def customer_types(self, start, end, user_id=None):
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT i.customer_type_snapshot AS customer_type, ROUND(SUM(i.grand_total), 2) AS revenue, COUNT(*) AS bills,
                                   COUNT(DISTINCT i.customer_id) AS customers
                            FROM invoices i WHERE {where} GROUP BY 1 ORDER BY revenue DESC''', params)

    def top_customers(self, start, end, user_id=None, limit=10):
        where, params = _scope(start, end, user_id)
        return self.all(f'''SELECT i.customer_id, MAX(i.customer_name_snapshot) AS name, MAX(i.customer_type_snapshot) AS customer_type,
                                   COUNT(*) AS bills, ROUND(SUM(i.grand_total), 2) AS revenue, ROUND(SUM(i.outstanding), 2) AS outstanding,
                                   MAX(i.invoice_date) AS last_visit
                            FROM invoices i WHERE {where} AND i.customer_id IS NOT NULL
                            GROUP BY i.customer_id ORDER BY revenue DESC LIMIT ?''', [*params, limit])

    def new_vs_returning(self, start, end, user_id=None):
        """Customers in the period whose first ever bill falls inside it (new) or before it (returning)."""
        where, params = _scope(start, end, user_id)
        return self.one(f'''SELECT COALESCE(SUM(CASE WHEN f.first_day >= ? THEN 1 ELSE 0 END), 0) AS new,
                                   COALESCE(SUM(CASE WHEN f.first_day < ? THEN 1 ELSE 0 END), 0) AS repeat
                            FROM (SELECT DISTINCT i.customer_id FROM invoices i WHERE {where} AND i.customer_id IS NOT NULL) c
                            JOIN (SELECT customer_id, MIN(invoice_date) AS first_day FROM invoices WHERE status='FINALIZED'
                                  GROUP BY customer_id) f ON f.customer_id=c.customer_id''', [start, start, *params])

    def open_dues(self):
        return self.all('''SELECT i.invoice_date, i.outstanding FROM invoices i
                           WHERE i.status='FINALIZED' AND i.outstanding > 0.009''')

    # ---- team --------------------------------------------------------------
    def staff(self, start, end):
        where, params = _scope(start, end, None)
        return self.all(f'''SELECT u.id AS user_id, COALESCE(u.display_name, u.username) AS name, u.role,
                                   COUNT(i.id) AS bills, ROUND(COALESCE(SUM(i.grand_total), 0), 2) AS sales,
                                   ROUND(COALESCE(AVG(i.grand_total), 0), 2) AS avg_bill, ROUND(COALESCE(SUM(i.discount), 0), 2) AS discounts,
                                   (SELECT COUNT(*) FROM invoices v WHERE v.voided_by=u.id AND substr(v.voided_at, 1, 10) BETWEEN ? AND ?) AS voids,
                                   (SELECT COUNT(*) FROM invoices e WHERE e.edited_by=u.id AND substr(e.edited_at, 1, 10) BETWEEN ? AND ?) AS edits,
                                   (SELECT ROUND(COALESCE(SUM(r.total_refund), 0), 2) FROM returns r
                                    WHERE r.user_id=u.id AND r.return_date BETWEEN ? AND ?) AS refunds
                            FROM users u LEFT JOIN invoices i ON i.user_id=u.id AND {where}
                            GROUP BY u.id HAVING bills > 0 OR voids > 0 OR edits > 0 OR refunds > 0
                            ORDER BY sales DESC''', [start, end, start, end, start, end, *params])

    def exceptions(self, start, end, user_id=None):
        """Voids, edits and returns in the period (by when they happened)."""
        mine, extra = ('', [])
        if user_id is not None:
            mine, extra = ' AND user_id=?', [user_id]
        voided = self.one(f'''SELECT COUNT(*) AS count, ROUND(COALESCE(SUM(grand_total), 0), 2) AS amount FROM invoices
                              WHERE status='VOID' AND revised_to_id IS NULL AND substr(voided_at, 1, 10) BETWEEN ? AND ?{mine}''',
                          [start, end, *extra])
        edited = self.scalar(f'''SELECT COUNT(*) FROM invoices WHERE revised_from_id IS NOT NULL
                                 AND substr(edited_at, 1, 10) BETWEEN ? AND ?{mine}''', [start, end, *extra], default=0)
        returned = self.one(f'''SELECT COUNT(*) AS count, ROUND(COALESCE(SUM(total_refund), 0), 2) AS amount FROM returns
                                WHERE return_date BETWEEN ? AND ?{mine}''', [start, end, *extra])
        return {'voids': voided, 'edits': edited, 'returns': returned}

    # ---- stock -------------------------------------------------------------
    def stock_by_category(self):
        return self.all(f'''SELECT category, COUNT(*) AS products, ROUND(SUM(MAX(stock, 0)), 2) AS units,
                                   ROUND(SUM(MAX(stock, 0) * cost_price), 2) AS inventory_cost,
                                   ROUND(SUM(MAX(stock, 0) * default_unit_price), 2) AS retail_value,
                                   SUM(CASE WHEN stock <= 0 THEN 1 ELSE 0 END) AS out_of_stock,
                                   SUM(CASE WHEN stock > 0 AND stock <= reorder_level THEN 1 ELSE 0 END) AS low
                            FROM (SELECT COALESCE(NULLIF(p.category, ''), 'Uncategorised') AS category, p.cost_price, p.default_unit_price,
                                         p.reorder_level, {STOCK_SQL} AS stock FROM products p WHERE p.status='ACTIVE')
                            GROUP BY category ORDER BY retail_value DESC''')

    def dead_stock(self, since, limit=10):
        """Products with stock on hand and no finalized sale since the given date."""
        return self.all(f'''SELECT * FROM (
                                SELECT p.name, p.sku, ROUND({STOCK_SQL}, 2) AS stock, ROUND({STOCK_SQL} * p.cost_price, 2) AS inventory_cost,
                                       ROUND({STOCK_SQL} * p.default_unit_price, 2) AS retail_value,
                                       (SELECT MAX(i.invoice_date) FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                                        WHERE ii.product_id=p.id AND i.status='FINALIZED') AS last_sale
                                FROM products p WHERE p.status='ACTIVE')
                            WHERE stock > 0 AND (last_sale IS NULL OR last_sale < ?)
                            ORDER BY retail_value DESC LIMIT ?''', (since, limit))

    def stock_levels(self):
        return self.all(f'''SELECT p.id AS product_id, p.name, p.sku, ROUND({STOCK_SQL}, 2) AS stock, p.reorder_level
                            FROM products p WHERE p.status='ACTIVE' ''')

    # ---- money out ---------------------------------------------------------
    def expenses_by_category(self, start, end, user_id=None):
        params = [start, end]
        mine = ''
        if user_id is not None:
            mine = ' AND user_id=?'
            params.append(user_id)
        return self.all(f'''SELECT category, ROUND(SUM(amount), 2) AS amount, COUNT(*) AS entries FROM expenses
                            WHERE expense_date BETWEEN ? AND ?{mine} GROUP BY category ORDER BY amount DESC''', params)

    def expenses_daily(self, start, end):
        return self.all('''SELECT expense_date AS day, ROUND(SUM(amount), 2) AS amount FROM expenses
                           WHERE expense_date BETWEEN ? AND ? GROUP BY expense_date''', (start, end))
