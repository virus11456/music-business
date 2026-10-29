"""Google Sheets authoritative storage; SQLite is a volatile query engine only.

One application process owns writes. No fallback to a disk database on any error.
"""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
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
    def __init__(self, repository, ttl=30, retry=10, flush_after=60, flush_every=25):
        self.repository = repository
        self.ttl = ttl
        self.retry = retry
        self.flush_after = flush_after
        self.flush_every = flush_every
        self.deferred_depth = 0
        self.pending_before = None
        self.pending_count = 0
        self.pending_since = 0
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
        self.loaded_wall = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.generation += 1
        self.invalid = False
        self.refresh_error = None

    def reload(self):
        self._install(self._build(self.repository.read(list(TABLES))))

    def refresh_in_background(self):
        """Serve the current view while a newer Sheet read is prepared; never block a request."""
        if self.refresh_thread is not None and self.refresh_thread.is_alive():
            return
        if self.pending_before is not None:
            return  # unflushed local work must not be replaced by an older Sheet read
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
                if self.writes != started_writes or self.depth or self.invalid or self.pending_before is not None:
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
            # A fixed wall-clock stamp, not an age: an age changes every second and would defeat response validators.
            loaded = None if self.connection is None else self.loaded_wall
            return {'loaded_at': loaded, 'refresh_error': self.refresh_error,
                    'refreshing': bool(self.refresh_thread is not None and self.refresh_thread.is_alive()),
                    'pending_writes': self.pending_count}

    def _push(self, before, c):
        """Compare the view against `before` and write every changed table to the Sheet once."""
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

    def flush(self):
        """Write deferred local changes to the Sheet. An unknown result reverts the view and forces a re-read."""
        with self.lock:
            if self.pending_before is None:
                return
            before, self.pending_before, self.pending_count = self.pending_before, None, 0
            try:
                self._push(before, self.connection)
            except BaseException:
                self.connection.deserialize(before)
                self.invalid = True
                raise

    @contextmanager
    def deferred(self):
        """Coalesce Sheet writes for a background job: local transactions commit at once and stay visible,
        the Sheet receives one write per `flush_after` seconds or `flush_every` transactions, and on exit.
        Only the job thread writes while a job runs (the dashboard lock blocks other mutations)."""
        with self.lock:
            self.deferred_depth += 1
        try:
            yield
        finally:
            with self.lock:
                self.deferred_depth -= 1
                if self.deferred_depth == 0:
                    self.flush()

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
                    if self.deferred_depth:
                        if self.pending_before is None:
                            self.pending_before, self.pending_since = before, time.monotonic()
                        self.pending_count += 1
                        if self.pending_count >= self.flush_every or time.monotonic() - self.pending_since >= self.flush_after:
                            self.flush()
                    else:
                        self._push(before, c)
            except BaseException:
                c.rollback()
                if before is not None and self.pending_before is None:
                    c.deserialize(before)
                    self.invalid = True  # Unknown remote result is resolved by a fresh read, never blind retry.
                elif before is not None:
                    c.deserialize(before)  # this transaction only; earlier deferred work stays pending
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


@contextmanager
def deferred():
    """Coalesced Sheet writes for a background job; a no-op outside Sheet-primary mode."""
    if not enabled():
        yield
        return
    with instance().deferred():
        yield


def instance():
    global _store
    with _store_lock:
        if _store is None:
            # This process is the only writer; the Sheet is re-read in the background every few minutes for manual edits.
            ttl = int(os.environ.get('SHEET_CACHE_SECONDS', '300') or 300)
            _store = PrimaryStore(SheetRepository(os.environ.get('GOOGLE_SPREADSHEET_ID', '')), ttl=max(30, ttl))
        return _store
