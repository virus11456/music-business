"""Explicit read-only SQLite -> Sheet migration; default audits local source only."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sheet_records import capture, digest, compare
from sheet_repository import SheetRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--sheet-id', required=True)
    parser.add_argument('--write-missing', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    path = Path(args.db).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        selected = conn.execute("SELECT value FROM meta WHERE key='google_sheet_id'").fetchone()
        if not selected or selected[0] != args.sheet_id:
            raise ValueError('Destination must match the already selected Google Sheet')
        tables = capture(conn)
    if args.write_missing:
        print(json.dumps(SheetRepository(args.sheet_id).seed_missing(tables)))
    elif args.verify:
        report = compare(tables, SheetRepository(args.sheet_id).read(list(tables)))
        print(json.dumps(report))
        if not report['equal']:
            raise SystemExit(2)
    else:
        print(json.dumps({'source_hash': digest(tables), 'table_rows': {n: len(v)-1 for n,v in tables.items()},
                          'writes': False, 'primary_switched': False}))


if __name__ == '__main__':
    main()
