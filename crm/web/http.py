"""Framework-independent request and response objects."""
import json
import urllib.parse
from email.parser import BytesParser
from email.policy import default as default_policy

from crm.errors import ValidationError


class Request:
    def __init__(self, method, target, headers, body_reader, max_body_bytes):
        parsed = urllib.parse.urlparse(target)
        self.method = method
        self.path = parsed.path
        self.query = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}
        self.headers = headers
        self._read = body_reader
        self.max_body = max_body_bytes
        self._raw = None

    def arg(self, name, default=None):
        return self.query.get(name, default)

    def raw_body(self):
        if self._raw is None:
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                raise ValidationError('Invalid Content-Length header.')
            if length < 0 or length > self.max_body:
                raise ValidationError(f'Request is too large (limit {self.max_body // (1024 * 1024)} MB).')
            self._raw = self._read(length) if length else b''
        return self._raw

    def json(self):
        """The body as a dict: JSON or form-encoded. Anything else is rejected."""
        raw = self.raw_body()
        content_type = self.headers.get('Content-Type', '')
        if 'application/x-www-form-urlencoded' in content_type:
            return {key: values[0] for key, values in urllib.parse.parse_qs(raw.decode(errors='replace')).items()}
        if not raw:
            return {}
        if 'application/json' not in content_type:
            raise ValidationError('Send the request body as JSON.')
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValidationError('The request body is not valid JSON.')
        if not isinstance(data, dict):
            raise ValidationError('The request body must be a JSON object.')
        return data

    def multipart(self):
        """(fields, files) from a multipart/form-data body."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            raise ValidationError('Upload the file as multipart/form-data.')
        message = BytesParser(policy=default_policy).parsebytes(
            b'Content-Type: ' + content_type.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + self.raw_body())
        fields, files = {}, {}
        for part in message.iter_parts():
            name = part.get_param('name', header='content-disposition')
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b''
            if filename:
                files[name] = {'filename': filename, 'content': payload}
            else:
                fields[name] = payload.decode('utf-8', errors='replace')
        return fields, files


class Response:
    def __init__(self, status=200, body=b'', content_type='application/json', headers=None):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = dict(headers or {})

    @classmethod
    def json(cls, data, status=200, headers=None):
        return cls(status, json.dumps(data, default=str).encode(), 'application/json', headers)

    @classmethod
    def error(cls, message, status, **details):
        return cls.json({'error': message, **details}, status)

    @classmethod
    def download(cls, filename, content, content_type, inline=False):
        disposition = 'inline' if inline else 'attachment'
        safe_name = filename.replace('"', '')
        return cls(200, content, content_type, {'Content-Disposition': f'{disposition}; filename="{safe_name}"'})
