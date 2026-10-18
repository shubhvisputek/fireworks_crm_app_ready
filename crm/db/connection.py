"""SQLite connections with explicit transaction control."""
import sqlite3
from contextlib import contextmanager


class Database:
    def __init__(self, path):
        self.path = path

    def connect(self):
        # isolation_level=None: no implicit BEGIN; writes happen inside transaction() only.
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn

    @contextmanager
    def session(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()


@contextmanager
def transaction(conn):
    """Run a block atomically. Nested calls join the outer transaction."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    else:
        conn.execute('COMMIT')
