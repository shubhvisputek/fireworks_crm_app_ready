from crm.repositories.base import Repository


class InventoryRepository(Repository):
    def stock(self, product_id):
        return self.scalar('SELECT COALESCE(SUM(qty_base), 0) FROM inventory_movements WHERE product_id=?', (product_id,), default=0)

    def add_movement(self, product_id, movement_type, qty, created_at, unit_cost=0, ref_type=None, ref_id=None,
                     reason=None, user_id=None, notes=None, batch_id=None):
        return self.insert('inventory_movements', {
            'product_id': product_id, 'movement_type': movement_type, 'qty_base': qty, 'unit_cost': unit_cost,
            'ref_type': ref_type, 'ref_id': ref_id, 'reason': reason, 'user_id': user_id, 'notes': notes,
            'batch_id': batch_id, 'created_at': created_at,
        })

    def add_batch(self, values):
        return self.insert('stock_batches', values)

    def ledger(self, product_id, start, end):
        return self.all('''SELECT m.*, p.name, p.sku FROM inventory_movements m JOIN products p ON p.id=m.product_id
                           WHERE m.product_id=? AND date(m.created_at) BETWEEN ? AND ? ORDER BY m.created_at, m.id''',
                        (product_id, start, end))
