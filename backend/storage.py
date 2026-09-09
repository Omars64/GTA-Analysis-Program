"""Durable JSON records: SQLite locally, PostgreSQL on Vercel.

No database connection or filesystem mutation happens at import/build time.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

BASE_DIR = Path(__file__).resolve().parent


def cloud_mode():
    return os.getenv("VERCEL") == "1" or os.getenv("GTA_CLOUD") == "1"


def runtime_dir():
    fallback = "/tmp/gta-weekly" if cloud_mode() else str(BASE_DIR / "runtime")
    return Path(os.getenv("GTA_DATA_DIR", fallback))


class Store:
    def __init__(self, url=None, path=None):
        self.url = url if url is not None else os.getenv("DATABASE_URL", "")
        self.path = Path(path) if path else runtime_dir() / "state.sqlite3"
        self.ready = False
        self.lock = threading.RLock()

    @contextmanager
    def connection(self):
        if cloud_mode() and not self.url:
            raise RuntimeError("DATABASE_URL is required for durable cloud storage.")
        if self.url:
            import psycopg
            conn = psycopg.connect(self.url, connect_timeout=10)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=15)
        try:
            with self.lock:
                if not self.ready:
                    conn.execute("CREATE TABLE IF NOT EXISTS gta_records (namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, updated DOUBLE PRECISION NOT NULL, PRIMARY KEY (namespace, key))")
                    conn.commit()
                    self.ready = True
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def sql(self, query):
        return query.replace("?", "%s") if self.url else query

    def get(self, namespace, key, default=None):
        with self.connection() as conn:
            row = conn.execute(self.sql("SELECT value FROM gta_records WHERE namespace=? AND key=?"), (namespace, key)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, namespace, key, value):
        with self.connection() as conn:
            conn.execute(self.sql("INSERT INTO gta_records VALUES (?, ?, ?, ?) ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value, updated=excluded.updated"), (namespace, key, json.dumps(value, ensure_ascii=False), time.time()))
        return value

    def mutate(self, namespace, key, change, default=None):
        """Serialize read-modify-write across processes, not just threads."""
        with self.connection() as conn:
            if not self.url:
                conn.execute("BEGIN IMMEDIATE")
            conn.execute(self.sql("INSERT INTO gta_records VALUES (?, ?, ?, ?) ON CONFLICT(namespace,key) DO NOTHING"), (namespace, key, json.dumps(default), time.time()))
            query = "SELECT value FROM gta_records WHERE namespace=? AND key=?"
            if self.url:
                query += " FOR UPDATE"
            row = conn.execute(self.sql(query), (namespace, key)).fetchone()
            value = change(json.loads(row[0]))
            conn.execute(self.sql("UPDATE gta_records SET value=?, updated=? WHERE namespace=? AND key=?"), (json.dumps(value, ensure_ascii=False), time.time(), namespace, key))
        return value

    def list(self, namespace, limit=100):
        with self.connection() as conn:
            rows = conn.execute(self.sql("SELECT key,value FROM gta_records WHERE namespace=? ORDER BY updated DESC LIMIT ?"), (namespace, limit)).fetchall()
        return [(key, json.loads(value)) for key, value in rows if value != "null"]


store = Store()
