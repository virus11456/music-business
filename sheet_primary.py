"""Google Sheets authoritative storage; SQLite is a volatile query engine only.

One application process owns writes. No fallback to a disk database on any error.
"""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from sheet_records import capture, decode, TABLES, allowed_meta
from sheet_repository import SheetRepository


def memory_schema():
    import db, workflow, platforms, matching, source_queue, purchase_store
    c = sqlite3.connect(':memory:', check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA + workflow.SCHEMA + platforms.SCHEMA + matching.SCHEMA + source_queue.SCHEMA + purchase_store.SCHEMA)
    extra = {
        'sourcing_offers': [('owned_confirmed','INTEGER NOT NULL DEFAULT 0'),('sale_price','TEXT'),('sale_currency','TEXT'),('supply_confirmed','INTEGER NOT NULL DEFAULT 0'),('dispatch_days','INTEGER')],
        'listing_drafts': [('supply_confirmed','INTEGER NOT NULL DEFAULT 0'),('dispatch_days','INTEGER'),('source_url',"TEXT NOT NULL DEFAULT ''"),('source_offer_id','INTEGER')],
    }
    for table, fields in extra.items():
        for name, kind in fields:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
    c.execute('CREATE UNIQUE INDEX one_draft_per_offer ON listing_drafts(source_offer_id) WHERE source_offer_id IS NOT NULL')
    c.execute('CREATE TABLE source_refresh_attempts(candidate_id INTEGER PRIMARY KEY,attempted_at TEXT NOT NULL,status TEXT NOT NULL)')
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA temp_store=MEMORY')
    return c


class PrimaryStore:
    def __init__(self, repository, ttl=30):
        self.repository = repository
        self.ttl = ttl
        self.lock = threading.RLock()
        self.connection = None
        self.loaded_at = 0
        self.depth = 0

    def reload(self):
        data = self.repository.read(list(TABLES))
        fresh = memory_schema()
        try:
            fresh.execute('PRAGMA foreign_keys=OFF')
            fresh.execute('BEGIN')
            for name in TABLES:
                columns = [r[1] for r in fresh.execute(f'PRAGMA table_info("{name}")')]
                rows = decode(name, data[name], columns)
                fresh.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in columns)})', rows)
            if fresh.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Sheet contains broken record relationships')
            # Local-only rate counters/cache may survive a refresh, never a process restart.
            if self.connection is not None:
                for table in ('api_budget', 'api_health'):
                    for row in self.connection.execute(f'SELECT * FROM {table}'):
                        fresh.execute(f'INSERT INTO {table} VALUES({",".join("?" for _ in row)})', tuple(row))
                for row in self.connection.execute('SELECT key,value FROM meta'):
                    if not allowed_meta(row[0]):
                        fresh.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', tuple(row))
            fresh.commit()
            fresh.execute('PRAGMA foreign_keys=ON')
        except BaseException:
            fresh.close()
            raise
        if self.connection is not None:
            self.connection.close()
        self.connection = fresh
        self.loaded_at = time.monotonic()

    @contextmanager
    def connect(self):
        with self.lock:
            if self.depth == 0 and (self.connection is None or time.monotonic()-self.loaded_at >= self.ttl):
                self.reload()
            c = self.connection
            before = c.serialize()
            expected = capture(c) if self.depth == 0 else None
            self.depth += 1
            try:
                yield c
                c.commit()
                if self.depth == 1:
                    updated = capture(c)
                    changed = {k: v for k, v in updated.items() if v != expected[k]}
                    if changed:
                        self.repository.replace({k: expected[k] for k in changed}, changed)
            except BaseException:
                c.rollback()
                c.deserialize(before)
                self.loaded_at = 0  # Unknown remote result is resolved by a fresh read, never blind retry.
                raise
            finally:
                self.depth -= 1



_store = None
_store_lock = threading.Lock()


def enabled():
    return os.getenv('DATA_BACKEND') == 'google_sheets'


def instance():
    global _store
    with _store_lock:
        if _store is None:
            _store = PrimaryStore(SheetRepository(os.environ.get('GOOGLE_SPREADSHEET_ID', '')))
        return _store
