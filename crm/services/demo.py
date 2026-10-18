"""Optional demo data (FIREWORKS_SEED_DEMO=1), built through the real services."""
import datetime as dt

from crm.services.base import Service

CATEGORIES = [('Sparklers', 'Ground'), ('Aerial Shots', 'Aerial'), ('Rockets', 'Aerial'), ('Gift Boxes', 'Combo'),
              ('Ground Spinners', 'Ground'), ('Flower Pots', 'Ground'), ('Sound Crackers', 'Crackers')]
CUSTOMERS = [('Aarav Traders', 'WHOLESALE', '9876500011'), ('Mahalaxmi Distributors', 'WHOLESALE', '9876500012'),
             ('Rohan Patil', 'RETAIL', '9876500013'), ('Sneha Kulkarni', 'RETAIL', '9876500014')]
# Shop hours with an evening rush, so the hour charts look like a real day.
HOURS = [10, 11, 12, 13, 15, 16, 17, 18, 18, 19, 19, 20, 20, 21]
EXPENSES = [(0, 'Transport/Freight', 18000), (1, 'Salaries/Wages', 12000), (2, 'Packaging', 4500), (3, 'Marketing', 7500), (7, 'Rent', 25000)]


class DemoService(Service):
    def seed(self):
        if self.repos.products.list(limit=1):
            return
        admin = self.repos.users.first_active_owner()
        services = self.services
        product_ids = []
        index = 0
        for category, sub in CATEGORIES:
            for n in range(5):
                index += 1
                cost = round(40 + index * 7.25, 2)
                product_ids.append(services.catalog.create_product(admin, {
                    'sku': f'FW-{index:04d}', 'name': f"{category.rstrip('s')} {n + 1}", 'category': category, 'subcategory': sub,
                    'brand': 'Demo Brand', 'unit': 'Box', 'unit_price': round(cost * 2.15, 2), 'cost_price': cost,
                    'opening_stock': 200 + index * 5, 'reorder_level': 20,
                }))
        customer_ids = [services.customers.create(admin, {'name': name, 'customer_type': kind, 'phone': phone}) for name, kind, phone in CUSTOMERS]
        today = self.clock.today()
        for days_ago in range(20, -1, -1):
            day = (today - dt.timedelta(days=days_ago)).isoformat()
            bills = 5 if days_ago > 2 else (8 if days_ago else 24)
            for b in range(bills):
                items = [{'product_id': product_ids[(b * 3 + j + days_ago) % len(product_ids)], 'qty': 1 + (b + j) % 4} for j in range(1 + b % 3)]
                paid = round(sum(round(self.repos.products.get(i['product_id'])['default_unit_price'] * i['qty'], 2) for i in items), 2)
                payments = [{'mode': 'UPI' if b % 2 else 'Cash', 'amount': paid}]
                if (b + days_ago) % 4 == 0:
                    upfront = round(paid * 0.35, 2)
                    payments = [{'mode': 'Cash', 'amount': upfront}, {'mode': 'Credit', 'amount': round(paid - upfront, 2)}]
                invoice_id, _ = services.sales.create_sale(admin, {'customer_id': customer_ids[(b + days_ago) % len(customer_ids)],
                                                                   'items': items, 'payments': payments}, invoice_date=day)
                hour = HOURS[(b * 5 + days_ago) % len(HOURS)]
                at = dt.datetime.combine(today - dt.timedelta(days=days_ago), dt.time(hour, (b * 7) % 60), self.clock.tz)
                self.repos.invoices.set_finalized_at(invoice_id, min(at, self.clock.now()).isoformat(timespec='seconds'))
        for days_ago, category, amount in EXPENSES:
            services.expenses.create(admin, {'expense_date': (today - dt.timedelta(days=days_ago)).isoformat(), 'category': category,
                                             'amount': amount, 'payment_mode': 'UPI', 'vendor': 'Demo Vendor', 'notes': 'Sample/Test data'})
