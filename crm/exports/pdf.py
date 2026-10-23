"""PDF invoice (customer + seller copy side by side) and sales report, generated in memory."""
import datetime as dt
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
LINE_H = 5 * mm
FOOTER_SPACE = 33 * mm  # room for up to 6 total lines (with Returned and Credit), payments and the footer
HEADER_SPACE = 71 * mm
COLUMN_W = PAGE_W / 2 - 24 * mm
# (x, label, show staff names). Who billed, edited or cancelled a bill is for the shop only, not the customer.
COLUMNS = ((MARGIN, 'CUSTOMER COPY', False), (PAGE_W / 2 + 6 * mm, 'SELLER COPY', True))


def short_time(value):
    try:
        return dt.datetime.fromisoformat(str(value)).strftime('%d-%m-%Y %I:%M %p')
    except (TypeError, ValueError):
        return str(value or '')


def fit_text(text, font, size, max_width):
    text = str(text or '')
    if stringWidth(text, font, size) <= max_width:
        return text
    while text and stringWidth(text + '...', font, size) > max_width:
        text = text[:-1]
    return text + '...' if text else ''


def money_paid(payments):
    """Payments the customer actually made. A 'Credit' entry is the part left to pay later (shown as credit due),
    so listing it as paid would add up to more than the bill once the credit is collected."""
    return [p for p in payments if str(p['mode']).upper() != 'CREDIT']


