"""Per-platform health from the nightly sourcing run: a platform that fails half or more of its searches is
marked failing, and a change of state (ok -> failing, failing -> ok) is reported once. No platform is paused
or retried here; failures stay isolated per platform as before."""
import json
from datetime import datetime, timezone
from db import connect

PREFIX = 'platform_health:'
MIN_SEARCHES = 5     # fewer searches than this say too little to judge
FAIL_RATE = .5
NAMES = {'yahoo_tw': 'Yahoo 台灣', 'yahoo_jp': 'Yahoo 日本', 'ruten': '露天', 'tower': 'Tower', 'rakuten': '樂天市場',
         'ebay': 'eBay', 'rottenblues': 'Rotten Blues'}

def record(settings, stats, instant=None, sender=None):
    """`stats` is demand_queue's per-platform {success, empty, failed, items, errors}."""
    at = (instant or datetime.now(timezone.utc)).isoformat()
    changes = []
    with connect(settings.db_path) as c:
        for platform, s in sorted((stats or {}).items()):
            searches = sum(int(s.get(k, 0)) for k in ('success', 'empty', 'failed'))
            if searches < MIN_SEARCHES:
                continue
            status = 'failing' if s.get('failed', 0) / searches >= FAIL_RATE else 'ok'
            row = c.execute('SELECT value FROM meta WHERE key=?', (PREFIX + platform,)).fetchone()
            previous = json.loads(row[0]) if row else {}
            since = previous.get('since') if previous.get('status') == status and previous.get('since') else at
            entry = {'status': status, 'since': since, 'checked_at': at, 'searches': searches,
                     'failed': int(s.get('failed', 0)), 'items': int(s.get('items', 0)), 'errors': dict(s.get('errors') or {})}
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (PREFIX + platform, json.dumps(entry, ensure_ascii=False)))
            # A first record that is already ok is not news; a first failing one is.
            if previous.get('status', 'ok') != status:
                changes.append({'platform': platform, **entry})
    sent = False
    if changes and settings.telegram_token and settings.telegram_chat:
        send = sender or __import__('notify').telegram
        try:
            send(settings, message(changes))
            sent = True
        except Exception:
            sent = False  # The change stays visible on the site and in the job record.
    return {'changes': [{'platform': ch['platform'], 'status': ch['status']} for ch in changes], 'notified': sent}

def message(changes):
    lines = ['SIMPLES 平台狀態變更']
    for ch in changes:
        name = NAMES.get(ch['platform'], ch['platform'])
        errors = '、'.join(f'{k} {v} 次' for k, v in ch['errors'].items())
        if ch['status'] == 'failing':
            lines.append(f"⚠️ {name}：{ch['failed']}/{ch['searches']} 次搜尋失敗" + (f'（{errors}）' if errors else ''))
        else:
            lines.append(f"✅ {name} 已恢復：{ch['searches']} 次搜尋、{ch['items']} 件商品")
    return '\n'.join(lines)

def state(settings):
    with connect(settings.db_path) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone():
            return []
        rows = c.execute('SELECT key,value FROM meta WHERE key LIKE ?', (PREFIX + '%',)).fetchall()
    out = []
    for key, value in rows:
        try:
            entry = json.loads(value)
        except ValueError:
            continue
        out.append({'platform': key[len(PREFIX):], **entry})
    return sorted(out, key=lambda e: (e.get('status') != 'failing', e['platform']))
