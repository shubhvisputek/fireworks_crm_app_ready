"""Shop expenses and recurring expense templates."""
from crm.domain import validation as v
from crm.domain.money import money
from crm.errors import ValidationError
from crm.services.base import Service

FREQUENCIES = ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY')


class ExpenseService(Service):
    def list(self, start=None, end=None):
        start = v.iso_date(start, 'Start date') or self.today()
        end = v.iso_date(end, 'End date') or self.today()
        return self.repos.expenses.list(start, end)

    def total(self, start, end):
        return money(self.repos.expenses.total(start, end))

    def create(self, actor, data):
        amount = v.number(data.get('amount'))
        if amount <= 0:
            raise ValidationError('Expense amount must be greater than 0.')
        values = {
            'expense_date': v.iso_date(data.get('expense_date'), 'Expense date') or self.today(),
            'category': v.text(data.get('category'), 100) or 'Miscellaneous', 'amount': money(amount),
            'payment_mode': v.text(data.get('payment_mode'), 30) or 'Cash', 'vendor': v.optional_text(data.get('vendor'), 200),
            'notes': v.optional_text(data.get('notes'), 1000), 'attachment_name': v.optional_text(data.get('attachment_name'), 200),
            'recurring': int(v.parse_bool(data.get('recurring'))), 'user_id': actor['id'], 'created_at': self.now(),
        }
        with self.transaction():
            expense_id = self.repos.expenses.create(values)
            self.audit(actor, 'Expense added', 'EXPENSE', expense_id, new=values)
        return expense_id

    def list_recurring(self):
        return self.repos.expenses.list_recurring()

    def create_recurring(self, actor, data):
        amount = v.number(data.get('amount'))
        if amount <= 0:
            raise ValidationError('Recurring expense amount must be greater than 0.')
        if not data.get('category') or not data.get('frequency') or not data.get('start_date'):
            raise ValidationError('Category, frequency, and start date are required.')
        frequency = v.text(data.get('frequency'), 20).upper()
        if frequency not in FREQUENCIES:
            raise ValidationError(f'Frequency must be one of: {", ".join(f.title() for f in FREQUENCIES)}.')
        start = v.iso_date(data.get('start_date'), 'Start date', required=True)
        end = v.iso_date(data.get('end_date'), 'End date')
        if end and end < start:
            raise ValidationError('End date cannot be before the start date.')
        values = {
            'category': v.text(data.get('category'), 100), 'amount': money(amount), 'payment_mode': v.text(data.get('payment_mode'), 30) or 'Cash',
            'vendor': v.optional_text(data.get('vendor'), 200), 'frequency': frequency.title(), 'start_date': start, 'end_date': end,
            'active': 1, 'notes': v.optional_text(data.get('notes'), 1000), 'created_at': self.now(),
        }
        with self.transaction():
            recurring_id = self.repos.expenses.create_recurring(values)
            self.audit(actor, 'Recurring expense added', 'RECURRING_EXPENSE', recurring_id, new=values)
        return recurring_id
