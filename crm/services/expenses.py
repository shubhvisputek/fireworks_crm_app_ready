"""Shop expenses and recurring expense templates."""
from crm.domain import validation as v
from crm.domain.money import money
from crm.domain.permissions import Permission as P
from crm.errors import NotFoundError, PermissionDenied, ValidationError
from crm.services.base import Service

FREQUENCIES = ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'YEARLY')


class ExpenseService(Service):
    def list(self, actor, start=None, end=None):
        """Everyone's expenses with 'See all expenses', otherwise only the ones this user entered."""
        start = v.iso_date(start, 'Start date') or self.today()
        end = v.iso_date(end, 'End date') or self.today()
        return self.repos.expenses.list(start, end, user_id=None if self.can(actor, P.EXPENSES_VIEW) else actor['id'])

    def total(self, start, end):
        return money(self.repos.expenses.total(start, end))

    def _expense_values(self, data):
        amount = v.number(data.get('amount'))
        if amount <= 0:
            raise ValidationError('Expense amount must be greater than 0.')
        return {
            'expense_date': v.iso_date(data.get('expense_date'), 'Expense date') or self.today(),
            'category': v.text(data.get('category'), 100) or 'Miscellaneous', 'amount': money(amount),
            'payment_mode': v.text(data.get('payment_mode'), 30) or 'Cash', 'vendor': v.optional_text(data.get('vendor'), 200),
            'notes': v.optional_text(data.get('notes'), 1000), 'attachment_name': v.optional_text(data.get('attachment_name'), 200),
            'recurring': int(v.parse_bool(data.get('recurring'))),
        }

    def create(self, actor, data):
        values = {**self._expense_values(data), 'user_id': actor['id'], 'created_at': self.now()}
        with self.transaction():
            expense_id = self.repos.expenses.create(values)
            self.audit(actor, 'Expense added', 'EXPENSE', expense_id, new=values)
        return expense_id

    def _editable(self, actor, expense_id):
        """The expense, if this user may change it: their own, or anyone's with 'Edit and delete everyone's expenses'."""
        expense = self.repos.expenses.get(expense_id)
        if not expense:
            raise NotFoundError('Expense not found.')
        if expense['user_id'] != actor['id'] and not self.can(actor, P.EXPENSES_MANAGE):
            raise PermissionDenied('You can only change expenses you entered yourself.')
        return expense

    def get(self, actor, expense_id):
        expense = self.repos.expenses.get(expense_id)
        if not expense or (expense['user_id'] != actor['id'] and not self.can(actor, P.EXPENSES_VIEW)):
            raise NotFoundError('Expense not found.')
        return expense

    def update(self, actor, expense_id, data):
        values = self._expense_values(data)
        with self.transaction():
            previous = self._editable(actor, expense_id)
            self.repos.expenses.update(expense_id, values)
            self.audit(actor, 'Expense edited', 'EXPENSE', expense_id, previous=previous, new=values)
        return self.repos.expenses.get(expense_id)

    def delete(self, actor, expense_id):
        with self.transaction():
            previous = self._editable(actor, expense_id)
            self.repos.expenses.delete(expense_id)
            self.audit(actor, 'Expense deleted', 'EXPENSE', expense_id, previous=previous)

    def list_recurring(self):
        return self.repos.expenses.list_recurring()

    def _recurring_values(self, data):
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
        return {
            'category': v.text(data.get('category'), 100), 'amount': money(amount), 'payment_mode': v.text(data.get('payment_mode'), 30) or 'Cash',
            'vendor': v.optional_text(data.get('vendor'), 200), 'frequency': frequency.title(), 'start_date': start, 'end_date': end,
            'notes': v.optional_text(data.get('notes'), 1000),
        }

    def create_recurring(self, actor, data):
        values = {**self._recurring_values(data), 'active': 1, 'created_at': self.now()}
        with self.transaction():
            recurring_id = self.repos.expenses.create_recurring(values)
            self.audit(actor, 'Recurring expense added', 'RECURRING_EXPENSE', recurring_id, new=values)
        return recurring_id

    def _recurring(self, recurring_id):
        recurring = self.repos.expenses.get_recurring(recurring_id)
        if not recurring:
            raise NotFoundError('Recurring expense not found.')
        return recurring

    def update_recurring(self, actor, recurring_id, data):
        values = self._recurring_values(data)
        if 'active' in data:
            values['active'] = int(v.parse_bool(data.get('active')))
        with self.transaction():
            previous = self._recurring(recurring_id)
            self.repos.expenses.update_recurring(recurring_id, values)
            self.audit(actor, 'Recurring expense edited', 'RECURRING_EXPENSE', recurring_id, previous=previous, new=values)
        return self.repos.expenses.get_recurring(recurring_id)

    def set_recurring_active(self, actor, recurring_id, active):
        active = int(v.parse_bool(active))
        with self.transaction():
            previous = self._recurring(recurring_id)
            self.repos.expenses.update_recurring(recurring_id, {'active': active})
            self.audit(actor, 'Recurring expense resumed' if active else 'Recurring expense paused', 'RECURRING_EXPENSE', recurring_id,
                       previous=previous, new={'active': active})
        return self.repos.expenses.get_recurring(recurring_id)

    def delete_recurring(self, actor, recurring_id):
        with self.transaction():
            previous = self._recurring(recurring_id)
            self.repos.expenses.delete_recurring(recurring_id)
            self.audit(actor, 'Recurring expense deleted', 'RECURRING_EXPENSE', recurring_id, previous=previous)
