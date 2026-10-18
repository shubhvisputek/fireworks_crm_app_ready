"""Database file backups: daily snapshots, on-demand backups and restore.

Snapshots use SQLite's online backup API, so they are consistent even while the app is in use.
"""
import logging
import os
import re
import sqlite3
import tempfile
import threading

from crm.errors import NotFoundError, ValidationError

log = logging.getLogger('crm')
NAME_RE = re.compile(r'^fireworks-(\d{8})-(\d{6})(?:-([a-z]+))?\.sqlite$')
REQUIRED_TABLES = {'users', 'products', 'invoices', 'invoice_items', 'business_settings'}
MIN_KEEP = 3


class BackupManager:
    def __init__(self, db_path, backup_dir, clock):
        self.db_path = db_path
        self.dir = backup_dir
        self.clock = clock
        self._lock = threading.Lock()

    def _path(self, name):
        if not NAME_RE.match(name or ''):
            raise NotFoundError('Backup not found.')
        path = os.path.join(self.dir, name)
        if not os.path.isfile(path):
            raise NotFoundError('Backup not found.')
        return path

    def list(self):
        if not os.path.isdir(self.dir):
            return []
        rows = []
        for name in sorted(os.listdir(self.dir), reverse=True):
            match = NAME_RE.match(name)
            if match:
                day, time = match.group(1), match.group(2)
                rows.append({'name': name, 'size': os.path.getsize(os.path.join(self.dir, name)), 'kind': match.group(3) or 'manual',
                             'created': f'{day[:4]}-{day[4:6]}-{day[6:]} {time[:2]}:{time[2:4]}'})
        return rows

    def create(self, kind='manual'):
        os.makedirs(self.dir, exist_ok=True)
        stamp = self.clock.now().strftime('%Y%m%d-%H%M%S')
        name = f'fireworks-{stamp}-{kind}.sqlite'
        with self._lock:
            source = sqlite3.connect(self.db_path)
            target = sqlite3.connect(os.path.join(self.dir, name))
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        return name

    def ensure_daily(self, keep_days):
        """Take today's automatic backup if there is none yet, then prune old automatic ones."""
        today = self.clock.now().strftime('%Y%m%d')
        if not any(row['name'].startswith(f'fireworks-{today}-') and row['name'].endswith('-daily.sqlite') for row in self.list()):
            self.create('daily')
        self.prune(keep_days)

    def prune(self, keep_days):
        daily = [row['name'] for row in self.list() if row['name'].endswith('-daily.sqlite')]
        for name in daily[max(int(keep_days or 0), MIN_KEEP):]:
            os.remove(os.path.join(self.dir, name))

    def read(self, name):
        with open(self._path(name), 'rb') as handle:
            return handle.read()

    @staticmethod
    def validate(path):
        try:
            conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            try:
                if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValidationError('The backup file is damaged.')
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            raise ValidationError('That file is not a Fireworks CRM backup.')
        if not REQUIRED_TABLES <= tables:
            raise ValidationError('That file is not a Fireworks CRM backup.')

    def restore(self, source_path):
        """Replace the live database with a backup. A safety copy of the current data is taken first."""
        self.validate(source_path)
        safety = self.create('prerestore')
        with self._lock:
            source = sqlite3.connect(source_path)
            target = sqlite3.connect(self.db_path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        return safety

    def restore_named(self, name):
        return self.restore(self._path(name))

    def restore_upload(self, content):
        if not content:
            raise ValidationError('Choose a backup file to restore.')
        fd, path = tempfile.mkstemp(suffix='.sqlite')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
            return self.restore(path)
        finally:
            os.remove(path)


class DailyBackupThread(threading.Thread):
    """Checks once an hour and takes the day's backup when missing."""

    def __init__(self, manager, keep_days_getter, interval_seconds=3600):
        super().__init__(daemon=True, name='daily-backup')
        self.manager = manager
        self.keep_days = keep_days_getter
        self.interval = interval_seconds
        self.stopped = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            try:
                self.manager.ensure_daily(self.keep_days())
            except Exception:
                log.exception('Daily backup failed')
            self.stopped.wait(self.interval)
