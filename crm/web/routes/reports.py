import json

from crm.domain.permissions import Permission as P
from crm.web.http import Response

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def dashboard(ctx):
    return ctx.services.reports.dashboard(ctx.user, ctx.request.arg('date'))


def analytics(ctx):
    q = ctx.request.query
    return ctx.services.reports.analytics(ctx.user, q.get('start'), q.get('end'), q.get('preset'))


def backup(ctx):
    filename, data = ctx.services.exports.backup_json(ctx.user)
    return Response.download(filename, json.dumps(data, indent=2, default=str).encode(), 'application/json')


def sales_xlsx(ctx):
    return Response.download(*ctx.services.exports.sales_xlsx(), XLSX)


def sales_detailed_xlsx(ctx):
    return Response.download(*ctx.services.exports.sales_detailed_xlsx(ctx.user), XLSX)


def sales_pdf(ctx):
    return Response.download(*ctx.services.exports.sales_pdf(), 'application/pdf')


def register(router):
    router.add('GET', '/api/dashboard', dashboard, P.DASHBOARD_VIEW)
    router.add('GET', '/api/analytics', analytics, P.ANALYTICS_VIEW)
    router.add('GET', '/api/backup', backup, P.BACKUP_DOWNLOAD)
    router.add('GET', '/api/export/sales.xlsx', sales_xlsx, P.REPORTS_EXPORT)
    router.add('GET', '/api/export/sales-detailed.xlsx', sales_detailed_xlsx, P.REPORTS_EXPORT)
    router.add('GET', '/api/export/sales.pdf', sales_pdf, P.REPORTS_EXPORT)
