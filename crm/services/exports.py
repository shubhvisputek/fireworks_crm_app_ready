"""Use cases that produce downloadable files."""
import re

from crm.domain import validation as v
from crm.domain.permissions import Permission
from crm.errors import ValidationError
from crm.exports import excel, pdf
from crm.services.base import Service


class ExportService(Service):
    def stamp(self):
        return self.clock.now().strftime('%Y%m%d-%H%M%S')

    def invoice_pdf(self, actor, invoice_id, receipt=False):
        invoice = self.services.sales.visible_invoice(actor, invoice_id)
        render = pdf.receipt_pdf if receipt else pdf.invoice_pdf
        content = render(invoice, self.repos.invoices.items(invoice_id), self.repos.invoices.payments(invoice_id),
                         self.services.settings.get_settings())
        return f"{invoice['invoice_number']}{'-receipt' if receipt else ''}.pdf", content

    MAX_LIST_ROWS, MAX_LIST_COLUMNS, MAX_CELL = 20_000, 40, 2_000

    def list_xlsx(self, actor, data):
        """An on-screen list, exactly as this user sees it, as an Excel file. The rows come from the page, which only ever
        holds what the user may see; the permission to export is checked here, and every export is audit-logged."""
        title = v.text((data or {}).get('title'), 60) or 'List'
        headers, rows = (data or {}).get('headers'), (data or {}).get('rows')
        if not isinstance(headers, list) or not headers or not isinstance(rows, list):
            raise ValidationError('Nothing to export.')
        if len(headers) > self.MAX_LIST_COLUMNS or len(rows) > self.MAX_LIST_ROWS:
            raise ValidationError(f'Lists can be exported up to {self.MAX_LIST_ROWS:,} rows and {self.MAX_LIST_COLUMNS} columns.')

        def cell(value):
            if isinstance(value, bool) or value is None:
                return ''
            if isinstance(value, (int, float)):
                return value
            return str(value)[:self.MAX_CELL]
        headers = [cell(h) for h in headers]
        rows = [[cell(value) for value in row[:len(headers)]] for row in rows if isinstance(row, list)]
        self.audit(actor, 'List exported', 'EXPORT', None, new={'list': title, 'rows': len(rows)})
        safe = re.sub(r'[^A-Za-z0-9]+', '-', title).strip('-').lower() or 'list'
        return f'{safe}-{self.stamp()}.xlsx', excel.list_table(title, headers, rows)

    def sales_xlsx(self):
        return f'sales-{self.stamp()}.xlsx', excel.sales_summary(self.repos.invoices.list_finalized())

    def sales_detailed_xlsx(self, actor):
        content = excel.sales_detailed(self.repos.invoices.list_finalized(), self.repos.invoices.items_for_export(),
                                       self.repos.invoices.payments_for_export(), include_profit=self.can(actor, Permission.PROFIT_VIEW))
        return f'sales-detailed-{self.stamp()}.xlsx', content

    def sales_pdf(self):
        business = self.services.settings.get_settings().get('business_name', '')
        return f'sales-{self.stamp()}.pdf', pdf.sales_report_pdf(self.repos.invoices.list_finalized(), business)

    def backup_json(self, actor):
        return f'fireworks-backup-{self.stamp()}.json', self.services.reports.backup(actor)
