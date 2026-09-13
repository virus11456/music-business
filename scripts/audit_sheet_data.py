#!/usr/bin/env python3
"""Read deployed Sheet data and authenticated API output; never start a batch."""
import json
import os
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import load_env
from sheet_repository import SheetRepository
from sheet_records import TABLES
from sheet_audit import audit_tables, audit_comparisons

if __name__ == '__main__':
    load_env()
    if os.environ.get('DATA_BACKEND') != 'google_sheets':
        raise SystemExit('Google Sheet primary mode required')
    data = SheetRepository(os.environ['GOOGLE_SPREADSHEET_ID']).read(list(TABLES))
    report = audit_tables(data)
    print('SHEET_AUDIT', json.dumps(report, ensure_ascii=False), flush=True)
    headers = {'Authorization': 'Bearer '+os.environ['REMOTE_ACCESS_TOKEN'],
               'Origin': 'https://music-business.vercel.app'}
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8765/api/state', headers=headers), timeout=60) as response:
            state = json.load(response)
        checks = audit_comparisons(state['workflow']['comparisons'])
        print('COMPARISON_AUDIT', json.dumps(checks, ensure_ascii=False), flush=True)
        print('ACTIVE', json.dumps(state['active'], ensure_ascii=False), flush=True)
        raise SystemExit(0 if report['ok'] and checks['ok'] else 1)
    except (OSError, ValueError, KeyError):
        print('COMPARISON_AUDIT unavailable; Sheet result does not verify API output', flush=True)
        raise SystemExit(2)
