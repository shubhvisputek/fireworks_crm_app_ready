"""The application: turns a Request into a Response. Independent of the socket server."""
import logging
import mimetypes
import os
import re
import urllib.parse
from dataclasses import dataclass, field

from crm.backups import BackupManager
from crm.clock import Clock
from crm.config import Config
from crm.db import Database, migrate
from crm.domain.permissions import has_permission
from crm.errors import AppError
from crm.security import LoginThrottle, SecretStore, TokenSigner
from crm.services import Services
from crm.web.http import Request, Response
from crm.web.router import AUTHENTICATED, PUBLIC, Router

log = logging.getLogger('crm')

COOKIE = 'fw_session'
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'Content-Security-Policy': ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                                "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"),
}
STATIC_TYPES = {'.js': 'application/javascript', '.css': 'text/css', '.webmanifest': 'application/manifest+json',
                '.html': 'text/html; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json'}


@dataclass
class RequestContext:
    """What a controller receives: the request, services, the signed-in user and path params."""
    request: Request
    services: Services
    app: 'Application'
    user: dict | None = None
    params: dict = field(default_factory=dict)
    response_headers: dict = field(default_factory=dict)

    def body(self):
        return self.request.json()

    def start_session(self, user):
        token = self.app.signer.sign(self.services.auth.session_payload(user))
        self.response_headers['Set-Cookie'] = self.app.session_cookie(urllib.parse.quote(token))

    def end_session(self):
        self.response_headers['Set-Cookie'] = self.app.session_cookie('', max_age=0)


class Application:
    def __init__(self, config: Config):
        self.config = config
        self.clock = Clock(config.timezone)
        self.db = Database(config.db_path)
        self.signer = TokenSigner(SecretStore(config.secret_path))
        self.throttle = LoginThrottle(config.login_max_failures, config.login_window_seconds)
        self.backups = BackupManager(config.db_path, config.backup_dir, self.clock)
        self.router = Router()
        from crm.web.routes import register_all
        register_all(self.router)

    # --- lifecycle --------------------------------------------------------
    def services(self, conn):
        return Services(conn, self.clock, self.config, self.throttle, self.backups)

    def initialize(self):
        """Create directories and schema, the first admin, and optional demo data."""
        self.config.ensure_directories()
        with self.db.session() as conn:
            migrate(conn, self.clock.now_iso(), self.clock.today())
            services = self.services(conn)
            services.auth.ensure_admin()
            if self.config.is_network_exposed and services.auth.default_password_in_use():
                raise RuntimeError('An account still uses the demo password "admin123". Start the app normally (localhost), '
                                   'change the password in Settings, then start it on the network again.')
            if self.config.seed_demo:
                services.demo.seed()

    def backup_keep_days(self):
        with self.db.session() as conn:
            return self.services(conn).settings.get_settings().get('backup_keep_days', 30)

    # --- sessions ---------------------------------------------------------
    def session_cookie(self, value, max_age=None):
        parts = [f'{COOKIE}={value}', 'HttpOnly', 'SameSite=Lax', 'Path=/']
        if max_age is not None:
            parts.append(f'Max-Age={max_age}')
        if self.config.secure_cookies:
            parts.append('Secure')
        return '; '.join(parts)

    def session_payload(self, request):
        match = re.search(r'(?:^|;\s*)' + COOKIE + r'=([^;]+)', request.headers.get('Cookie', ''))
        return self.signer.verify(urllib.parse.unquote(match.group(1))) if match else None

    # --- dispatch ---------------------------------------------------------
    def handle(self, request: Request) -> Response:
        try:
            if not request.path.startswith('/api/'):
                return self.serve_static(request)
            return self.handle_api(request)
        except AppError as error:
            return Response.json(error.to_dict(), error.status)
        except Exception:
            log.exception('Unhandled error for %s %s', request.method, request.path)
            return Response.error('Something went wrong. Please try again.', 500)

    def handle_api(self, request):
        if request.method == 'POST' and not self.same_origin(request):
            return Response.error('Cross-site request rejected.', 403)
        route, params = self.router.match(request.method, request.path)
        if route is None:
            return Response.error('Use ' + '/'.join(sorted(params)), 405) if params else Response.error('Not found', 404)
        if route.max_body:
            request.max_body = route.max_body
        with self.db.session() as conn:
            ctx = RequestContext(request, self.services(conn), self, params=params)
            if route.permission != PUBLIC:
                ctx.user = ctx.services.auth.user_for_session(self.session_payload(request))
                if not ctx.user:
                    return Response.error('Authentication required', 401)
                needed = route.permission if isinstance(route.permission, tuple) else (route.permission,)
                if route.permission != AUTHENTICATED and not any(has_permission(ctx.user, p) for p in needed):
                    return Response.error('This account does not have access to that feature.', 403)
            result = route.handler(ctx)
        response = result if isinstance(result, Response) else Response.json(result)
        response.headers.update(ctx.response_headers)
        return response

    @staticmethod
    def same_origin(request):
        """Browsers send Origin on POST; reject requests coming from another site."""
        origin = request.headers.get('Origin')
        return not origin or urllib.parse.urlparse(origin).netloc == request.headers.get('Host', '')

    def serve_static(self, request):
        if request.method not in ('GET', 'HEAD'):
            return Response.error('Not found', 404)
        if request.path == '/favicon.ico':
            return Response(204, b'', 'text/plain')
        relative = 'index.html' if request.path == '/' else request.path[len('/static/'):] if request.path.startswith('/static/') else None
        if relative is None:
            return Response(404, b'Not found', 'text/plain')
        root = os.path.realpath(self.config.static_dir)
        path = os.path.realpath(os.path.join(root, urllib.parse.unquote(relative)))
        if not path.startswith(root + os.sep) or not os.path.isfile(path):
            return Response(404, b'Not found', 'text/plain')
        extension = os.path.splitext(path)[1]
        content_type = STATIC_TYPES.get(extension) or mimetypes.guess_type(path)[0] or 'application/octet-stream'
        with open(path, 'rb') as handle:
            return Response(200, handle.read(), content_type, {'Cache-Control': 'no-cache'})
