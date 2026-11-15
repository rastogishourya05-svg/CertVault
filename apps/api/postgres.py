"""Small DB-API wrapper; parameterized SQL and verified TLS outside loopback."""

import ssl
from contextlib import contextmanager
from urllib.parse import unquote, urlsplit

import pg8000.dbapi

DatabaseError = pg8000.dbapi.Error


class Rows:
    def __init__(self, cursor):
        self.cursor = cursor

    def _row(self, values):
        return dict(zip((column[0] for column in self.cursor.description), values, strict=True))

    def fetchone(self):
        values = self.cursor.fetchone()
        return self._row(values) if values is not None else None

    def fetchall(self):
        return [self._row(values) for values in self.cursor.fetchall()]


class Database:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        cursor = self.connection.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return Rows(cursor)


@contextmanager
def connect(dsn):
    url = urlsplit(dsn)
    if url.scheme not in ("postgres", "postgresql") or not url.hostname:
        raise ValueError("Invalid PostgreSQL connection URL")
    context = False if url.hostname in ("127.0.0.1", "localhost") else ssl.create_default_context()
    connection = pg8000.dbapi.connect(
        user=unquote(url.username or ""),
        password=unquote(url.password or ""),
        host=url.hostname,
        port=url.port or 5432,
        database=unquote(url.path.lstrip("/")),
        ssl_context=context,
        timeout=10,
    )
    try:
        yield Database(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
