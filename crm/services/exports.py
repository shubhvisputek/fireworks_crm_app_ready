"""Use cases that produce downloadable files."""
from crm.domain.permissions import Permission
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
