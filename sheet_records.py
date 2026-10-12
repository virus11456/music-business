"""Lossless business-table contract for migration to the owner's Google Sheet.

This module does not switch the live database. SQL/schema is never loaded from Sheets.
"""
import hashlib
import json
import math
from decimal import Decimal

TABLES = (
    'purchase_items', 'releases', 'snapshots', 'costs', 'fx_rates', 'scores', 'decisions',
    'scan_targets', 'alerts_sent', 'outbox', 'jobs', 'published_listings',
    'listing_exports', 'excluded_matches', 'sourcing_offers', 'listing_drafts',
    'platform_candidates', 'platform_runs', 'version_searches', 'source_checks',
    'source_topics', 'source_pages', 'source_refresh_attempts', 'meta',
)
META_KEYS = {'mode', 'google_sheet_id', 'business_assumptions', 'last_sheet_sync',
             'reference_fx_refresh_after', 'discogs_inventory_snapshot',
             'discogs_inventory_pending', 'purchase_list_v1', 'purchase_revision'}
META_PREFIXES = ('release_labels_', 'release_barcodes_', 'source_identity_',
                 'purchase_priority_', 'schedule_slot:', 'watch_hit:', 'listing_submission:')
PREFIX = 'SIMPLES_Data_'
NULLS = '__null_columns'


def allowed_meta(key):
    return key in META_KEYS or key.startswith(META_PREFIXES)


def digest(tables):
    return hashlib.sha256(json.dumps(tables, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def capture(connection):
    """Capture within the caller's consistent read transaction. No credentials exported."""
    present = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result = {}
    for name in TABLES:
        if name not in present:
            if name == 'purchase_items': result[name] = [['key','release_id','source_url','title','seller',NULLS]]
            continue
        columns = [r[1] for r in connection.execute(f'PRAGMA table_info("{name}")')]
        rows = [list(r) for r in connection.execute(f'SELECT * FROM "{name}"')]
        if name == 'meta':
            rows = [r for r in rows if allowed_meta(r[columns.index('key')])]
        # Order-independent audit; Sheet users may sort rows without changing identity.
        rows.sort(key=lambda r: json.dumps(r, ensure_ascii=False, allow_nan=False))
        result[name] = [columns + [NULLS]]
        for row in rows:
            if any(not isinstance(v, (str, int, float, type(None))) for v in row):
                raise ValueError('Unsupported database value')
            if any(isinstance(v, float) and not math.isfinite(v) for v in row):
                raise ValueError('Non-finite number')
            encoded = ['' if v is None else v for v in row]
            if any(isinstance(v, str) and len(v.encode('utf-16-le')) // 2 > 45000 for v in encoded):
                raise ValueError(f'{name}: cell requires chunking before migration')
            result[name].append(encoded + [json.dumps([i for i, v in enumerate(row) if v is None])])
    return result


def decode(name, values, expected_columns):
    """Strict header/type shape, preserving NULL separately from empty strings."""
    if name not in TABLES or not values or values[0] != expected_columns + [NULLS]:
        raise ValueError('Sheet columns do not match the application schema')
    rows = []
    for row in values[1:]:
        if len(row) != len(expected_columns) + 1:
            raise ValueError('Incomplete Sheet row')
        nulls = json.loads(row[-1])
        if (not isinstance(nulls, list) or len(set(nulls)) != len(nulls)
                or any(type(i) is not int or not 0 <= i < len(expected_columns) for i in nulls)):
            raise ValueError('Invalid NULL marker')
        restored = list(row[:-1])
        for i in nulls:
            if restored[i] != '':
                raise ValueError('NULL marker conflicts with cell content')
            restored[i] = None
        if name == 'meta' and not allowed_meta(restored[expected_columns.index('key')]):
            raise ValueError('Unsupported configuration key')
        rows.append(restored)
    return rows


def compare(expected, actual):
    report = {}
    for name in sorted(set(expected) | set(actual)):
        left, right = expected.get(name), actual.get(name)
        equal = False
        if left and right and left[0] == right[0]:
            cols = left[0][:-1]
            lrows = decode(name, left, cols)
            rrows = decode(name, right, cols)
            def canonical(rows):
                def scalar(v):
                    if isinstance(v, (int, float)):
                        return ['number', str(Decimal(str(v)).normalize())]
                    return ['value', v]
                return sorted(json.dumps([scalar(v) for v in r], ensure_ascii=False) for r in rows)
            equal = canonical(lrows) == canonical(rrows)
        report[name] = {'source_rows': len(left)-1 if left else None,
                        'sheet_rows': len(right)-1 if right else None, 'equal': equal}
    return {'equal': bool(report) and all(r['equal'] for r in report.values()), 'tables': report}
