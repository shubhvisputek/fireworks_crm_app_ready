"""Bills: create, void, edit (re-issue), returns and credit collection."""
import re
from collections import defaultdict

from crm.domain import validation as v
from crm.domain.money import allocate_discount, amounts_equal, money
from crm.domain.permissions import Permission as P
from crm.errors import NotFoundError, ValidationError
from crm.services.base import Service

CREDIT = 'CREDIT'
INVOICE_STATUSES = ('FINALIZED', 'VOID')


class SalesService(Service):
    # --- queries ------------------------------------------------------------
    def list_invoices(self, actor, start=None, end=None, status='FINALIZED'):
        start = v.iso_date(start, 'Start date') or self.today()
        end = v.iso_date(end, 'End date') or self.today()
        status = v.one_of(status, INVOICE_STATUSES, 'Status', default='FINALIZED')
        own_only = None if self.can(actor, P.SALES_VIEW) else actor['id']
        return self.repos.invoices.list(start, end, status, user_id=own_only)

    def visible_invoice(self, actor, invoice_id):
        """The invoice if this user may see it: everyone's with 'See all bills', otherwise only bills they made."""
        invoice = self.repos.invoices.get(invoice_id)
        if not invoice or (not self.can(actor, P.SALES_VIEW) and invoice['user_id'] != actor['id']):
            raise NotFoundError('Invoice not found')
        return invoice

    def invoice_detail(self, actor, invoice_id):
        invoice = self.visible_invoice(actor, invoice_id)
        return self.visible(actor, {'invoice': invoice, 'items': self.repos.invoices.items(invoice_id),
                                    'payments': self.repos.invoices.payments(invoice_id)})

    # --- creating bills ---------------------------------------------------------
    def _invoice_number(self):
        prefix = re.sub(r'[^A-Z0-9]', '', str(self.services.settings.get_settings().get('invoice_prefix') or '').upper())[:10] or 'FW'
        return f"{prefix}-{self.today().replace('-', '')}-{self.repos.sequences.next('invoice'):05d}"

    def _bill_lines(self, items):
        if not isinstance(items, list) or not items:
            raise ValidationError('Add at least one product to the bill.')
        allow_negative = self.services.settings.get_settings().get('negative_stock_allowed', False)
        lines, needed = [], defaultdict(float)
        for item in items:
            product_id = v.integer_id((item or {}).get('product_id'), 'Product')
            product = self.repos.products.get_active(product_id)
            if not product:
                raise ValidationError(f'Product {product_id} not found or inactive.')
            qty = v.number(item.get('qty'), 0)
            if qty <= 0:
                raise ValidationError(f"Invalid quantity for {product['name']}.")
            needed[product_id] += qty
            if not allow_negative and product['current_stock_base'] < needed[product_id]:
                raise ValidationError(f"Insufficient stock for {product['name']}. Available: {product['current_stock_base']:g} base units.")
            # Prices always come from the product master; a client-sent price is ignored.
            price = float(product['default_unit_price'] or 0)
            lines.append({'product': product, 'qty': qty, 'price': price, 'gross': money(price * qty)})
        return lines

    @staticmethod
    def _payments(payments, total):
        if not isinstance(payments, list):
            raise ValidationError('Payments must be a list.')
        cleaned, paid, credit = [], 0.0, 0.0
        for payment in payments:
            payment = payment or {}
            amount = v.amount(payment.get('amount'), 'Payment amount', default=0.0)
            mode = v.text(payment.get('mode'), 20) or 'Cash'
            paid += amount
            if mode.upper() == CREDIT:
                credit += amount
            if amount:
                cleaned.append({'mode': mode, 'amount': amount, 'reference': v.optional_text(payment.get('reference'), 100),
                                'notes': v.optional_text(payment.get('notes'))})
        if not amounts_equal(paid, total):
            raise ValidationError('Payment allocations must equal the invoice total after discount.')
        return cleaned, money(paid - credit), money(credit)

    def create_sale(self, actor, data, invoice_date=None, billed_by=None):
        """Finalize a bill atomically. Returns (invoice_id, invoice_number)."""
        with self.transaction():
            phone = v.phone(data.get('customer_phone'))
            name = v.text(data.get('customer_name'), 200)
            customer = self.services.customers.resolve_for_bill(data.get('customer_id'), name, phone)
            settings = self.services.settings.get_settings()
            lines = self._bill_lines(data.get('items'))
            subtotal = money(sum(line['gross'] for line in lines))
            try:
                discount = money(data.get('discount', 0))
            except (ValueError, TypeError, ArithmeticError):
                raise ValidationError('Discount must be a valid amount.')
            if discount < 0 or discount > subtotal:
                raise ValidationError('Discount must be between 0 and the subtotal.')
            approved_by = self._discount_approval(actor, discount, subtotal, data.get('approval'))
            for line, share in zip(lines, allocate_discount(discount, [line['gross'] for line in lines])):
                line['discount'] = share
                line['net'] = money(line['gross'] - share)
            total = money(sum(line['net'] for line in lines))
            payments, received, outstanding = self._payments(data.get('payments') or [], total)

            number = self._invoice_number()
            now = self.now()
            invoice_id = self.repos.invoices.create({
                'invoice_number': number, 'invoice_date': invoice_date or self.today(),
                'customer_id': customer['id'] if customer else None,
                'customer_name_snapshot': customer['name'] if customer else (name or settings.get('walk_in_name') or 'Walk-in Customer'),
                'customer_type_snapshot': customer['customer_type'] if customer else 'CUSTOMER',
                'status': 'FINALIZED', 'pricing_mode': 'STANDARD', 'subtotal': subtotal, 'discount': discount,
                'taxable_amount': total, 'grand_total': total, 'amount_received': received, 'outstanding': outstanding,
                'user_id': billed_by or actor['id'], 'notes': v.optional_text(data.get('notes'), 1000), 'created_at': now, 'finalized_at': now,
                'discount_approved_by': approved_by,
            })
            for line in lines:
                product = line['product']
                cost = float(product['cost_price'] or 0)
                self.repos.invoices.add_item({
                    'invoice_id': invoice_id, 'product_id': product['id'], 'sku_snapshot': product['sku'], 'product_name_snapshot': product['name'],
                    'hsn_snapshot': None, 'qty_input': line['qty'], 'sell_unit': product['unit'], 'qty_base': line['qty'],
                    'unit_price': line['price'], 'original_price': line['price'], 'discount': line['discount'], 'taxable_amount': line['net'],
                    'gst_rate': 0, 'cess_rate': 0, 'gst_amount': 0,  # no tax in this app; old columns that must be filled
                    'cost_snapshot': cost,
                    'manual_override_reason': v.optional_text(data.get('override_reason')),
                })
                self.repos.inventory.add_movement(product['id'], 'SALE', -line['qty'], now, unit_cost=cost, ref_type='INVOICE',
                                                  ref_id=invoice_id, reason='Sale', user_id=actor['id'])
            for payment in payments:
                self.repos.invoices.add_payment({'invoice_id': invoice_id, 'customer_id': customer['id'] if customer else None,
                                                 'payment_date': self.today(), 'user_id': actor['id'], 'created_at': now, **payment})
            if data.get('held_ref'):
                self.services.held_bills.release(actor, data['held_ref'])  # a resumed held bill is done once it is billed
            self.audit(actor, 'Invoice finalized', 'INVOICE', invoice_id,
                       new={'invoice_number': number, 'total': total, 'discount': discount, 'discount_approved_by': approved_by})
        return invoice_id, number

    def _discount_approval(self, actor, discount, subtotal, approval):
        """Discounts above the shop limit need someone with 'Give or approve any discount'.

        Returns the approver's user id when an approval was needed, otherwise None.
        """
        limit = v.number(self.services.settings.get_settings().get('max_discount_pct'), 100)
        if not discount or not subtotal or discount / subtotal * 100 <= limit + 1e-9 or self.can(actor, P.DISCOUNT_APPROVE):
            return None
        approval = approval if isinstance(approval, dict) else {}
        if not approval.get('username'):
            raise ValidationError(f'Discounts above {limit:g}% need approval from a manager.', code='DISCOUNT_APPROVAL_REQUIRED',
                                  max_discount_pct=limit)
        approver = self.services.auth.verify_credentials(approval.get('username'), approval.get('password'), purpose='discount')
        if not self.can(approver, P.DISCOUNT_APPROVE):
            raise ValidationError(f"{approver['username']} is not allowed to approve discounts.", code='DISCOUNT_APPROVAL_REQUIRED',
                                  max_discount_pct=limit)
        return approver['id']

    # --- credit dues --------------------------------------------------------
    def dues(self):
        """Outstanding credit grouped by customer, largest first."""
        customers = {}
        for bill in self.repos.reports.dues():
            key = bill['customer_id'] or f"walk-in:{bill['customer_name_snapshot']}"
            entry = customers.setdefault(key, {'customer_id': bill['customer_id'], 'name': bill['customer_name_snapshot'],
                                               'phone': bill['customer_phone'], 'total_due': 0.0, 'oldest': bill['invoice_date'], 'bills': []})
            entry['total_due'] = money(entry['total_due'] + bill['outstanding'])
            entry['bills'].append(bill)
        rows = sorted(customers.values(), key=lambda c: -c['total_due'])
        return {'customers': rows, 'total_due': money(sum(c['total_due'] for c in rows))}

    # --- changing bills ---------------------------------------------------------
    def void(self, actor, invoice_id):
        """Cancel a bill and put its stock back. Payments stay on record."""
        with self.transaction():
            invoice = self.visible_invoice(actor, invoice_id)  # only bills this user may see
            if not invoice or invoice['status'] != 'FINALIZED':
                raise ValidationError('Finalized invoice not found or already voided.')
            if self.repos.invoices.posted_return_count(invoice_id):
                raise ValidationError('This sale has a posted return and cannot be deleted.')
            items = self.repos.invoices.items(invoice_id)
            for item in items:
                self.repos.inventory.add_movement(item['product_id'], 'SALE_VOID', item['qty_base'], self.now(), unit_cost=item['cost_snapshot'],
                                                  ref_type='INVOICE', ref_id=invoice_id, reason='Voided sale stock restoration', user_id=actor['id'])
            self.repos.invoices.mark_void(invoice_id, actor['id'], self.now())
            self.audit(actor, 'Invoice voided', 'INVOICE', invoice_id, previous=invoice, new={'status': 'VOID', 'stock_restored': len(items)})
        return {'invoice_id': invoice_id, 'restored_items': len(items)}

    def edit(self, actor, invoice_id, data):
        """Re-issue a bill with new items: the original is voided and linked to the new one."""
        reason = v.text(data.get('reason'), 500)
        if len(reason) < 3:
            raise ValidationError('Enter a reason for editing this bill.')
        with self.transaction():
            old = self.visible_invoice(actor, invoice_id)  # only bills this user may see
            if not old or old['status'] != 'FINALIZED':
                raise ValidationError('Only a finalized bill can be edited.')
            old_items = self.repos.invoices.items(invoice_id)
            self.void(actor, invoice_id)
            new_id, new_number = self.create_sale(actor, data, invoice_date=old['invoice_date'], billed_by=old['user_id'])
            edited_at = self.now()
            self.repos.invoices.link_revision(invoice_id, new_id, reason, actor['id'], edited_at)
            new_invoice = self.repos.invoices.get(new_id)
            summary = lambda items: [{'product_id': i['product_id'], 'name': i['product_name_snapshot'], 'qty': i['qty_input']} for i in items]
            self.audit(actor, 'Invoice edited', 'INVOICE', new_id,
                       previous={'invoice_id': invoice_id, 'invoice_number': old['invoice_number'], 'total': old['grand_total'], 'items': summary(old_items)},
                       new={'invoice_id': new_id, 'invoice_number': new_number, 'total': new_invoice['grand_total'],
                            'items': summary(self.repos.invoices.items(new_id)), 'reason': reason})
        return {'invoice_id': new_id, 'invoice_number': new_number, 'previous_invoice_number': old['invoice_number'], 'edited_at': edited_at}

    def record_return(self, actor, data):
        invoice_id = v.integer_id(data.get('invoice_id'), 'Invoice')
        with self.transaction():
            invoice = self.visible_invoice(actor, invoice_id)  # only bills this user may see
            if not invoice or invoice['status'] != 'FINALIZED':
                raise ValidationError('Finalized invoice not found.')
            lines, refund = [], 0.0
            for entry in data.get('items') or []:
                item = self.repos.invoices.item(v.integer_id((entry or {}).get('invoice_item_id'), 'Invoice item'), invoice_id)
                qty = v.number(entry.get('qty'), 0)
                if not item or qty <= 0 or self.repos.invoices.returned_qty(item['id']) + qty > item['qty_input'] + 0.0001:
                    raise ValidationError('Invalid return quantity for one of the items.')
                qty_base = item['qty_base'] / item['qty_input'] * qty
                amount = money(item['unit_price'] * qty - item['discount'] * (qty / item['qty_input']))
                lines.append((item, qty, qty_base, amount))
                refund += amount
            if not lines:
                raise ValidationError('Select at least one item to return.')
            refund = money(refund)
            # If the customer still owes on this bill, the returned goods come off that first; only the rest is paid back.
            credit_adjusted = money(min(refund, invoice['outstanding']))
            if credit_adjusted:
                self.repos.invoices.set_outstanding(invoice_id, money(invoice['outstanding'] - credit_adjusted))
            number = f"RET-{self.today().replace('-', '')}-{self.repos.sequences.next('return'):05d}"
            return_id = self.repos.invoices.create_return({
                'return_number': number, 'invoice_id': invoice_id, 'customer_id': invoice['customer_id'], 'return_date': self.today(),
                'reason': v.optional_text(data.get('reason')), 'total_refund': refund, 'credit_adjusted': credit_adjusted,
                'user_id': actor['id'], 'created_at': self.now(),
            })
            for item, qty, qty_base, amount in lines:
                self.repos.invoices.add_return_item({'return_id': return_id, 'invoice_item_id': item['id'], 'product_id': item['product_id'],
                                                     'qty_input': qty, 'qty_base': qty_base, 'refund_amount': amount})
                self.repos.inventory.add_movement(item['product_id'], 'RETURN_IN', qty_base, self.now(), unit_cost=item['cost_snapshot'],
                                                  ref_type='RETURN', ref_id=return_id, reason='Sales return', user_id=actor['id'])
            self.audit(actor, 'Sale returned', 'RETURN', return_id,
                       new={'invoice_id': invoice_id, 'refund': refund, 'credit_adjusted': credit_adjusted})
        return {'return_number': number, 'refund': refund, 'credit_adjusted': credit_adjusted, 'paid_back': money(refund - credit_adjusted)}

    def collect_payment(self, actor, data):
        """Record money received against a bill's outstanding credit."""
        invoice_id = v.integer_id(data.get('invoice_id'), 'Invoice')
        amount = v.number(data.get('amount'), 0)
        with self.transaction():
            invoice = self.visible_invoice(actor, invoice_id)  # only bills this user may see
            if not invoice or invoice['status'] != 'FINALIZED':
                raise ValidationError('Finalized invoice not found.')
            if amount <= 0 or amount > invoice['outstanding'] + 0.01:
                raise ValidationError('Payment must be greater than 0 and not exceed outstanding.')
            amount = money(amount)
            self.repos.invoices.add_payment({
                'invoice_id': invoice_id, 'customer_id': invoice['customer_id'], 'payment_date': self.today(),
                'mode': v.text(data.get('mode'), 20) or 'Cash', 'amount': amount, 'reference': v.optional_text(data.get('reference'), 100),
                'notes': v.optional_text(data.get('notes')), 'user_id': actor['id'], 'created_at': self.now(),
            })
            outstanding = money(invoice['outstanding'] - amount)
            self.repos.invoices.apply_payment(invoice_id, amount, outstanding)
            self.audit(actor, 'Payment collected', 'PAYMENT', invoice_id, new={'amount': amount, 'mode': data.get('mode')})
        return outstanding
