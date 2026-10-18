"""Dashboard analytics: one period, compared with the period before it, seen from several angles.

Each section is included only when the user may see it, and everything passes
through ``visible()`` so cost and profit never reach users without that permission.
Users without *Sales analytics* get the same views limited to their own bills.
"""
import datetime as dt

from crm.domain import validation as v
from crm.domain.money import money
from crm.domain.permissions import Permission as P
from crm.errors import ValidationError
from crm.services.base import Service

PRESETS = ('today', 'yesterday', '7d', '30d', 'month', 'last_month', 'season')
MAX_DAYS = 400
DEAD_STOCK_DAYS = 30
COVER_LOOKBACK_DAYS = 30
DUE_BUCKETS = [(7, '0–7 days'), (30, '8–30 days'), (60, '31–60 days'), (None, 'Over 60 days')]


def _pct(part, whole):
    return money(part / whole * 100) if whole else 0


def _days(start, end):
    first = dt.date.fromisoformat(start)
    return [(first + dt.timedelta(days=n)).isoformat() for n in range((dt.date.fromisoformat(end) - first).days + 1)]


class InsightService(Service):
    def resolve_period(self, preset=None, start=None, end=None):
        today = self.clock.today()
        if preset == 'yesterday':
            day = today - dt.timedelta(days=1)
            return day.isoformat(), day.isoformat()
        if preset == '7d':
            return (today - dt.timedelta(days=6)).isoformat(), today.isoformat()
        if preset == '30d':
            return (today - dt.timedelta(days=29)).isoformat(), today.isoformat()
        if preset == 'month':
            return today.replace(day=1).isoformat(), today.isoformat()
        if preset == 'last_month':
            last = today.replace(day=1) - dt.timedelta(days=1)
            return last.replace(day=1).isoformat(), last.isoformat()
        if preset == 'season':
            return self.services.reports.resolve_preset('season')
        if preset == 'today' or not (start or end):
            return today.isoformat(), today.isoformat()
        start = v.iso_date(start, 'Start date') or today.isoformat()
        end = v.iso_date(end, 'End date') or today.isoformat()
        if start > end:
            raise ValidationError('Start date must be on or before the end date.')
        return start, end

    def insights(self, actor, preset=None, start=None, end=None):
        if preset and preset not in PRESETS:
            raise ValidationError('Unknown period.')
        start, end = self.resolve_period(preset, start, end)
        days = _days(start, end)
        if len(days) > MAX_DAYS:
            raise ValidationError(f'Choose a period of at most {MAX_DAYS} days.')
        prev_end = (dt.date.fromisoformat(start) - dt.timedelta(days=1)).isoformat()
        prev_start = (dt.date.fromisoformat(prev_end) - dt.timedelta(days=len(days) - 1)).isoformat()
        full = self.can(actor, P.ANALYTICS_VIEW)
        user_id = None if full else actor['id']
        ctx = {'start': start, 'end': end, 'prev_start': prev_start, 'prev_end': prev_end, 'days': days, 'user_id': user_id}

        data = {
            'period': {'start': start, 'end': end, 'prev_start': prev_start, 'prev_end': prev_end, 'days': len(days),
                       'preset': preset or 'custom'},
            'scope': 'all' if full else 'own',
            'sales': self._sales(ctx),
            'products': self._products(ctx),
        }
        if full:
            data['customers'] = self._customers(ctx, with_dues=self.can(actor, P.DUES_VIEW))
            data['stock'] = self._stock()
            data['finance'] = self._finance(ctx, data['sales']['kpi'], with_expenses=self.can(actor, P.EXPENSES_VIEW))
            if self.can(actor, P.SALES_VIEW):
                data['team'] = self._team(ctx)
        return self.visible(actor, data)

    # ---- sections ----------------------------------------------------------
    def _kpi(self, start, end, user_id):
        t = self.repos.insights.totals(start, end, user_id)
        profit = t['sales'] - t['cogs']
        return {'sales': money(t['sales']), 'bills': t['bills'], 'avg_bill': money(t['avg_bill']), 'items': money(t['items']),
                'customers': t['customers'], 'discounts': money(t['discounts']), 'discount_pct': _pct(t['discounts'], t['gross_sales']),
                'credit': money(t['credit']), 'cogs': money(t['cogs']), 'gross_profit': money(profit),
                'gross_margin': _pct(profit, t['sales'])}

    def _sales(self, ctx):
        r = self.repos.insights
        uid = ctx['user_id']
        current = {row['day']: row for row in r.daily(ctx['start'], ctx['end'], uid)}
        previous = r.daily(ctx['prev_start'], ctx['prev_end'], uid)
        prev_by_day = {row['day']: row for row in previous}
        prev_days = _days(ctx['prev_start'], ctx['prev_end'])
        trend = []
        for n, day in enumerate(ctx['days']):
            row = current.get(day, {})
            prev = prev_by_day.get(prev_days[n], {})
            sales, cogs = row.get('sales', 0), row.get('cogs', 0)
            trend.append({'day': day, 'sales': money(sales), 'bills': row.get('bills', 0), 'cogs': money(cogs),
                          'profit': money(sales - cogs), 'prev_day': prev_days[n], 'prev_sales': money(prev.get('sales', 0))})
        cells = r.weekday_hour(ctx['start'], ctx['end'], uid)
        hourly = [{'hour': h, 'sales': 0, 'bills': 0} for h in range(24)]
        for cell in cells:
            if 0 <= (cell['hour'] or 0) < 24:
                hourly[cell['hour']]['sales'] = money(hourly[cell['hour']]['sales'] + cell['sales'])
                hourly[cell['hour']]['bills'] += cell['bills']
        return {
            'kpi': self._kpi(ctx['start'], ctx['end'], uid),
            'previous': self._kpi(ctx['prev_start'], ctx['prev_end'], uid),
            'trend': trend, 'hourly': hourly, 'heatmap': cells,
            'bill_sizes': r.bill_sizes(ctx['start'], ctx['end'], uid),
            'payments': r.payments(ctx['start'], ctx['end'], uid),
            'exceptions': r.exceptions(ctx['start'], ctx['end'], uid),
        }

    def _products(self, ctx):
        r = self.repos.insights
        rows = r.products(ctx['start'], ctx['end'], ctx['user_id'])
        before = {row['product_id']: row['revenue'] for row in r.products(ctx['prev_start'], ctx['prev_end'], ctx['user_id'])}
        total = sum(row['revenue'] for row in rows)
        for row in rows:
            row['share'] = _pct(row['revenue'], total)
            row['gross_margin'] = _pct(row['profit'], row['revenue'])
            row['prev_revenue'] = money(before.get(row['product_id'], 0))
            row['change'] = money(row['revenue'] - row['prev_revenue'])
        # How concentrated sales are: the share of revenue earned by the best-selling fifth of products sold.
        top_fifth = rows[:max(1, round(len(rows) / 5))] if rows else []
        movers = sorted((row for row in rows if row['prev_revenue']), key=lambda row: row['change'])
        categories = r.categories(ctx['start'], ctx['end'], ctx['user_id'])
        for row in categories:
            row['share'] = _pct(row['revenue'], total)
            row['gross_margin'] = _pct(row['profit'], row['revenue'])
        return {
            'top': rows[:10], 'bottom': rows[::-1][:10] if len(rows) > 10 else [],
            'rising': [row for row in movers[::-1] if row['change'] > 0][:5],
            'falling': [row for row in movers if row['change'] < 0][:5],
            'categories': categories, 'sold_count': len(rows),
            'concentration': {'top_products': len(top_fifth), 'share': _pct(sum(row['revenue'] for row in top_fifth), total)},
        }

    def _customers(self, ctx, with_dues):
        r = self.repos.insights
        data = {
            'types': r.customer_types(ctx['start'], ctx['end']),
            'top': r.top_customers(ctx['start'], ctx['end']),
            'new_vs_repeat': r.new_vs_returning(ctx['start'], ctx['end']),
        }
        if with_dues:
            today = self.clock.today()
            buckets = [{'label': label, 'amount': 0, 'bills': 0} for _, label in DUE_BUCKETS]
            for due in r.open_dues():
                age = (today - dt.date.fromisoformat(due['invoice_date'])).days
                n = next(i for i, (limit, _) in enumerate(DUE_BUCKETS) if limit is None or age <= limit)
                buckets[n]['amount'] = money(buckets[n]['amount'] + due['outstanding'])
                buckets[n]['bills'] += 1
            data['dues_aging'] = buckets
            data['dues_total'] = money(sum(b['amount'] for b in buckets))
        return data

    def _team(self, ctx):
        rows = self.repos.insights.staff(ctx['start'], ctx['end'])
        total = sum(row['sales'] for row in rows)
        for row in rows:
            row['share'] = _pct(row['sales'], total)
        return {'staff': rows}

    def _stock(self):
        r = self.repos.insights
        today = self.clock.today()
        categories = r.stock_by_category()
        since = (today - dt.timedelta(days=COVER_LOOKBACK_DAYS - 1)).isoformat()
        sold = self.repos.reports.quantity_sold_by_product(since, today.isoformat())
        running_out = []
        for item in r.stock_levels():
            rate = (sold.get(item['product_id']) or 0) / COVER_LOOKBACK_DAYS
            if rate > 0:
                cover = max(item['stock'], 0) / rate
                if cover <= 14:
                    running_out.append({'name': item['name'], 'sku': item['sku'], 'stock': item['stock'],
                                        'per_day': money(rate), 'days_left': money(cover)})
        running_out.sort(key=lambda item: item['days_left'])
        dead_since = (today - dt.timedelta(days=DEAD_STOCK_DAYS)).isoformat()
        return {
            'categories': categories,
            'totals': {key: money(sum(row[key] or 0 for row in categories)) for key in ('units', 'inventory_cost', 'retail_value')}
            | {key: sum(row[key] or 0 for row in categories) for key in ('products', 'out_of_stock', 'low')},
            'running_out': running_out[:10], 'dead_stock': r.dead_stock(dead_since), 'dead_stock_days': DEAD_STOCK_DAYS,
            'storage': self.services.inventory.storage_status(),
        }

    def _finance(self, ctx, kpi, with_expenses):
        r = self.repos.insights
        expenses = self.services.expenses.total(ctx['start'], ctx['end'])
        data = {
            'pnl': {'sales': kpi['sales'], 'cogs': kpi['cogs'], 'gross_profit': kpi['gross_profit'], 'expenses': money(expenses),
                    'net_profit': money(kpi['gross_profit'] - expenses)},
            'targets': self._targets(),
        }
        if with_expenses:
            data['expense_categories'] = r.expenses_by_category(ctx['start'], ctx['end'])
            by_day = {row['day']: row['amount'] for row in r.expenses_daily(ctx['start'], ctx['end'])}
            data['expense_trend'] = [{'day': day, 'amount': money(by_day.get(day, 0))} for day in ctx['days']]
        return data

    def _targets(self):
        targets = self.services.settings.get_targets()
        today = self.clock.today()
        week_start = today - dt.timedelta(days=today.weekday())
        season_start, season_end = self.services.reports.resolve_preset('season')
        periods = [('daily', 'Today', today.isoformat(), today.isoformat()),
                   ('weekly', 'This week', week_start.isoformat(), today.isoformat()),
                   ('monthly', 'This month', today.replace(day=1).isoformat(), today.isoformat()),
                   ('seasonal', 'Season', season_start, min(season_end, today.isoformat()))]
        result = []
        for key, label, start, end in periods:
            target = targets.get(key) or 0
            actual = self.repos.insights.totals(start, end)['sales'] if start <= end else 0
            result.append({'key': key, 'label': label, 'start': start, 'end': end, 'target': money(target),
                           'actual': money(actual), 'pct': _pct(actual, target)})
        return result
