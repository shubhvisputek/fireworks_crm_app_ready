from crm.repositories.base import Repository

# Invoice with the names of the people who billed, edited or voided it, and its revision links.
INVOICE_SELECT = '''
SELECT i.*, COALESCE(ub.display_name, ub.username) AS billed_by_name, COALESCE(ue.display_name, ue.username) AS edited_by_name,
       COALESCE(uv.display_name, uv.username) AS voided_by_name, COALESCE(ua.display_name, ua.username) AS discount_approved_by_name,
       rf.invoice_number AS revised_from_number, rt.invoice_number AS revised_to_number, c.phone AS customer_phone,
       (SELECT COALESCE(ROUND(SUM(r.total_refund), 2), 0) FROM returns r WHERE r.invoice_id=i.id AND r.status='POSTED') AS returned_amount
FROM invoices i
LEFT JOIN users ub ON ub.id=i.user_id
LEFT JOIN users ue ON ue.id=i.edited_by
LEFT JOIN users uv ON uv.id=i.voided_by
LEFT JOIN users ua ON ua.id=i.discount_approved_by
LEFT JOIN invoices rf ON rf.id=i.revised_from_id
LEFT JOIN invoices rt ON rt.id=i.revised_to_id
LEFT JOIN customers c ON c.id=i.customer_id
'''


class InvoiceRepository(Repository):
    # --- invoices ---------------------------------------------------------
    def list(self, start, end, status='FINALIZED', limit=500, user_id=None):
        own = ' AND i.user_id=?' if user_id else ''
        params = (start, end, status) + ((user_id,) if user_id else ()) + (limit,)
        return self.all(INVOICE_SELECT + f' WHERE i.invoice_date BETWEEN ? AND ? AND i.status=?{own} ORDER BY i.id DESC LIMIT ?', params)

    def list_finalized(self):
        return self.all(INVOICE_SELECT + " WHERE i.status='FINALIZED' ORDER BY i.invoice_date, i.id")

    def get(self, invoice_id):
        return self.one(INVOICE_SELECT + ' WHERE i.id=?', (invoice_id,))

    def create(self, values):
        return self.insert('invoices', values)

    def set_finalized_at(self, invoice_id, at):
        self.execute('UPDATE invoices SET created_at=?, finalized_at=? WHERE id=?', (at, at, invoice_id))

    def mark_void(self, invoice_id, user_id, at):
        self.execute("UPDATE invoices SET status='VOID', voided_by=?, voided_at=? WHERE id=?", (user_id, at, invoice_id))

    def link_revision(self, old_id, new_id, reason, user_id, at):
        self.execute('UPDATE invoices SET revised_from_id=?, revision_reason=?, edited_by=?, edited_at=? WHERE id=?',
                     (old_id, reason, user_id, at, new_id))
        self.execute('UPDATE invoices SET revised_to_id=? WHERE id=?', (new_id, old_id))

    def set_outstanding(self, invoice_id, outstanding):
        self.execute('UPDATE invoices SET outstanding=? WHERE id=?', (outstanding, invoice_id))

    def apply_payment(self, invoice_id, amount, outstanding):
        self.execute('UPDATE invoices SET amount_received=amount_received+?, outstanding=? WHERE id=?', (amount, outstanding, invoice_id))

    # --- items ------------------------------------------------------------
    def add_item(self, values):
        return self.insert('invoice_items', values)

    def items(self, invoice_id):
        return self.all('''SELECT ii.*, (SELECT COALESCE(SUM(ri.qty_input), 0) FROM return_items ri JOIN returns r ON r.id=ri.return_id
                                         WHERE ri.invoice_item_id=ii.id AND r.status='POSTED') AS returned_qty
                           FROM invoice_items ii WHERE ii.invoice_id=? ORDER BY ii.id''', (invoice_id,))

    def item(self, item_id, invoice_id):
        return self.one('SELECT * FROM invoice_items WHERE id=? AND invoice_id=?', (item_id, invoice_id))

    def items_for_export(self):
        return self.all('''SELECT i.invoice_number, i.invoice_date, i.customer_name_snapshot, ii.sku_snapshot, ii.product_name_snapshot,
                                  ii.qty_input, ii.sell_unit, ii.qty_base, ii.unit_price, ii.discount, ii.taxable_amount, ii.cost_snapshot
                           FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                           WHERE i.status='FINALIZED' ORDER BY i.invoice_date, i.id, ii.id''')

    # --- payments ---------------------------------------------------------
    def add_payment(self, values):
        return self.insert('payments', values)

    def payments(self, invoice_id):
        return self.all('SELECT * FROM payments WHERE invoice_id=? ORDER BY id', (invoice_id,))

    def payments_for_export(self):
        return self.all('''SELECT i.invoice_number, i.invoice_date, i.customer_name_snapshot, p.payment_date, p.mode, p.amount, p.reference, p.notes
                           FROM payments p JOIN invoices i ON i.id=p.invoice_id
                           WHERE i.status='FINALIZED' ORDER BY i.invoice_date, i.id, p.id''')

    # --- returns ----------------------------------------------------------
    def posted_return_count(self, invoice_id):
        return self.scalar("SELECT COUNT(*) FROM returns WHERE invoice_id=? AND status='POSTED'", (invoice_id,), default=0)

    def returned_qty(self, invoice_item_id):
        return self.scalar('''SELECT COALESCE(SUM(ri.qty_input), 0) FROM return_items ri JOIN returns r ON r.id=ri.return_id
                              WHERE ri.invoice_item_id=? AND r.status='POSTED' ''', (invoice_item_id,), default=0)

    def create_return(self, values):
        return self.insert('returns', values)

    def add_return_item(self, values):
        return self.insert('return_items', values)
