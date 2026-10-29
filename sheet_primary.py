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
    """In-memory SQLite view of the Sheet.

    Reads never compare tables: a connection only pays for a snapshot copy, and the
    before/after table comparison runs only when the transaction changed rows. An
    expired view is refreshed in the background while requests keep being served;
    an unknown remote result still forces a synchronous re-read before the next use.
    """
    def __init__(self, repository, ttl=30, retry=10):
        self.repository = repository
        self.ttl = ttl
        self.retry = retry
        self.lock = threading.RLock()
        self.connection = None
        self.loaded_at = 0
        self.depth = 0
        self.generation = 0
        self.invalid = False
        self.writes = 0
        self.refresh_thread = None
        self.refresh_error = None
        self.refresh_failed_at = None

    def _build(self, data):
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
            fresh.commit()
            fresh.execute('PRAGMA foreign_keys=ON')
        except BaseException:
            fresh.close()
            raise
        return fresh

    def _install(self, fresh):
        # Local-only rate counters/cache may survive a refresh, never a process restart.
        if self.connection is not None:
            for table in ('api_budget', 'api_health'):
                for row in self.connection.execute(f'SELECT * FROM {table}'):
                    fresh.execute(f'INSERT OR REPLACE INTO {table} VALUES({",".join("?" for _ in row)})', tuple(row))
            for row in self.connection.execute('SELECT key,value FROM meta'):
                if not allowed_meta(row[0]):
                    fresh.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', tuple(row))
            fresh.commit()
            self.connection.close()
        self.connection = fresh
        self.loaded_at = time.monotonic()
        self.generation += 1
        self.invalid = False
        self.refresh_error = None

    def reload(self):
        self._install(self._build(self.repository.read(list(TABLES))))

    def refresh_in_background(self):
        """Serve the current view while a newer Sheet read is prepared; never block a request."""
        if self.refresh_thread is not None and self.refresh_thread.is_alive():
            return
        if self.refresh_failed_at is not None and time.monotonic() - self.refresh_failed_at < self.retry:
            return
        started_writes = self.writes
        def worker():
            try:
                fresh = self._build(self.repository.read(list(TABLES)))
            except Exception as exc:
                with self.lock:
                    self.refresh_error = type(exc).__name__
                    self.refresh_failed_at = time.monotonic()
                return
            with self.lock:
                # A write committed meanwhile is newer than this read; keep the local view and retry later.
                if self.writes != started_writes or self.depth or self.invalid:
                    fresh.close()
                    return
                self._install(fresh)
        self.refresh_thread = threading.Thread(target=worker, name='sheet-refresh', daemon=True)
        self.refresh_thread.start()

    def version(self):
        """Changes whenever the served data can differ; safe as a cache key for derived views."""
        with self.lock:
            return (self.generation, self.connection.total_changes if self.connection is not None else -1)

    def status(self):
        with self.lock:
            age = None if self.connection is None else round(time.monotonic() - self.loaded_at)
            return {'loaded_seconds_ago': age, 'refresh_error': self.refresh_error,
                    'refreshing': bool(self.refresh_thread is not None and self.refresh_thread.is_alive())}

    @contextmanager
    def connect(self):
        with self.lock:
            if self.depth == 0:
                if self.connection is None or self.invalid:
                    self.reload()
                elif time.monotonic() - self.loaded_at >= self.ttl:
                    self.refresh_in_background()
            c = self.connection
            before = c.serialize() if self.depth == 0 else None
            changes = c.total_changes
            self.depth += 1
            try:
                yield c
                c.commit()
                if self.depth == 1 and c.total_changes != changes:
                    scratch = sqlite3.connect(':memory:')
                    try:
                        scratch.deserialize(before)
                        expected = capture(scratch)
                    finally:
                        scratch.close()
                    updated = capture(c)
                    changed = {k: v for k, v in updated.items() if v != expected[k]}
                    if changed:
                        self.repository.replace({k: expected[k] for k in changed}, changed)
                        self.writes += 1
            except BaseException:
                c.rollback()
                if before is not None:
                    c.deserialize(before)
                    self.invalid = True  # Unknown remote result is resolved by a fresh read, never blind retry.
                raise
            finally:
                self.depth -= 1



_store = None
_store_lock = threading.Lock()


def enabled():
    return os.getenv('DATA_BACKEND') == 'google_sheets'


def version():
    return instance().version() if enabled() else None


def status():
    return instance().status() if enabled() else None


def instance():
    global _store
    with _store_lock:
        if _store is None:
            _store = PrimaryStore(SheetRepository(os.environ.get('GOOGLE_SPREADSHEET_ID', '')))
        return _store
