"""Bills parked at the counter to be resumed later."""
import json
import secrets

from crm.domain import validation as v
from crm.domain.money import money
from crm.errors import NotFoundError, ValidationError
from crm.services.base import Service


def encode(data):
    return json.dumps({'items': data.get('items') or [], 'discount': money(data.get('discount', 0)),
                       'customer_phone': v.text(data.get('customer_phone'), 20)})


def decode(value):
    stored = json.loads(value or '[]')
    if isinstance(stored, list):  # early format: just the item list
        return {'items': stored, 'discount': 0.0, 'customer_phone': ''}
    if isinstance(stored, dict):
        return {'items': stored.get('items') or [], 'discount': money(stored.get('discount', 0)), 'customer_phone': str(stored.get('customer_phone') or '')}
    return {'items': [], 'discount': 0.0, 'customer_phone': ''}


def present(row):
    bill = dict(row)
    bill.update(decode(bill.pop('items_json')))
    return bill


class HeldBillService(Service):
    def hold(self, actor, data):
        items = data.get('items') or []
        if not isinstance(items, list) or not items:
            raise ValidationError('Add products before holding a bill.')
        ref = f"HOLD-{self.clock.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"
        with self.transaction():
            held_id = self.repos.held_bills.create({
                'ref': ref, 'customer_id': data.get('customer_id') or None, 'customer_name': v.optional_text(data.get('customer_name'), 200),
                'pricing_mode': v.text(data.get('pricing_mode'), 20) or 'STANDARD', 'items_json': encode(data),
                'notes': v.optional_text(data.get('notes')), 'created_at': self.now(), 'user_id': actor['id'],
            })
        return {'id': held_id, 'ref': ref}

    def list(self):
        return [present(row) for row in self.repos.held_bills.list()]

    def peek(self, held_id):
        row = self.repos.held_bills.get(held_id)
        if not row:
            raise NotFoundError('Held bill not found.')
        held = decode(row['items_json'])
        return {'ok': True, 'bill': row, **held}

    def resume(self, actor, held_id):
        """Take a held bill back to the counter; it is removed from the held list."""
        with self.transaction():
            row = self.repos.held_bills.get(held_id)
            if not row:
                raise NotFoundError('Held bill not found.')
            self.repos.held_bills.delete(held_id)
            self.audit(actor, 'Held bill resumed', 'HELD_BILL', held_id)
        return {'ok': True, 'bill': row, **decode(row['items_json'])}

    def delete(self, actor, held_id):
        with self.transaction():
            self.repos.held_bills.delete(held_id)
            self.audit(actor, 'Held bill deleted', 'HELD_BILL', held_id)
