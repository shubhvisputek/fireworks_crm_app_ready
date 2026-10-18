"""Stock movements: adjustments, removals, purchases (GRN) and the ledger."""
from crm.domain import validation as v
from crm.domain.money import money
from crm.errors import ValidationError
from crm.services.base import Service

# Adjustment types that take stock away; anything else adds stock.
REDUCING_ADJUSTMENTS = ('DAMAGE', 'BREAKAGE', 'MOISTURE', 'EXPIRED', 'MISSING')


class InventoryService(Service):
    def _product(self, product_id):
        product = self.repos.products.get(v.integer_id(product_id, 'Product'))
        if not product:
            raise ValidationError('Product not found.')
        return product

    def _check_not_negative(self, product, delta, message):
        allowed = self.services.settings.get_settings().get('negative_stock_allowed', False)
        if delta < 0 and not allowed and product['current_stock_base'] + delta < 0:
            raise ValidationError(message)

    def adjust(self, actor, data):
        with self.transaction():
            product = self._product(data.get('product_id'))
            qty = v.positive(data.get('qty'), 'Quantity')
            kind = v.text(data.get('type'), 30).upper() or 'OTHER'
            delta = -qty if kind in REDUCING_ADJUSTMENTS else qty
            self._check_not_negative(product, delta, 'Adjustment would create negative stock.')
            self.repos.inventory.add_movement(product['id'], 'ADJUSTMENT', delta, self.now(), unit_cost=v.number(data.get('unit_cost')),
                                              ref_type='ADJUSTMENT', reason=v.text(data.get('reason'), 200) or kind,
                                              user_id=actor['id'], notes=v.optional_text(data.get('notes')))
            self.audit(actor, 'Stock adjusted', 'INVENTORY', product['id'], new={'type': kind, 'qty': delta, 'reason': data.get('reason')})
        return self.repos.inventory.stock(product['id'])

    def remove(self, actor, data):
        with self.transaction():
            product = self._product(data.get('product_id'))
            qty = v.number(data.get('qty'))
            if qty <= 0:
                raise ValidationError('Removal quantity must be greater than 0.')
            self._check_not_negative(product, -qty, 'Removal would create negative stock.')
            self.repos.inventory.add_movement(product['id'], 'STOCK_REMOVAL', -qty, self.now(), unit_cost=v.number(data.get('unit_cost')),
                                              ref_type='INVENTORY_REMOVAL', reason=v.text(data.get('reason'), 200) or 'Stock removed',
                                              user_id=actor['id'], notes=v.optional_text(data.get('notes')))
            self.audit(actor, 'Stock removed', 'INVENTORY', product['id'], new={'qty': qty, 'reason': data.get('reason')})
        return self.repos.inventory.stock(product['id'])

    def ledger(self, product_id, start=None, end=None):
        start = v.iso_date(start, 'Start date') or '1900-01-01'
        end = v.iso_date(end, 'End date') or self.today()
        return self.repos.inventory.ledger(v.integer_id(product_id, 'Product'), start, end)

    def record_purchase(self, actor, data):
        items = data.get('items') or []
        if not isinstance(items, list) or not items:
            raise ValidationError('Add at least one product to the purchase.')
        purchase_date = v.iso_date(data.get('purchase_date'), 'Purchase date') or self.today()
        freight = v.amount(data.get('freight'), 'Freight', default=0.0)
        supplier = v.optional_text(data.get('supplier_name'), 200)
        track_batches = v.parse_bool(data.get('batch_tracking', True))
        with self.transaction():
            number = f"PUR-{purchase_date.replace('-', '')}-{self.repos.sequences.next('purchase'):05d}"
            purchase_id = self.repos.purchases.create({
                'purchase_number': number, 'purchase_date': purchase_date, 'supplier_id': data.get('supplier_id') or None,
                'supplier_name': supplier, 'invoice_number': v.optional_text(data.get('invoice_number'), 64),
                'subtotal': 0, 'gst': 0, 'freight': freight, 'total': 0, 'user_id': actor['id'], 'created_at': self.now(),
            })
            subtotal = 0.0
            for item in items:
                product = self._product(item.get('product_id'))
                qty = v.positive(item.get('qty'), 'Quantity')
                cost = v.amount(item.get('cost_price'), 'Cost price', default=0.0)
                unit = v.text(item.get('sell_unit'), 30) or product['unit']
                subtotal += qty * cost
                batch_id = None
                if track_batches:
                    batch_id = self.repos.inventory.add_batch({
                        'product_id': product['id'], 'batch_number': v.optional_text(item.get('batch_number'), 64), 'supplier': supplier,
                        'manufacturer': product['brand'], 'purchase_date': purchase_date, 'qty_base': qty, 'cost': cost,
                        'location': v.optional_text(item.get('location'), 100), 'notes': v.optional_text(item.get('notes')), 'created_at': self.now(),
                    })
                self.repos.purchases.add_item({'purchase_id': purchase_id, 'product_id': product['id'], 'qty_input': qty, 'sell_unit': unit,
                                               'qty_base': qty, 'cost_price': cost, 'gst_rate': 0, 'gst_amount': 0,
                                               'batch_number': v.optional_text(item.get('batch_number'), 64), 'batch_id': batch_id})
                self.repos.inventory.add_movement(product['id'], 'PURCHASE', qty, self.now(), unit_cost=cost, ref_type='PURCHASE',
                                                  ref_id=purchase_id, reason='Purchase/GRN', user_id=actor['id'], batch_id=batch_id)
                if cost > 0:
                    # Latest purchase cost becomes the product's cost for profit reporting.
                    self.repos.products.set_cost_price(product['id'], cost, self.now())
            total = money(subtotal + freight)
            self.repos.purchases.set_totals(purchase_id, money(subtotal), total)
            self.audit(actor, 'Stock purchase posted', 'PURCHASE', purchase_id, new={'number': number, 'items': items, 'total': total})
        return {'purchase_id': purchase_id, 'purchase_number': number, 'total': total}

    def list_purchases(self):
        return self.repos.purchases.list()
