"""Day-end cash closing: what each cashier should have against what they counted."""
import datetime as dt
import json

from crm.domain import validation as v
from crm.domain.money import money
from crm.domain.permissions import Permission as P
from crm.errors import ValidationError
from crm.services.base import Service


class CashClosingService(Service):
    def _period_start(self, user_id):
        last = self.repos.cash_closings.last_for_user(user_id)
        # Midnight in the shop's timezone, in the same ISO format as stored timestamps.
        start_of_day = dt.datetime.combine(self.clock.today(), dt.time(), self.clock.tz).isoformat(timespec='seconds')
        if last and last['closed_at'] > start_of_day:
            return last['closed_at']
        return start_of_day

    def summary(self, actor):
        """Expected takings for this user since their last closing (or since the start of today)."""
        since, until = self._period_start(actor['id']), self.now()
        by_mode = self.repos.cash_closings.payments_by_mode(actor['id'], since, until)
        refunds = money(self.repos.cash_closings.refunds(actor['id'], since, until))
        cash_expenses = money(self.repos.cash_closings.cash_expenses(actor['id'], since, until))
        cash_taken = sum(row['amount'] for row in by_mode if row['mode'].upper() == 'CASH')
        return {
            'period_start': since, 'period_end': until, 'modes': by_mode, 'bills': sum(row['bills'] for row in by_mode),
            'refunds': refunds, 'cash_expenses': cash_expenses,
            'expected_cash': money(cash_taken - refunds - cash_expenses),
        }

    def close(self, actor, data):
        counted_cash = v.amount(data.get('counted_cash'), 'Counted cash')
        counted_other = data.get('counted') if isinstance(data.get('counted'), dict) else {}
        with self.transaction():
            summary = self.summary(actor)
            if not summary['modes'] and not summary['refunds'] and not summary['cash_expenses'] and not counted_cash:
                raise ValidationError('There is nothing to close since your last closing.')
            counted = {'Cash': money(counted_cash), **{str(k)[:20]: money(v.number(val)) for k, val in counted_other.items() if str(k).upper() != 'CASH'}}
            difference = money(counted_cash - summary['expected_cash'])
            values = {
                'user_id': actor['id'], 'business_date': self.today(), 'period_start': summary['period_start'], 'closed_at': summary['period_end'],
                'expected_json': json.dumps({**{row['mode']: row['amount'] for row in summary['modes']}, 'refunds': summary['refunds'],
                                             'cash_expenses': summary['cash_expenses']}),
                'counted_json': json.dumps(counted), 'expected_cash': summary['expected_cash'], 'counted_cash': money(counted_cash),
                'difference': difference, 'bills': summary['bills'], 'notes': v.optional_text(data.get('notes'), 500),
            }
            closing_id = self.repos.cash_closings.create(values)
            self.audit(actor, 'Cash drawer closed', 'CASH_CLOSING', closing_id, new=values)
        return {'id': closing_id, 'expected_cash': summary['expected_cash'], 'counted_cash': money(counted_cash), 'difference': difference}

    def history(self, actor):
        own_only = None if self.can(actor, P.CASH_CLOSING_VIEW_ALL) else actor['id']
        rows = self.repos.cash_closings.list(user_id=own_only)
        for row in rows:
            row['expected'] = json.loads(row.pop('expected_json') or '{}')
            row['counted'] = json.loads(row.pop('counted_json') or '{}')
        return rows
