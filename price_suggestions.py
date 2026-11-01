"""Discogs price suggestions (seller account, by condition) for versions that already have a source pairing.

Read-only: one GET /marketplace/price_suggestions/{release_id} per version, refreshed weekly, stored in meta
`price_suggestion:<release_id>`. Shown next to the lowest listing; the profit basis is unchanged."""
import json
from datetime import datetime, timedelta, timezone
from db import connect

PREFIX = 'price_suggestion:'
MAX_AGE = timedelta(days=7)
GRADES = {'Mint (M)': 'M', 'Near Mint (NM or M-)': 'NM', 'Very Good Plus (VG+)': 'VG+', 'Very Good (VG)': 'VG'}

def parse(data):
    """{currency, M, NM, VG+, VG} from the API response, or None when it carries no usable price."""
    if not isinstance(data, dict):
        return None
    out, currencies = {}, set()
    for name, key in GRADES.items():
        item = data.get(name)
        if not isinstance(item, dict):
            continue
        value, currency = item.get('value'), item.get('currency')
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 and isinstance(currency, str) and len(currency) == 3:
            out[key] = round(float(value), 2)
            currencies.add(currency.upper())
    if not out or len(currencies) != 1:
        return None
    return {'currency': currencies.pop(), **out}

def paired_release_ids(c):
    """Versions with a confirmed offer or a linked platform candidate."""
    ids = {r[0] for r in c.execute('SELECT DISTINCT release_id FROM sourcing_offers')} if c.execute(
        "SELECT 1 FROM sqlite_master WHERE name='sourcing_offers'").fetchone() else set()
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='version_searches'").fetchone():
        for (results,) in c.execute('SELECT results FROM version_searches'):
            try:
                ids.update(int(r['release_id']) for r in json.loads(results) if isinstance(r, dict) and r.get('release_id'))
            except (ValueError, TypeError, KeyError):
                continue
    return ids

def stored(c):
    out = {}
    for key, value in c.execute('SELECT key,value FROM meta WHERE key LIKE ?', (PREFIX + '%',)):
        try:
            out[int(key[len(PREFIX):])] = json.loads(value)
        except (ValueError, TypeError):
            continue
    return out

def due(c, instant):
    """Paired versions without a suggestion first, then the oldest past MAX_AGE."""
    have = stored(c)
    def age(rid):
        try:
            return instant - datetime.fromisoformat(have[rid]['at'])
        except (KeyError, ValueError, TypeError):
            return None
    missing = sorted(rid for rid in paired_release_ids(c) if rid not in have)
    old = sorted((rid for rid in have if rid in paired_release_ids(c) and (age(rid) is None or age(rid) >= MAX_AGE)), key=lambda r: have[r].get('at', ''))
    return missing + old

def refresh(settings, client=None, limit=150, instant=None):
    instant = instant or datetime.now(timezone.utc)
    result = {'checked': 0, 'saved': 0, 'empty': 0, 'failed': 0, 'due': 0}
    if not settings.token:
        return {**result, 'skipped': 'no_token'}
    with connect(settings.db_path) as c:
        queue = due(c, instant)
    result['due'] = len(queue)
    if not queue:
        return result
    if client is None:
        from discogs_client import DiscogsClient
        client = DiscogsClient(settings)
    from discogs_client import APIError
    for rid in queue[:limit]:
        result['checked'] += 1
        try:
            parsed = parse(client.get(f'/marketplace/price_suggestions/{rid}'))
        except (APIError, ValueError, TypeError):
            result['failed'] += 1
            continue
        entry = {'at': instant.isoformat(), **(parsed or {'currency': None})}
        with connect(settings.db_path) as c:
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (PREFIX + str(rid), json.dumps(entry)))
        result['saved' if parsed else 'empty'] += 1
    return result
