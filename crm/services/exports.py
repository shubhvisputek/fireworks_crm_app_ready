"""Use cases that produce downloadable files."""
from crm.errors import NotFoundError
from crm.exports import excel, pdf
from crm.services.base import Service


class ExportService(Service):
    def stamp(self):
        return self.clock.now().strftime('%Y%m%d-%H%M%S')

    def invoice_pdf(self, invoice_id):
        invoice = self.repos.invoices.get(invoice_id)
        if not invoice:
            raise NotFoundError('Invoice not found')
        content = pdf.invoice_pdf(invoice, self.repos.invoices.items(invoice_id), self.repos.invoices.payments(invoice_id),
                                  self.services.settings.get_settings())
        return f"{invoice['invoice_number']}.pdf", content

    def sales_xlsx(self):
        return f'sales-{self.stamp()}.xlsx', excel.sales_summary(self.repos.invoices.list_finalized())

    def sales_detailed_xlsx(self):
        content = excel.sales_detailed(self.repos.invoices.list_finalized(), self.repos.invoices.items_for_export(),
                                       self.repos.invoices.payments_for_export())
        return f'sales-detailed-{self.stamp()}.xlsx', content

    def sales_pdf(self):
        business = self.services.settings.get_settings().get('business_name', '')
        return f'sales-{self.stamp()}.pdf', pdf.sales_report_pdf(self.repos.invoices.list_finalized(), business)

    def backup_json(self):
        return f'fireworks-backup-{self.stamp()}.json', self.services.reports.backup()
