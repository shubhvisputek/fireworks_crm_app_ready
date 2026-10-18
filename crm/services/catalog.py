"""Product master: products, prices and removal."""
from crm.domain import validation as v
from crm.domain.permissions import Permission as P
from crm.errors import NotFoundError, ValidationError
from crm.services.base import Service

PRODUCT_STATUSES = ('ACTIVE', 'INACTIVE')
# Columns from an earlier tax/tiered-pricing design. Still stored, never shown.
LEGACY_COLUMNS = ('units_per_box', 'boxes_per_carton', 'units_per_carton', 'hsn', 'gst_rate', 'cess_rate', 'cost_price',
                  'mrp', 'retail_selling_price', 'wholesale_selling_price')
EDITABLE_TEXT = {'name': 200, 'category': 100, 'subcategory': 100, 'brand': 100, 'unit': 30}


def present_product(row, include_cost=False):
    product = {k: val for k, val in row.items() if k not in LEGACY_COLUMNS}
    product['price'] = {'unit_price': row['default_unit_price']}
    if include_cost:
        product['cost_price'] = row['cost_price']
    return product


class CatalogService(Service):
    def list_products(self, status='ACTIVE', query='', category='', limit=200):
        limit = max(1, min(int(v.number(limit, 200)), 500))
        rows = self.repos.products.list(v.text(status, 20) or 'ACTIVE', v.text(query, 100), v.text(category, 100), limit)
        return [present_product(row) for row in rows]

    def categories(self):
        return self.repos.products.categories()

    def product_detail(self, actor, product_id):
        product = self.repos.products.get(product_id)
        if not product:
            raise NotFoundError('Product not found')
        return self.visible(actor, {
            'product': present_product(product, include_cost=True),
            'prices': self.repos.products.price_history(product_id),
            'stock': product['current_stock_base'],
            'last_sale': self.repos.products.last_sale_date(product_id),
            'last_purchase': self.repos.products.last_purchase_date(product_id),
        })

    def create_product(self, actor, data):
        sku = v.text(data.get('sku'), 64)
        name = v.text(data.get('name'), 200)
        if not sku or not name:
            raise ValidationError('Product identifier and name are required.')
        unit_price = v.amount(data.get('unit_price'), 'Unit price')
        opening = v.amount(data.get('opening_stock'), 'Opening stock', default=0.0)
        cost = v.amount(data.get('cost_price'), 'Cost price', default=0.0) if self.can(actor, P.PROFIT_VIEW) else 0.0
        explosive_kg = v.amount(data.get('explosive_kg'), 'Explosive content (kg)', default=0.0)
        barcode = v.optional_text(data.get('barcode'), 64)
        values = {
            'sku': sku, 'name': name,
            'category': v.optional_text(data.get('category'), 100), 'subcategory': v.optional_text(data.get('subcategory'), 100),
            'brand': v.optional_text(data.get('brand'), 100), 'unit': v.text(data.get('unit'), 30) or 'unit',
            'reorder_level': v.amount(data.get('reorder_level'), 'Reorder level', default=0.0),
            'status': v.one_of(data.get('status'), PRODUCT_STATUSES, 'Product status', default='ACTIVE'),
            'default_unit_price': unit_price, 'cost_price': cost, 'barcode': barcode, 'explosive_kg': explosive_kg,
            'created_at': self.now(), 'updated_at': self.now(),
        }
        with self.transaction():
            if self.repos.products.sku_exists(sku):
                raise ValidationError(f'Product ID {sku} already exists.')
            self._check_barcode(barcode)
            self.services.inventory.check_storage(actor, opening * explosive_kg, data.get('allow_over_limit'))
            product_id = self.repos.products.create(values)
            if opening:
                batch = v.optional_text(data.get('batch'), 64)
                batch_id = self.repos.inventory.add_batch({'product_id': product_id, 'batch_number': batch, 'qty_base': opening, 'cost': cost,
                                                           'purchase_date': self.today(), 'created_at': self.now()}) if batch else None
                self.repos.inventory.add_movement(product_id, 'OPENING', opening, self.now(), unit_cost=cost, ref_type='MANUAL',
                                                  reason='Product master opening stock', user_id=actor['id'], batch_id=batch_id)
            self.audit(actor, 'Product created', 'PRODUCT', product_id, new={**values, 'opening_stock': opening})
        return product_id

    def _check_barcode(self, barcode, product_id=None):
        owner = self.repos.products.barcode_owner(barcode) if barcode else None
        if owner and owner != product_id:
            raise ValidationError(f'Barcode {barcode} is already used by another product.')

    def update_product(self, actor, product_id, data):
        """Edit product details. Price changes go through set_unit_price; cost needs the profit permission."""
        with self.transaction():
            product = self.repos.products.get(product_id)
            if not product:
                raise NotFoundError('Product not found')
            values = {}
            for field, length in EDITABLE_TEXT.items():
                if field in data:
                    values[field] = v.text(data[field], length) or (product[field] if field in ('name', 'unit') else None)
            if 'barcode' in data:
                values['barcode'] = v.optional_text(data['barcode'], 64)
                self._check_barcode(values['barcode'], product_id)
            if 'reorder_level' in data:
                values['reorder_level'] = v.amount(data['reorder_level'], 'Reorder level', default=0.0)
            if 'explosive_kg' in data:
                values['explosive_kg'] = v.amount(data['explosive_kg'], 'Explosive content (kg)', default=0.0)
            if 'cost_price' in data and self.can(actor, P.PROFIT_VIEW):
                values['cost_price'] = v.amount(data['cost_price'], 'Cost price', default=0.0)
            if 'status' in data:
                values['status'] = v.one_of(data['status'], PRODUCT_STATUSES, 'Product status')
            if not values:
                return
            values['updated_at'] = self.now()
            self.repos.products.update(product_id, values)
            self.audit(actor, 'Product updated', 'PRODUCT', product_id,
                       previous={k: product[k] for k in values if k != 'updated_at'}, new={k: values[k] for k in values if k != 'updated_at'})

    def set_unit_price(self, actor, product_id, unit_price):
        unit_price = v.amount(unit_price, 'Unit price')
        with self.transaction():
            product = self.repos.products.get(product_id)
            if not product:
                raise ValidationError('Product not found.')
            self.repos.products.set_unit_price(product_id, unit_price, self.now())
            self.audit(actor, 'Default unit price changed', 'PRODUCT', product_id,
                       previous={'default_unit_price': product['default_unit_price']}, new={'default_unit_price': unit_price})

    def remove_product(self, actor, product_id):
        """Delete a product never used in a transaction; otherwise archive it."""
        with self.transaction():
            product = self.repos.products.get(product_id)
            if not product:
                raise ValidationError('Product not found.')
            if self.repos.products.transaction_references(product_id):
                self.repos.products.set_status(product_id, 'INACTIVE', self.now())
                action = 'Product deactivated'
            else:
                self.repos.products.delete(product_id)
                action = 'Product removed'
            self.audit(actor, action, 'PRODUCT', product_id, previous=product)
        return action.lower()
