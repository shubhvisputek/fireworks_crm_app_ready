"""Adapter from Python's built-in threaded HTTP server to the Application."""
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from crm.backups import DailyBackupThread
from crm.config import Config
from crm.web.app import SECURITY_HEADERS, Application
from crm.web.http import Request

log = logging.getLogger('crm')


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """At most MAX_CONNECTIONS requests are handled at once; further connections wait their turn
    instead of starting unlimited threads."""

    MAX_CONNECTIONS = 64
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slots = threading.BoundedSemaphore(self.MAX_CONNECTIONS)

    def process_request(self, request, client_address):
        self._slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'FireworksCRM'
        sys_version = ''
        timeout = 30  # seconds a client may stay silent; stops slow connections holding a thread forever

        def log_message(self, fmt, *args):
            log.debug('%s - %s', self.address_string(), fmt % args)

        def _dispatch(self, head=False):
            request = Request(self.command if not head else 'GET', self.path, self.headers, self.rfile.read, app.config.max_body_bytes,
                              self.client_address[0] if self.client_address else '')
            response = app.handle(request)
            self.send_response(response.status)
            self.send_header('Content-Type', response.content_type)
            self.send_header('Content-Length', str(len(response.body)))
            self.send_header('Cache-Control', response.headers.pop('Cache-Control', 'no-store'))
            for key, value in {**SECURITY_HEADERS, **response.headers}.items():
                for item in value if isinstance(value, list) else [value]:  # a list sends the header once per value
                    self.send_header(key, item)
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
    # Database, backups and the session key are readable by this user only (not other accounts on the computer).
    os.umask(0o077)
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
    BoundedThreadingHTTPServer((config.host, config.port), make_handler(app)).serve_forever()
