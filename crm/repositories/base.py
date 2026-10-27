"""Shared helpers for repositories. Repositories hold SQL only, no business rules."""


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


class Repository:
    def __init__(self, conn):
        self.conn = conn

    def one(self, sql, params=()):
        return row_to_dict(self.conn.execute(sql, params).fetchone())

    def all(self, sql, params=()):
        return rows_to_dicts(self.conn.execute(sql, params).fetchall())

    def scalar(self, sql, params=(), default=None):
        row = self.conn.execute(sql, params).fetchone()
        return default if row is None or row[0] is None else row[0]

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def insert(self, table, values):
        columns = ', '.join(values)
        placeholders = ', '.join('?' for _ in values)
        cursor = self.conn.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(values.values()))
        return cursor.lastrowid

    def update_row(self, table, row_id, values):
        assignments = ', '.join(f'{column}=?' for column in values)
        return self.conn.execute(f'UPDATE {table} SET {assignments} WHERE id=?', (*values.values(), row_id)).rowcount