class InvoicePdf:
    """Two identical copies per page; long bills continue on further pages."""

    def __init__(self, invoice, items, payments, settings):
        self.inv, self.items, self.payments, self.settings = invoice, items, payments, settings
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=A4)
        self.c.setPageCompression(0)

    def _line(self, x, y, text, font='Helvetica', size=7, width=COLUMN_W):
        self.c.setFont(font, size)
        self.c.drawString(x, y, fit_text(text, font, size, width))

    def _header(self, x, copy_label, continued, staff=True):
        c, inv, st = self.c, self.inv, self.settings
        top = PAGE_H - MARGIN
        self._line(x, top, st.get('business_name', ''), 'Helvetica-Bold', 11, COLUMN_W - 3 * mm)
        c.setFont('Helvetica-Bold', 10)
        c.drawRightString(x + COLUMN_W, top + 2 * mm, 'INVOICE')
        c.setFont('Helvetica-Bold', 8)
        c.drawRightString(x + COLUMN_W, top - 5 * mm, copy_label)
        y = top - 6 * mm
        self._line(x, y, st.get('address', ''))
        y -= 4 * mm
        self._line(x, y, f"License: {st.get('license_number') or 'N/A'}")
        y -= 8 * mm
        lines = [f"Invoice: {inv['invoice_number']}", f"Date: {inv['invoice_date']}",
                 f"Customer: {inv['customer_name_snapshot']} ({inv['customer_type_snapshot']})",
                 # The customer copy leaves this line blank so both copies keep their items side by side.
                 f"Billed by: {inv.get('billed_by_name') or '-'}" if staff else '']
        for text in lines:
            self._line(x, y, text)
            y -= 4 * mm
        if inv.get('revised_from_number'):
            editor = f" - edited by {inv.get('edited_by_name') or '-'} on {short_time(inv.get('edited_at'))}" if staff else ''
            self._line(x, y, f"Revised from {inv['revised_from_number']}{editor}", 'Helvetica-Oblique')
            y -= 4 * mm
        if inv['status'] == 'VOID':
            replaced = f" - replaced by {inv['revised_to_number']}" if inv.get('revised_to_number') else ''
            who = f" ({inv.get('voided_by_name') or '-'}, {short_time(inv.get('voided_at'))})" if staff else ''
            self._line(x, y, f"CANCELLED{replaced}{who}", 'Helvetica-Bold')
            y -= 4 * mm
        y -= 1 * mm
        if continued:
            self._line(x, y, 'Continued', 'Helvetica-Oblique')
            y -= 4 * mm
        c.setFont('Helvetica-Bold', 7)
        c.drawString(x, y, 'Product / Item')
        c.drawRightString(x + 38 * mm, y, 'Qty')
        c.drawRightString(x + 59 * mm, y, 'Unit Price')
        c.drawRightString(x + COLUMN_W, y, 'Line Total')
        y -= 4 * mm
        c.line(x, y, x + COLUMN_W, y)
        return y - 4 * mm

    def _item(self, x, y, item):
        c = self.c
        c.setFont('Helvetica', 7)
        c.drawString(x, y, fit_text(f"{item['sku_snapshot']} {item['product_name_snapshot']}", 'Helvetica', 7, 35 * mm))
        c.drawRightString(x + 38 * mm, y, f"{item['qty_input']:g}")
        c.drawRightString(x + 59 * mm, y, f"{item['unit_price']:.2f}")
        c.drawRightString(x + COLUMN_W, y, f"{item['unit_price'] * item['qty_input']:,.2f}")

    def _totals(self, x):
        c, inv = self.c, self.inv
        y = MARGIN + FOOTER_SPACE - 8 * mm
        c.setFont('Helvetica-Bold', 7)
        c.line(x, y + 10 * mm, x + COLUMN_W, y + 10 * mm)
        y -= 2 * mm
        totals = [('Subtotal', inv['subtotal']), ('Discount', inv['discount']), ('Total', inv['grand_total'])]
        if inv.get('returned_amount'):
            totals.append(('Returned', inv['returned_amount']))
        totals.append(('Received', inv['amount_received']))
        if inv['outstanding'] > 0:
            totals.append(('Credit', inv['outstanding']))
        for label, value in totals:
            c.drawString(x + 34 * mm, y, label)
            c.drawRightString(x + COLUMN_W, y, f'Rs. {value:,.2f}')
            y -= 5 * mm
        paid = ', '.join(f"{p['mode']} Rs. {p['amount']:,.2f}" for p in money_paid(self.payments)) or 'No payment yet'
        self._line(x, y - 2 * mm, 'Payment(s): ' + paid)
        self._line(x, y - 8 * mm, self.settings.get('invoice_footer', 'Thank you.'))

    def render(self):
        per_page = max(1, int((PAGE_H - MARGIN - HEADER_SPACE - MARGIN - FOOTER_SPACE) // LINE_H))
        pages = [self.items[i:i + per_page] for i in range(0, len(self.items), per_page)] or [[]]
        for number, page_items in enumerate(pages):
            for x, label, staff in COLUMNS:
                y = self._header(x, label, continued=number > 0, staff=staff)
                for item in page_items:
                    self._item(x, y, item)
                    y -= LINE_H
                if number == len(pages) - 1:
                    self._totals(x)
            if number < len(pages) - 1:
                self.c.showPage()
        self.c.save()
        return self.buffer.getvalue()


def invoice_pdf(invoice, items, payments, settings):
    return InvoicePdf(invoice, items, payments, settings).render()


def sales_report_pdf(invoices, business_name):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = PAGE_H - MARGIN
    c.setFont('Helvetica-Bold', 14)
    c.drawString(MARGIN, y, f'{business_name} — Sales Report')
    y -= 8 * mm
    c.setFont('Helvetica', 8)
    for x, label in ((18, 'Invoice'), (55, 'Date'), (82, 'Customer'), (145, 'Type'), (170, 'Total')):
        c.drawString(x * mm, y, label)
    y -= 4 * mm
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 5 * mm
    for inv in invoices:
        c.drawString(18 * mm, y, str(inv['invoice_number'])[-18:])
        c.drawString(55 * mm, y, str(inv['invoice_date']))
        c.drawString(82 * mm, y, str(inv['customer_name_snapshot'])[:25])
        c.drawString(145 * mm, y, str(inv['customer_type_snapshot'])[:10])
        c.drawRightString(188 * mm, y, f"{inv['grand_total']:,.2f}")
        y -= 4.5 * mm
        if y < MARGIN:
            c.showPage()
            c.setFont('Helvetica', 8)
            y = PAGE_H - MARGIN
    c.save()
    return buffer.getvalue()


RECEIPT_W = 80 * mm
RECEIPT_MARGIN = 4 * mm
RECEIPT_TEXT_W = RECEIPT_W - 2 * RECEIPT_MARGIN


def receipt_pdf(invoice, items, payments, settings):
    """80 mm thermal-printer receipt; the page is exactly as long as the content."""
    payments = money_paid(payments)
    line = 3.8 * mm
    totals = [('Subtotal', invoice['subtotal']), ('Discount', invoice['discount']), ('TOTAL', invoice['grand_total'])]
    if invoice.get('returned_amount'):
        totals.append(('Returned', invoice['returned_amount']))
    totals += [('Received', invoice['amount_received'])] + ([('Credit due', invoice['outstanding'])] if invoice['outstanding'] > 0 else [])
    header_lines = 6 + (1 if settings.get('phone') else 0) + (1 if invoice.get('revised_from_number') else 0) + (1 if invoice['status'] == 'VOID' else 0)
    height = (header_lines + 2 * len(items) + len(totals) + len(payments) + 6) * line + 2 * RECEIPT_MARGIN
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(RECEIPT_W, height))
    x, right = RECEIPT_MARGIN, RECEIPT_W - RECEIPT_MARGIN
    y = height - RECEIPT_MARGIN - line

    def text(value, font='Helvetica', size=8, align='left'):
        nonlocal y
        c.setFont(font, size)
        value = fit_text(value, font, size, RECEIPT_TEXT_W)
        if align == 'center':
            c.drawCentredString(RECEIPT_W / 2, y, value)
        else:
            c.drawString(x, y, value)
        y -= line

    def pair(label, value, font='Helvetica'):
        nonlocal y
        c.setFont(font, 8)
        c.drawString(x, y, fit_text(label, font, 8, RECEIPT_TEXT_W * 0.6))
        c.drawRightString(right, y, value)
        y -= line

    def rule():
        nonlocal y
        c.setDash(1, 2)
        c.line(x, y + line * 0.4, right, y + line * 0.4)
        c.setDash()
        y -= line * 0.6

    text(settings.get('business_name', ''), 'Helvetica-Bold', 10, 'center')
    text(settings.get('address', ''), size=7, align='center')
    if settings.get('phone'):
        text(f"Ph: {settings['phone']}", size=7, align='center')
    rule()
    text(f"Bill: {invoice['invoice_number']}")
    text(f"Date: {invoice['invoice_date']}", size=7)  # no staff name: the receipt goes to the customer
    text(f"Customer: {invoice['customer_name_snapshot']}", size=7)
    if invoice.get('revised_from_number'):
        text(f"Revised from {invoice['revised_from_number']}", 'Helvetica-Oblique', 7)
    if invoice['status'] == 'VOID':
        text('CANCELLED', 'Helvetica-Bold', 9, 'center')
    rule()
    for item in items:
        text(f"{item['product_name_snapshot']}", size=8)
        pair(f"  {item['qty_input']:g} x {item['unit_price']:.2f}", f"{item['unit_price'] * item['qty_input']:,.2f}")
    rule()
    for label, value in totals:
        pair(label, f'Rs. {value:,.2f}', 'Helvetica-Bold' if label == 'TOTAL' else 'Helvetica')
    for payment in payments:
        pair(f"  Paid {payment['mode']}", f"{payment['amount']:,.2f}")
    rule()
    text(settings.get('invoice_footer', 'Thank you.'), size=7, align='center')
    c.save()
    return buffer.getvalue()
