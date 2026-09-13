import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releases (
 release_id INTEGER PRIMARY KEY CHECK(release_id>0), title TEXT NOT NULL,
 artist TEXT, year INTEGER, country TEXT, format TEXT, catno TEXT,
 source_theme TEXT, added_at TEXT NOT NULL, notes TEXT);
CREATE TABLE IF NOT EXISTS snapshots (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 captured_at TEXT NOT NULL, captured_day TEXT NOT NULL,
 lowest_price TEXT, currency TEXT, num_for_sale INTEGER CHECK(num_for_sale>=0),
 have INTEGER CHECK(have>=0), want INTEGER CHECK(want>=0),
 UNIQUE(release_id, captured_day));
CREATE INDEX IF NOT EXISTS snapshots_history ON snapshots(release_id,captured_at);
CREATE TABLE IF NOT EXISTS costs (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 source TEXT NOT NULL, cost_amount TEXT NOT NULL, cost_currency TEXT NOT NULL,
 grading TEXT, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fx_rates (
 currency TEXT NOT NULL, rate_date TEXT NOT NULL, twd_per_unit TEXT NOT NULL,
 source TEXT NOT NULL, PRIMARY KEY(currency,rate_date));
CREATE TABLE IF NOT EXISTS scores (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 snapshot_id INTEGER NOT NULL REFERENCES snapshots, scored_at TEXT NOT NULL,
 opportunity_score REAL NOT NULL, components TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS score_latest ON scores(release_id,id);
CREATE TABLE IF NOT EXISTS decisions (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 decision TEXT NOT NULL CHECK(decision IN ('want','skip','watch')),
 score_at_time REAL, price_at_time TEXT, currency TEXT,
 target_price TEXT, target_currency TEXT, decided_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scan_targets (
 id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, query_params TEXT NOT NULL,
 min_want_have REAL NOT NULL DEFAULT 1.5, enabled INTEGER NOT NULL DEFAULT 1,
 last_run_at TEXT, next_page INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS alerts_sent (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 rules TEXT NOT NULL, sent_at TEXT NOT NULL, score REAL, price TEXT,
 currency TEXT, outbox_id INTEGER UNIQUE);
CREATE TABLE IF NOT EXISTS outbox (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 snapshot_id INTEGER NOT NULL REFERENCES snapshots, rules TEXT NOT NULL,
 message TEXT NOT NULL, urgent INTEGER NOT NULL, score REAL, price TEXT, currency TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','uncertain','cancelled')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT,
 UNIQUE(release_id,snapshot_id,rules));
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, status TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS api_budget (id INTEGER PRIMARY KEY CHECK(id=1), next_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS api_health (id INTEGER PRIMARY KEY CHECK(id=1), remaining INTEGER, checked_at TEXT);
PRAGMA user_version=1;
'''

@contextmanager
def connect(path):
    import sheet_primary
    if sheet_primary.enabled():
        with sheet_primary.instance().connect() as conn:
            yield conn
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

def init(path):
    with connect(path) as c:
        version = c.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise ValueError('不支援的資料庫版本')
        c.executescript(SCHEMA)

def snapshot(c, release_id, captured_at, price, currency, supply, have, want):
    day = datetime.fromisoformat(captured_at).astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()
    c.execute('''INSERT INTO snapshots(release_id,captured_at,captured_day,lowest_price,currency,num_for_sale,have,want)
      VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(release_id,captured_day) DO UPDATE SET
      captured_at=excluded.captured_at,lowest_price=excluded.lowest_price,currency=excluded.currency,
      num_for_sale=excluded.num_for_sale,have=excluded.have,want=excluded.want''',
      (release_id,captured_at,day,None if price is None else str(price),currency,supply,have,want))

def latest_decision(c, rid):
    return c.execute('SELECT * FROM decisions WHERE release_id=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()

def decide(c, rid, choice, target=None, currency=None):
    from config import money
    if choice not in ('want','skip','watch'):
        raise ValueError('決策必須為 want / skip / watch')
    if choice == 'watch' and (target is None or not currency or money(target) <= 0):
        raise ValueError('觀察必須填入大於零的目標價及幣別')
    s = c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(rid,)).fetchone()
    score = c.execute('SELECT opportunity_score FROM scores WHERE release_id=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()
    c.execute('''INSERT INTO decisions(release_id,decision,score_at_time,price_at_time,currency,target_price,target_currency,decided_at)
      VALUES(?,?,?,?,?,?,?,?)''',(rid,choice,score[0] if score else None,s['lowest_price'] if s else None,
      s['currency'] if s else None,str(money(target)) if choice=='watch' else None,currency.upper() if choice=='watch' else None,now()))
    c.execute("UPDATE outbox SET status='cancelled',updated_at=? WHERE release_id=? AND status='pending'",(now(),rid))

@contextmanager
def job(path, name):
    with connect(path) as c:
        jid = c.execute("INSERT INTO jobs(name,started_at,status) VALUES(?,?,'running')",(name,now())).lastrowid
    detail = {}
    try:
        yield detail
    except Exception as exc:
        with connect(path) as c:
            c.execute("UPDATE jobs SET finished_at=?,status='failed',detail=? WHERE id=?",(now(),json.dumps({'errors':[__import__('sync_failure').report(exc)]}) if type(exc) is __import__('sync_failure').SyncFailure else type(exc).__name__,jid))
        raise
    else:
        with connect(path) as c:
            c.execute('UPDATE jobs SET finished_at=?,status=?,detail=? WHERE id=?',
                      (now(),'partial' if detail.get('failed') else 'success',json.dumps(detail),jid))
