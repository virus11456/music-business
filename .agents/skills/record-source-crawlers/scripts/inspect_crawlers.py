#!/usr/bin/env python3
"""Read an existing SIMPLES database without starting jobs or opening the network."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from source_queue import fingerprint


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def inspect(path, instant=None):
    instant = instant or datetime.now(timezone.utc)
    db = Path(path).resolve(strict=True)
    if not db.is_file():
        raise ValueError('Database must be an existing file')
    c = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    try:
        c.execute('PRAGMA query_only=ON')
        c.execute('BEGIN')  # One consistent snapshot while the service may update.
        required = {'platform_candidates', 'platform_runs', 'source_checks', 'meta'}
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            raise ValueError('Missing crawler schema: ' + ', '.join(sorted(required - tables)))
        queue = dict(total=0, unchecked=0, due=0, cached=0, invalid_retry_at=0)
        statuses = {}
        platforms = {}
        for r in c.execute('SELECT p.*,s.fingerprint AS saved_fingerprint,s.retry_at,s.status AS check_status FROM platform_candidates p LEFT JOIN source_checks s ON s.candidate_id=p.id'):
            queue['total'] += 1
            p = platforms.setdefault(r['platform'], {'saved': 0, 'stale_or_unknown_quotes': 0})
            p['saved'] += 1
            captured = timestamp(r['captured_at'])
            if captured is None or not 0 <= (instant-captured).total_seconds() <= 48*3600:
                p['stale_or_unknown_quotes'] += 1
            status = r['check_status']
            if status is None:
                queue['unchecked'] += 1
            else:
                statuses[status] = statuses.get(status, 0) + 1
            retry = timestamp(r['retry_at'])
            if status is not None and retry is None:
                queue['invalid_retry_at'] += 1
            if r['saved_fingerprint'] != fingerprint(r) or retry is None or retry <= instant:
                queue['due'] += 1
            else:
                queue['cached'] += 1
        for r in c.execute('SELECT p.platform,p.count,p.status,p.recorded_at FROM platform_runs p WHERE p.id=(SELECT max(x.id) FROM platform_runs x WHERE x.platform=p.platform)'):
            p = platforms.setdefault(r['platform'], {'saved': 0, 'stale_or_unknown_quotes': 0})
            p['last_collection'] = dict(r)
        slot = c.execute("SELECT key,value FROM meta WHERE key LIKE 'schedule_slot:%' ORDER BY key DESC LIMIT 1").fetchone()
        return {
            'observed_at': instant.isoformat(), 'read_only': True,
            'queue': {**queue, 'statuses': statuses}, 'platforms': platforms,
            'schedule': {'last_recorded_slot': {'at': slot['key'].removeprefix('schedule_slot:'), 'status': slot['value']} if slot else None,
                         'enabled': None, 'note': 'Database history only; verify live enabled/active/next_run through /api/state.'},
            'note': 'due includes invalid retry timestamps for diagnosis; counts do not prove platform connectivity or profitable matches.',
        }
    finally:
        c.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path, help='Existing SIMPLES SQLite database; opened read-only')
    args = parser.parse_args()
    try:
        result = inspect(args.db)
    except (OSError, ValueError, sqlite3.Error) as exc:
        # Avoid leaking paths, credentials or database payloads in exception messages.
        print(json.dumps({'error': type(exc).__name__, 'message': '無法讀取既有爬蟲資料庫；請檢查路徑、權限與資料表。'}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
