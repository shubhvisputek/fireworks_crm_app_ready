"""Cash closing, audit log and backups."""
from crm.domain.permissions import OWNER, Permission as P
from crm.errors import PermissionDenied
from crm.web.http import Response


def closing_summary(ctx):
    return ctx.services.cash_closing.summary(ctx.user)


def close_drawer(ctx):
    return {'ok': True, **ctx.services.cash_closing.close(ctx.user, ctx.body())}


def closing_history(ctx):
    return ctx.services.cash_closing.history(ctx.user)


def audit(ctx):
    q = ctx.request.query
    return ctx.services.audit_log.search(q.get('start'), q.get('end'), q.get('user_id'), q.get('entity'), q.get('q'))


def list_backups(ctx):
    return {'backups': ctx.app.backups.list(), 'keep_days': ctx.services.settings.get_settings().get('backup_keep_days', 30)}


def create_backup(ctx):
    name = ctx.app.backups.create('manual')
    ctx.services.audit_log.audit(ctx.user, 'Backup created', 'BACKUP', None, new={'name': name})
    return {'ok': True, 'name': name}


def download_backup(ctx):
    name = ctx.request.arg('name', '')
    return Response.download(name, ctx.app.backups.read(name), 'application/vnd.sqlite3')


def restore_backup(ctx):
    # A backup file can contain any accounts, including an owner, so only the owner may restore one.
    if ctx.user['role'] != OWNER:
        raise PermissionDenied('Only the owner can restore a backup.')
    content_type = ctx.request.headers.get('Content-Type', '')
    if 'multipart/form-data' in content_type:
        _fields, files = ctx.request.multipart()
        upload = files.get('file') or {}
        source, safety = upload.get('filename', 'upload'), ctx.app.backups.restore_upload(upload.get('content'))
    else:
        source = ctx.body().get('name', '')
        safety = ctx.app.backups.restore_named(source)
    ctx.services.audit_log.audit(ctx.user, 'Backup restored', 'BACKUP', None, new={'restored': source, 'safety_backup': safety})
    # The restored database has its own users: bring its schema up to date and sign everyone out
    # (a new signing key makes every existing session cookie invalid).
    ctx.app.after_restore()
    ctx.end_session()
    return {'ok': True, 'restored': source, 'safety_backup': safety, 'relogin': True}


def register(router):
    router.add('GET', '/api/cash-closing/summary', closing_summary, P.CASH_CLOSING_OWN)
    router.add('POST', '/api/cash-closing', close_drawer, P.CASH_CLOSING_OWN)
    router.add('GET', '/api/cash-closings', closing_history, (P.CASH_CLOSING_OWN, P.CASH_CLOSING_VIEW_ALL))
    router.add('GET', '/api/audit', audit, P.AUDIT_VIEW)
    router.add('GET', '/api/backups', list_backups, P.BACKUP_RESTORE)
    router.add('POST', '/api/backups', create_backup, P.BACKUP_RESTORE)
    router.add('GET', '/api/backups/download', download_backup, P.BACKUP_RESTORE)
    router.add('POST', '/api/backups/restore', restore_backup, P.BACKUP_RESTORE, max_body=500 * 1024 * 1024)
