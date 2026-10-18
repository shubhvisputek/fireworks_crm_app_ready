"""Stock movements, purchases (GRN), the licence storage limit and the seasonal reorder plan."""
import datetime as dt
import math

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

    # --- licence storage limit --------------------------------------------
    def storage_status(self):
        """Net explosive content in store against the licence limit (0 = no limit set)."""
        limit = v.number(self.services.settings.get_settings().get('storage_limit_kg'), 0)
        current = round(self.repos.reports.stored_explosive_kg(), 3)
        return {'limit_kg': limit, 'current_kg': current, 'pct': round(current / limit * 100, 1) if limit else 0,
                'over': bool(limit) and current > limit}

    def check_storage(self, actor, added_kg, allow_over_limit):
        """Refuse stock that would take the store past the licence limit, unless the user confirms."""
        status = self.storage_status()
        after = round(status['current_kg'] + added_kg, 3)
        if not status['limit_kg'] or added_kg <= 0 or after <= status['limit_kg']:
            return
        if not v.parse_bool(allow_over_limit):
            raise ValidationError(f"This would bring stored explosives to {after:g} kg, above the licence limit of {status['limit_kg']:g} kg.",
                                  code='STORAGE_LIMIT', current_kg=status['current_kg'], after_kg=after, limit_kg=status['limit_kg'])
        self.audit(actor, 'Storage limit exceeded (confirmed)', 'INVENTORY', None,
                   new={'current_kg': status['current_kg'], 'after_kg': after, 'limit_kg': status['limit_kg']})

    # --- movements ----------------------------------------------------------
    def adjust(self, actor, data):
        with self.transaction():
            product = self._product(data.get('product_id'))
            qty = v.positive(data.get('qty'), 'Quantity')
            kind = v.text(data.get('type'), 30).upper() or 'OTHER'
            delta = -qty if kind in REDUCING_ADJUSTMENTS else qty
            self._check_not_negative(product, delta, 'Adjustment would create negative stock.')
            if delta > 0:
                self.check_storage(actor, delta * float(product['explosive_kg'] or 0), data.get('allow_over_limit'))
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

    def ledger(self, actor, product_id, start=None, end=None):
        start = v.iso_date(start, 'Start date') or '1900-01-01'
        end = v.iso_date(end, 'End date') or self.today()
        return self.visible(actor, self.repos.inventory.ledger(v.integer_id(product_id, 'Product'), start, end))

    def record_purchase(self, actor, data):
        items = data.get('items') or []
        if not isinstance(items, list) or not items:
            raise ValidationError('Add at least one product to the purchase.')
        purchase_date = v.iso_date(data.get('purchase_date'), 'Purchase date') or self.today()
        freight = v.amount(data.get('freight'), 'Freight', default=0.0)
        track_batches = v.parse_bool(data.get('batch_tracking', True))
        with self.transaction():
            supplier_id, supplier = self.services.suppliers.resolve(actor, data.get('supplier_id'), data.get('supplier_name'))
            products = [self._product(item.get('product_id')) for item in items]
            added_kg = sum(v.number(item.get('qty')) * float(p['explosive_kg'] or 0) for item, p in zip(items, products))
            self.check_storage(actor, added_kg, data.get('allow_over_limit'))
            number = f"PUR-{purchase_date.replace('-', '')}-{self.repos.sequences.next('purchase'):05d}"
            purchase_id = self.repos.purchases.create({
                'purchase_number': number, 'purchase_date': purchase_date, 'supplier_id': supplier_id,
                'supplier_name': supplier, 'invoice_number': v.optional_text(data.get('invoice_number'), 64),
                'subtotal': 0, 'freight': freight, 'total': 0, 'user_id': actor['id'], 'created_at': self.now(),
            })
            subtotal = 0.0
            for item, product in zip(items, products):
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

    def list_purchases(self, actor):
        return self.visible(actor, self.repos.purchases.list())

    # --- seasonal reorder plan ----------------------------------------------
    def reorder_plan(self, actor, start=None, end=None, growth_pct=None):
        """Suggest how much to buy: last season's sales plus growth, minus stock in hand."""
        start = v.iso_date(start, 'Season start')
        end = v.iso_date(end, 'Season end')
        if not start or not end:
            start, end = self._last_season()
        growth = v.amount(growth_pct, 'Growth %', minimum=-100, default=10.0)
        sold = self.repos.reports.quantity_sold_by_product(start, end)
        rows = []
        for product in self.repos.products.list(limit=10_000):
            last = float(sold.get(product['id'], 0))
            stock = max(float(product['current_stock_base']), 0)
            target = math.ceil(last * (1 + growth / 100)) if last else 0
            suggested = max(0, target - stock)
            rows.append({'product_id': product['id'], 'sku': product['sku'], 'name': product['name'], 'unit': product['unit'],
                         'sold_last_season': last, 'stock': stock, 'target': target, 'suggested': suggested,
                         'cost': money(suggested * float(product['cost_price'] or 0))})
        rows.sort(key=lambda row: (-row['suggested'], row['sku']))
        return self.visible(actor, {'season': {'start': start, 'end': end}, 'growth_pct': growth, 'rows': rows,
                                    'total_cost': money(sum(row['cost'] for row in rows))})

    def _last_season(self):
        """Last year's season dates (from Settings), or October last year."""
        targets = self.services.settings.get_targets()
        try:
            start = dt.date.fromisoformat(targets.get('season_start') or '')
            end = dt.date.fromisoformat(targets.get('season_end') or '')
            return start.replace(year=start.year - 1).isoformat(), end.replace(year=end.year - 1).isoformat()
        except ValueError:
            year = self.clock.today().year - 1
            return f'{year}-10-01', f'{year}-10-31'
