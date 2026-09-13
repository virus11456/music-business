"""Read-only audits of one Sheet snapshot and comparison output; no repair or writes."""
import json
import sqlite3
from collections import Counter
from decimal import Decimal, InvalidOperation
from sheet_records import TABLES, decode, capture, compare
from sheet_primary import memory_schema
from matching import normalized


def audit_tables(data):
    c = memory_schema()
    errors = []
    counts = {}
    try:
        c.execute('PRAGMA foreign_keys=OFF')
        for name in TABLES:
            try:
                cols = [r[1] for r in c.execute(f'PRAGMA table_info("{name}")')]
                rows = decode(name, data.get(name), cols)
                counts[name] = len(rows)
                c.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in cols)})', rows)
            except (ValueError, TypeError, sqlite3.Error):
                errors.append({'table': name, 'code': 'schema_type_or_unique_constraint'})
        broken = list(c.execute('PRAGMA foreign_key_check'))
        errors.extend({'table': r[0], 'code': 'missing_parent', 'row': r[1]} for r in broken)
        if not errors and not compare(data, capture(c))['equal']:
            errors.append({'code': 'roundtrip_mismatch'})
        for row in c.execute('SELECT candidate_id,results FROM version_searches'):
            try:
                results = json.loads(row['results'])
                ids = [r['release_id'] for r in results]
                if any(type(rid) is not int or rid <= 0 for rid in ids) or len(ids) != len(set(ids)):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                errors.append({'code': 'invalid_search_results', 'candidate_id': row['candidate_id']})
        platforms = dict(c.execute('SELECT platform,count(*) FROM platform_candidates GROUP BY platform'))
        checks = dict(c.execute('SELECT status,count(*) FROM source_checks GROUP BY status'))
        jobs = [dict(r) for r in c.execute('SELECT id,status,started_at,finished_at FROM jobs ORDER BY id DESC LIMIT 3')]
        return {'ok': not errors, 'tables': counts, 'errors': errors, 'platforms': platforms,
                'checks': checks, 'jobs': jobs, 'scope': 'single_read_snapshot_not_write_probe'}
    finally:
        c.close()


def audit_comparisons(rows):
    errors = []
    keys = Counter(r['key'] for r in rows)
    for key, count in keys.items():
        if count > 1:
            errors.append({'key': key, 'code': 'duplicate_comparison'})
    positive = 0
    for r in rows:
        if r.get('excluded'):
            continue
        if not r.get('offer') and r.get('format') and r.get('source_format') != r['format']:
            errors.append({'key': r['key'], 'code': 'candidate_format_conflict'})
        catalog = normalized(r.get('source_catalog_no') or '')
        catalogs = {normalized(v) for v in (r.get('catalog_no') or '').split(',')} - {'', 'none', 'na', '未確認'}
        if not r.get('offer') and catalog not in ('', 'none', 'na', '未確認') and catalogs and catalog not in catalogs:
            errors.append({'key': r['key'], 'code': 'candidate_catalog_conflict'})
        a, b = set(r.get('barcodes') or []), set(r.get('source_barcodes') or [])
        if not r.get('offer') and a and b and not a & b:
            errors.append({'key': r['key'], 'code': 'candidate_barcode_conflict'})
        if r.get('gross_twd') is None:
            continue
        try:
            sale = Decimal(str(r['sale_twd']))
            buy = Decimal(str(r['cost_twd'] if r.get('cost_basis') == 'confirmed_total' else r['source_twd']))
            gross = Decimal(str(r['gross_twd']))
            margin = Decimal(str(r['gross_margin']))
            if not all(v.is_finite() for v in [sale, buy, gross, margin]) or sale <= 0:
                raise ValueError()
            # API rounds amounts to cents while margin uses original conversion precision.
            if abs((sale-buy)-gross) > Decimal('.02') or abs(gross-margin*sale) > Decimal('.0051')*(1+abs(margin)):
                errors.append({'key': r['key'], 'code': 'gross_math_mismatch'})
            if gross > 0 and (r.get('want') or 0) > 0:
                positive += 1
        except (InvalidOperation, ValueError, TypeError, KeyError, ZeroDivisionError):
            errors.append({'key': r['key'], 'code': 'invalid_gross_values'})
    return {'ok': not errors, 'rows': len(rows), 'positive_demand_combinations': positive, 'errors': errors,
            'scope': 'structure_format_barcode_arithmetic_not_pressing_confirmation'}
