"""Adapter from Python's built-in threaded HTTP server to the Application."""
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from crm.backups import DailyBackupThread
from crm.config import Config
from crm.web.app import SECURITY_HEADERS, Application
from crm.web.http import Request

log = logging.getLogger('crm')


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'FireworksCRM/2.0'
        sys_version = ''

        def log_message(self, fmt, *args):
            log.debug('%s - %s', self.address_string(), fmt % args)

        def _dispatch(self, head=False):
            request = Request(self.command if not head else 'GET', self.path, self.headers, self.rfile.read, app.config.max_body_bytes)
            response = app.handle(request)
            self.send_response(response.status)
            self.send_header('Content-Type', response.content_type)
            self.send_header('Content-Length', str(len(response.body)))
            self.send_header('Cache-Control', response.headers.pop('Cache-Control', 'no-store'))
            for key, value in {**SECURITY_HEADERS, **response.headers}.items():
                self.send_header(key, value)
            self.end_headers()
            if not head:
                self.wfile.write(response.body)

        def _safely(self, head=False):
            try:
                self._dispatch(head)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser went away (closed tab, cancelled download); nothing to send

        def do_GET(self):
            self._safely()

        def do_HEAD(self):
            self._safely(head=True)

        def do_POST(self):
            self._safely()

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stderr)
    config = Config.from_env()
    app = Application(config)
    try:
        app.initialize()
    except RuntimeError as error:
        raise SystemExit(str(error))
    if config.auto_backup:
        DailyBackupThread(app.backups, app.backup_keep_days).start()
    shown = 'localhost' if not config.is_network_exposed else config.host
    print(f'Fireworks CRM running at http://{shown}:{config.port}', flush=True)
    print('Login username: admin; password is configured through FIREWORKS_ADMIN_PASSWORD.' if config.admin_password
          else 'Local demo login: admin / admin123 (change it in Settings)', flush=True)
    ThreadingHTTPServer((config.host, config.port), make_handler(app)).serve_forever()
