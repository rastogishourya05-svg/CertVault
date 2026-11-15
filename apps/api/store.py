"""Isolated local demonstration store. Not a production database adapter."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def data_dir() -> Path:
    path = Path(os.environ.get("CERTVAULT_DATA_DIR", ".local"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def db():
    connection = sqlite3.connect(data_dir() / "demo.sqlite3", timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_states (hash TEXT PRIMARY KEY, owner TEXT NOT NULL, provider TEXT NOT NULL, verifier BLOB NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (owner TEXT PRIMARY KEY, threshold INTEGER NOT NULL DEFAULT 52428800, name TEXT NOT NULL DEFAULT 'Demo learner');
        CREATE TABLE IF NOT EXISTS certificates (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, issuer TEXT NOT NULL,
          issued TEXT, category TEXT NOT NULL, source TEXT NOT NULL, hash TEXT NOT NULL,
          bytes INTEGER NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, trashed INTEGER NOT NULL DEFAULT 0,
          created TEXT NOT NULL, text TEXT NOT NULL, UNIQUE(owner, hash));
        CREATE TABLE IF NOT EXISTS connections (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, provider TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL, UNIQUE(owner,provider));
        CREATE TABLE IF NOT EXISTS imports (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, connection_id TEXT NOT NULL REFERENCES connections(id),
          source_key TEXT NOT NULL, title TEXT NOT NULL, issuer TEXT NOT NULL, category TEXT NOT NULL,
          declared_size INTEGER NOT NULL, status TEXT NOT NULL, certificate_id TEXT,
          UNIQUE(owner,connection_id,source_key));
        CREATE TABLE IF NOT EXISTS notifications (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, event_key TEXT NOT NULL, message TEXT NOT NULL,
          read INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, UNIQUE(owner,event_key));
        CREATE TABLE IF NOT EXISTS audit (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, event TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS shares (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, certificate_id TEXT NOT NULL REFERENCES certificates(id),
          token_hash TEXT NOT NULL UNIQUE, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS public_profiles (
          owner TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, enabled INTEGER NOT NULL DEFAULT 0,
          name TEXT NOT NULL, featured TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS drafts (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, certificate_id TEXT NOT NULL REFERENCES certificates(id),
          tone TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS collections (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, created TEXT NOT NULL,
          UNIQUE(owner,name));
        CREATE TABLE IF NOT EXISTS collection_items (
          collection_id TEXT NOT NULL REFERENCES collections(id), certificate_id TEXT NOT NULL REFERENCES certificates(id),
          PRIMARY KEY(collection_id,certificate_id));
        """)
        columns = {row["name"] for row in c.execute("PRAGMA table_info(certificates)")}
        if "tags" not in columns:
            c.execute("ALTER TABLE certificates ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")


def rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


def profile_view(row):
    result = dict(row)
    result["featured"] = json.loads(result["featured"])
    return result
