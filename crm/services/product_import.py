"""One-time product master import from CSV or Excel."""
import csv
import io
import json
import re

from openpyxl import load_workbook

from crm.domain import validation as v
from crm.errors import ValidationError
from crm.services.base import Service
from crm.services.catalog import PRODUCT_STATUSES

MAX_ROWS = 20_000
PREVIEW_ROWS = 100
REQUIRED = ('sku', 'name', 'unit_price')

COLUMN_ALIASES = {
    'sku': ['sku', 'product code', 'product_code', 'productcode', 'product id', 'product_id', 'serial number', 'serial no',
            'serial no.', 'product number', 'product no'],
    'name': ['product name', 'name', 'product'],
    'category': ['category'],
    'subcategory': ['subcategory', 'sub-category'],
    'brand': ['brand / manufacturer', 'brand', 'manufacturer'],
    'unit': ['unit', 'uom', 'selling unit'],
    'unit_price': ['unit price', 'unit selling price', 'selling price', 'default unit price', 'default selling price',
                   'retail selling price', 'retail price', 'price'],
    'cost_price': ['cost price', 'cost', 'purchase price', 'buying price'],
    'opening_stock': ['opening stock', 'opening_stock', 'stock', 'stock quantity', 'opening quantity'],
    'reorder_level': ['minimum stock / reorder level', 'reorder level', 'reorder_level', 'minimum stock'],
    'status': ['product status', 'status'],
}


def _normalise(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').strip().lower()).strip()


def suggest_mapping(headers):
    """Best header for each field, by exact match, containment, then word overlap."""
    normalised = {_normalise(h): h for h in headers}
    mapping = {}
    for key, aliases in COLUMN_ALIASES.items():
        best, best_score = None, 0
        for alias in aliases:
            na = _normalise(alias)
            for nh, header in normalised.items():
                if nh == na:
                    score = 100
                elif na in nh or nh in na:
                    score = 80 + min(len(na), len(nh)) / 100
                else:
                    alias_words = set(na.split())
                    score = len(alias_words & set(nh.split())) / max(1, len(alias_words)) * 70
                if score > best_score:
                    best, best_score = header, score
        mapping[key] = best if best_score >= 45 else None
    return mapping


def read_rows(filename, content):
    """Rows as dicts keyed by header, from CSV or the first Excel sheet."""
    if filename.lower().endswith('.csv'):
        text = content.decode('utf-8-sig', errors='replace')
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            raise ValidationError('The file could not be read. Upload a CSV or .xlsx file.')
        try:
            values = list(workbook.active.iter_rows(values_only=True, max_row=MAX_ROWS + 1))
        finally:
            workbook.close()
        if not values:
            return []
        headers = [str(h).strip() if h is not None else '' for h in values[0]]
        rows = [{headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))} for row in values[1:]]
    if len(rows) > MAX_ROWS:
        raise ValidationError(f'The file has more than {MAX_ROWS} rows.')
    return rows


