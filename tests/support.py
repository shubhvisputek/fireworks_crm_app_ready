"""Test helpers: run the real server in a subprocess and talk to it over HTTP."""
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body or b'null')


class Client:
    """A browser-like client with its own cookie jar."""

    def __init__(self, base_url):
        self.base_url = base_url
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, method, path, body=None, headers=None, raw=None):
        headers = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            headers.setdefault('Content-Type', 'application/json')
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=20) as resp:
                return Response(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as err:
            return Response(err.code, err.headers, err.read())

    def get(self, path, **kw):
        return self.request('GET', path, **kw)

    def post(self, path, body=None, **kw):
        return self.request('POST', path, body=body if body is not None else ({} if 'raw' not in kw else None), **kw)

    def login(self, username, password):
        return self.post('/api/login', {'username': username, 'password': password})

    def upload(self, path, fields, filename, content):
        boundary = 'testboundary7f3a'
        parts = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n'.encode() + content + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        return self.request('POST', path, raw=b''.join(parts), headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})


class ServerProcess:
    """Starts `python server.py` against a throwaway data directory."""

    def __init__(self, env=None):
        self.tmp = tempfile.mkdtemp(prefix='fwcrm-test-')
        self.port = free_port()
        self.base_url = f'http://127.0.0.1:{self.port}'
        self.env = {
            **os.environ,
            'PORT': str(self.port),
            'HOST': '127.0.0.1',
            'FIREWORKS_DB': os.path.join(self.tmp, 'fireworks.db'),
            'FIREWORKS_SECRET': os.path.join(self.tmp, '.secret'),
            'FIREWORKS_DATA_DIR': self.tmp,
            **(env or {}),
        }
        self.proc = None

    def start(self):
        self.log = open(os.path.join(self.tmp, 'server.log'), 'w')
        self.proc = subprocess.Popen([sys.executable, 'server.py'], cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError('Server exited early:\n' + open(self.log.name).read())
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=0.2):
                    return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError('Server did not start:\n' + open(self.log.name).read())

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        if getattr(self, 'log', None):
            self.log.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def client(self):
        return Client(self.base_url)


def pdf_text(content):
    """The text drawn in a PDF made by reportlab, whether or not its page streams are compressed."""
    import base64
    import re
    import zlib
    text = b''
    for match in re.finditer(rb'stream\r?\n(.*?)endstream', content, re.S):
        data = match.group(1).strip()
        try:
            if data.endswith(b'~>'):
                data = zlib.decompress(base64.a85decode(data[:-2], adobe=False))
        except (ValueError, zlib.error):
            pass
        text += data
    parts = re.findall(rb'\(((?:[^\\)]|\\.)*)\) Tj', text)
    return ' '.join(' '.join(re.sub(r'\\(.)', r'\1', part.decode('latin-1')) for part in parts).split())
