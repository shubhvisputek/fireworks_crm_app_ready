"""Dashboard, analytics and the JSON backup."""
import datetime as dt
import json

from crm.domain import validation as v
from crm.domain.money import money
from crm.domain.permissions import Permission
from crm.domain.visibility import strip_fields
from crm.services.base import Service


def strip_json_text(text):
    """Cost/profit fields removed from a JSON string (audit log values)."""
    if not text:
        return text
    try:
        return json.dumps(strip_fields(json.loads(text)))
    except (TypeError, ValueError):
        return None

PRESETS = ('today', 'yesterday', '7d', 'month', 'season')


class ReportService(Service):
    def sales_kpis(self, start, end):
        totals = self.repos.reports.sales_totals(start, end)
        cogs = self.repos.reports.cost_of_goods(start, end)
        profit = totals['sales'] - cogs
        margin = (profit / totals['sales'] * 100) if totals['sales'] else 0
        return {'sales': money(totals['sales']), 'bills': totals['bills'], 'avg_bill': money(totals['avg_bill']),
                'discounts': money(totals['discounts']), 'cogs': money(cogs), 'gross_profit': money(profit), 'gross_margin': money(margin)}

    def resolve_preset(self, preset):
        today = self.clock.today()
        if preset == 'yesterday':
            day = today - dt.timedelta(days=1)
            return day.isoformat(), day.isoformat()
        if preset == '7d':
            return (today - dt.timedelta(days=6)).isoformat(), today.isoformat()
        if preset == 'month':
            return today.replace(day=1).isoformat(), today.isoformat()
        if preset == 'season':
            targets = self.services.settings.get_targets()
            if targets.get('season_start') and targets.get('season_end'):
                return targets['season_start'], targets['season_end']
            return f'{today.year}-10-01', f'{today.year}-10-31'
        return today.isoformat(), today.isoformat()

    def own_kpis(self, start, end, user_id):
        """Sales figures for one person's bills (people without shop-wide analytics see only their own)."""
        t = self.repos.insights.totals(start, end, user_id)
        return {'sales': money(t['sales']), 'bills': t['bills'], 'avg_bill': money(t['avg_bill']), 'discounts': money(t['discounts'])}

    def dashboard(self, actor, day=None):
        day = v.iso_date(day, 'Date') or self.today()
        date = dt.date.fromisoformat(day)
        yesterday = (date - dt.timedelta(days=1)).isoformat()
        last_week = (date - dt.timedelta(days=7)).isoformat()
        low_count, attention = self.repos.reports.low_stock(limit=10)
        shop_wide = self.can(actor, Permission.ANALYTICS_VIEW)

        def kpis(d):
            return self.sales_kpis(d, d) if shop_wide else self.own_kpis(d, d, actor['id'])
        expenses = (self.services.expenses.total(day, day) if self.can(actor, Permission.EXPENSES_VIEW)
                    else money(sum(e['amount'] for e in self.services.expenses.list(actor, day, day))))
        return self.visible(actor, {
            'scope': 'all' if shop_wide else 'own',
            'today': kpis(day), 'yesterday': kpis(yesterday),
            'last_week': kpis(last_week), 'expenses': expenses,
            'low_stock': low_count, 'inventory_cost': money(self.repos.reports.inventory_cost()),
            'target': self.services.settings.get_targets().get('daily'), 'attention': attention,
            'storage': self.services.inventory.storage_status(),
        })

    def analytics(self, actor, start=None, end=None, preset=None):
        if preset:
            start, end = self.resolve_preset(preset)
        start = v.iso_date(start, 'Start date') or self.today()
        end = v.iso_date(end, 'End date') or self.today()
        kpi = self.sales_kpis(start, end)
        expenses = self.services.expenses.total(start, end)
        slow = self.repos.reports.slow_movers(start, end)
        return self.visible(actor, {
            'period': {'start': start, 'end': end}, 'kpi': kpi, 'expenses': expenses, 'net_profit': money(kpi['gross_profit'] - expenses),
            'hourly': self.repos.reports.hourly(start, end), 'top_products': self.repos.reports.top_products(start, end),
            'categories': self.repos.reports.categories(start, end), 'payments': self.repos.reports.payment_mix(start, end),
            'customers': self.repos.reports.customer_mix(start, end), 'slow_movers': slow, 'bottom_products': slow[:10],
            'discounts': self.repos.reports.discounts(start, end), 'target': self.services.settings.get_targets(),
        })

    def backup(self, actor):
        dump = self.repos.backup.dump()
        if not self.can(actor, Permission.PROFIT_VIEW):
            # Audit before/after values are JSON text, so cost prices inside them are removed here too.
            for entry in dump.get('audit_logs', []):
                for key in ('previous_json', 'new_json'):
                    entry[key] = strip_json_text(entry.get(key))
        data = self.visible(actor, dump)
        # Credentials never leave the server, even in a backup.
        for user in data.get('users', []):
            user.pop('password_hash', None)
            user.pop('session_version', None)
        return data