class ProductImportService(Service):
    def _load(self, upload, mapping_json):
        if not upload or not upload.get('filename'):
            raise ValidationError('Attach a CSV or Excel file.')
        rows = read_rows(upload['filename'], upload['content'])
        headers = list(rows[0].keys()) if rows else []
        try:
            mapping = json.loads(mapping_json) if mapping_json else suggest_mapping(headers)
        except json.JSONDecodeError:
            raise ValidationError('Column mapping is not valid.')
        missing = [field for field in REQUIRED if not mapping.get(field)]
        if missing:
            raise ValidationError('Mandatory columns missing: ' + ', '.join(missing))
        return rows, headers, mapping

    @staticmethod
    def _cell(row, mapping, field):
        column = mapping.get(field)
        return row.get(column) if column else None

    def preview(self, upload, mapping_json=None):
        rows, headers, mapping = self._load(upload, mapping_json)
        preview, errors, seen = [], [], set()
        for index, row in enumerate(rows[:PREVIEW_ROWS], 1):
            sku = v.text(self._cell(row, mapping, 'sku'))
            name = v.text(self._cell(row, mapping, 'name'))
            price = v.number(self._cell(row, mapping, 'unit_price'), -1)
            if not sku or not name or price < 0:
                errors.append({'row': index, 'error': 'Product identifier, Product Name, and a non-negative Unit Price are required'})
                continue
            if sku in seen:
                errors.append({'row': index, 'error': f'Duplicate Product ID: {sku}'})
            elif self.repos.products.sku_exists(sku):
                errors.append({'row': index, 'error': f'Duplicate Product ID already exists: {sku}'})
            seen.add(sku)
            preview.append({key: self._cell(row, mapping, key) for key in COLUMN_ALIASES})
        return {'count': len(rows), 'headers': headers, 'mapping': mapping, 'preview': preview, 'errors': errors}

    def _parse_row(self, row, mapping):
        sku = v.text(self._cell(row, mapping, 'sku'), 64)
        name = v.text(self._cell(row, mapping, 'name'), 200)
        if not sku or not name:
            raise ValidationError('Product identifier and name are required')
        price = v.number(self._cell(row, mapping, 'unit_price'), -1)
        if price < 0:
            raise ValidationError('Unit price is required and cannot be negative')
        opening = v.number(self._cell(row, mapping, 'opening_stock'), 0)
        if opening < 0:
            raise ValidationError('Opening stock cannot be negative')
        cost = v.number(self._cell(row, mapping, 'cost_price'), 0)
        if cost < 0:
            raise ValidationError('Cost price cannot be negative')
        status = v.text(self._cell(row, mapping, 'status'), 20).upper() or 'ACTIVE'
        if status not in PRODUCT_STATUSES:
            raise ValidationError(f'Product status must be ACTIVE or INACTIVE, not {status}')
        return {
            'sku': sku, 'name': name, 'unit': v.text(self._cell(row, mapping, 'unit'), 30) or 'unit',
            'category': v.text(self._cell(row, mapping, 'category'), 100), 'subcategory': v.text(self._cell(row, mapping, 'subcategory'), 100),
            'brand': v.text(self._cell(row, mapping, 'brand'), 100), 'reorder_level': max(0.0, v.number(self._cell(row, mapping, 'reorder_level'), 0)),
            'status': status, 'default_unit_price': price, 'cost_price': cost,
        }, opening

    def import_products(self, actor, upload, mapping_json=None):
        rows, _headers, mapping = self._load(upload, mapping_json)
        errors, seen, duplicates, imported = [], set(), 0, 0
        with self.transaction():
            for index, row in enumerate(rows, 1):
                try:
                    values, opening = self._parse_row(row, mapping)
                    if values['sku'] in seen:
                        duplicates += 1
                        raise ValidationError(f"Duplicate Product ID: {values['sku']}")
                    seen.add(values['sku'])
                    if self.repos.products.sku_exists(values['sku']):
                        duplicates += 1
                        raise ValidationError(f"Duplicate Product ID already exists: {values['sku']}")
                    product_id = self.repos.products.create({**values, 'created_at': self.now(), 'updated_at': self.now()})
                    if opening:
                        self.repos.inventory.add_movement(product_id, 'OPENING', opening, self.now(), unit_cost=values['cost_price'],
                                                          ref_type='IMPORT', reason='Product master opening stock', user_id=actor['id'])
                    imported += 1
                except ValidationError as error:
                    errors.append({'row': index, 'error': error.message})
            if errors:
                # Raising inside the transaction rolls back every row: imports are all-or-nothing.
                raise ValidationError(f'Product Master validation failed for {len(errors)} row(s).', ok=False, total_rows=len(rows),
                                      imported=0, failed_rows=len(errors), duplicate_rows=duplicates, validation_errors=errors)
            self.audit(actor, 'Product master imported', 'PRODUCT', None, new={'rows': imported, 'added': imported, 'updated': 0})
        return {'ok': True, 'total_rows': len(rows), 'imported': imported, 'added': imported, 'updated': 0,
                'failed_rows': 0, 'duplicate_rows': duplicates, 'validation_errors': []}
