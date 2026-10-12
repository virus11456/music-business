"""Create Discogs marketplace listings from confirmed drafts, one attempt each.

Every attempt is recorded before the request is sent. Unknown outcomes stay
`uncertain` until the inventory read-back or a human confirms them; nothing here
retries a write on its own.
"""
import json
import os
from datetime import datetime, timezone

from db import connect, now
from discogs_client import DiscogsClient, ListingRejected, ListingUncertain
import workflow

PREFIX = workflow.SUBMISSION_PREFIX
STATUSES = ('submitting', 'listed', 'failed', 'uncertain')
LISTING_STATUSES = ('Draft', 'For Sale')
OPEN = ('submitting', 'uncertain')
HISTORY_LIMIT = 10


def configured():
    return os.getenv('DISCOGS_LISTING_WRITE', '').strip() == '1'


def external_id(draft_id, release_id):
    return f'simples-{draft_id}-release-{release_id}'


def key(draft_id):
    return PREFIX + str(draft_id)


def submission(c, draft_id):
    return workflow.submission_record(c, draft_id)


def all_submissions(c):
    rows = []
    for r in c.execute('SELECT value FROM meta WHERE key LIKE ?', (PREFIX + '%',)):
        try:
            data = json.loads(r[0])
        except ValueError:
            data = None
        rows.append(data if isinstance(data, dict) else {'draft_id': None, 'status': 'damaged', 'reason': '送出紀錄損壞，請人工核對', 'started_at': ''})
    rows.sort(key=lambda r: (r.get('started_at') or '', r.get('draft_id') or 0), reverse=True)
    return rows


def state(settings):
    with connect(settings.db_path) as c:
        rows = all_submissions(c)
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        if row.get('status') in counts:
            counts[row['status']] += 1
    return {'enabled': configured(), 'counts': counts, 'rows': rows[:100], 'limit': 100}


def _comments(draft):
    text = draft['description']
    if draft['dispatch_days']:
        text += f" Dispatch within {draft['dispatch_days']} days after payment."
    return text[:500]


def prepare(settings, draft_ids, seller_currency, status):
    """Validate the whole batch before any request; raises a user-facing error."""
    if not configured():
        raise workflow.BatchDraftError('尚未啟用 Discogs 刊登寫入：請在後端設定 DISCOGS_LISTING_WRITE=1')
    if status not in LISTING_STATUSES:
        raise workflow.BatchDraftError('刊登狀態只能是 Draft（Discogs 草稿）或 For Sale（直接出售）')
    if (not isinstance(draft_ids, list) or not 1 <= len(draft_ids) <= 50 or len(set(draft_ids)) != len(draft_ids)
            or any(type(x) is not int or x <= 0 for x in draft_ids)):
        raise workflow.BatchDraftError('請選擇 1 至 50 筆不同草稿')
    drafts = []
    with connect(settings.db_path) as c:
        for draft_id in draft_ids:
            r = c.execute('SELECT d.*,r.artist,r.title,r.catno,r.format,r.year FROM listing_drafts d JOIN releases r USING(release_id) WHERE d.id=?', (draft_id,)).fetchone()
            if not r:
                raise workflow.BatchDraftError(f'草稿 #{draft_id} 不存在')
            issues = workflow.draft_export_issues(c, r)
            if issues:
                raise workflow.BatchDraftError(f'草稿 #{draft_id}：' + '；'.join(issues))
            if r['currency'] != seller_currency:
                raise workflow.BatchDraftError(f'草稿 #{draft_id} 幣別與 Discogs 賣家設定不同，請分批送出')
            drafts.append(dict(r))
    return drafts


def _save(c, record):
    c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key(record['draft_id']), json.dumps(record, ensure_ascii=False)))


def _begin(c, draft, status):
    previous = submission(c, draft['id'])
    history = []
    if previous:
        if previous.get('status') not in ('listed', 'failed'):
            raise ValueError(f"草稿 #{draft['id']} 仍有結果不明的送出，請先核對")
        history = (previous.get('history') or []) + [{k: previous.get(k) for k in ('status', 'listing_id', 'reason', 'requested_status', 'started_at', 'finished_at')}]
    record = {'draft_id': draft['id'], 'release_id': draft['release_id'], 'source_url': draft['source_url'],
              'external_id': external_id(draft['id'], draft['release_id']), 'artist': draft['artist'], 'title': draft['title'],
              'price': draft['price'], 'currency': draft['currency'], 'media_cond': draft['media_cond'], 'sleeve_cond': draft['sleeve_cond'],
              'requested_status': status, 'status': 'submitting', 'listing_id': None, 'reason': None,
              'started_at': now(), 'finished_at': None, 'attempts': len(history) + 1, 'history': history[-HISTORY_LIMIT:]}
    _save(c, record)
    return record


def _finish(c, record, status, listing_id=None, reason=None):
    record.update(status=status, listing_id=listing_id, reason=reason, finished_at=now())
    if status == 'listed':
        c.execute('INSERT INTO published_listings VALUES(?,?,?,?) ON CONFLICT(source_url,release_id) DO UPDATE SET listing_id=excluded.listing_id,recorded_at=excluded.recorded_at',
                  (record['source_url'], record['release_id'], str(listing_id), now()))
    _save(c, record)


def run(settings, draft_ids, seller_currency, status='Draft', client=None):
    drafts = prepare(settings, draft_ids, seller_currency, status)
    client = client or DiscogsClient(settings)
    summary = {'listing_publish': True, 'requested_status': status, 'listed': 0, 'rejected': 0, 'uncertain': 0, 'not_attempted': 0, 'failed': 0, 'items': []}
    stop = False
    for draft in drafts:
        if stop:
            summary['not_attempted'] += 1
            summary['items'].append({'draft_id': draft['id'], 'status': 'not_attempted'})
            continue
        with connect(settings.db_path) as c:
            record = _begin(c, draft, status)
        payload = {'release_id': draft['release_id'], 'condition': draft['media_cond'], 'sleeve_condition': draft['sleeve_cond'],
                   'price': float(draft['price']), 'status': status, 'comments': _comments(draft),
                   'external_id': record['external_id'], 'allow_offers': False}
        try:
            data = client.post('/marketplace/listings', payload)
            listing_id = data.get('listing_id')
            if type(listing_id) is not int or listing_id < 1:
                raise ListingUncertain('Discogs 回應缺少刊登編號，刊登結果不明')
            outcome, listing, reason = 'listed', listing_id, None
        except ListingRejected as error:
            outcome, listing, reason = 'failed', None, str(error)
        except ListingUncertain as error:
            outcome, listing, reason = 'uncertain', None, str(error)
        except Exception as error:
            outcome, listing, reason = 'uncertain', None, '送出過程發生未預期錯誤：' + type(error).__name__
        with connect(settings.db_path) as c:
            _finish(c, record, outcome, listing, reason)
        summary['items'].append({'draft_id': draft['id'], 'status': outcome, 'listing_id': listing, 'reason': reason})
        if outcome == 'listed':
            summary['listed'] += 1
        elif outcome == 'failed':
            summary['rejected'] += 1
        else:
            summary['uncertain'] += 1
            stop = True  # a broken connection must not cascade into more unknown outcomes
    summary['failed'] = summary['rejected'] + summary['uncertain'] + summary['not_attempted']
    return summary


def resolve(settings, draft_id, outcome, listing_id=None):
    """Human confirmation of an open attempt after checking Discogs. No request is sent."""
    if type(draft_id) is not int or draft_id < 1 or outcome not in ('listed', 'not_listed'):
        raise ValueError('刊登核對資料無效')
    if outcome == 'listed':
        listing = str(listing_id or '').strip()
        if not listing.isascii() or not listing.isdigit() or int(listing) <= 0:
            raise ValueError('請填 Discogs 刊登編號')
        listing_id = int(listing)
    with connect(settings.db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        record = submission(c, draft_id)
        if not record or record.get('status') not in OPEN:
            raise ValueError('只能處理結果不明的送出，請重新整理')
        if outcome == 'listed':
            _finish(c, record, 'listed', listing_id, '人工核對：Discogs 已有此刊登')
        else:
            _finish(c, record, 'failed', None, '人工核對：Discogs 未建立刊登，可重新確認草稿後再送出')
    return {'saved': True, 'message': '刊登核對結果已儲存；沒有重送請求'}


def reconcile(c, rows):
    """Close open attempts that the complete inventory snapshot proves exist. Returns the count."""
    confirmed = 0
    by_external = {r['external_id']: r for r in rows if r.get('external_id')}
    for record in all_submissions(c):
        if record.get('status') not in OPEN:
            continue
        row = by_external.get(record.get('external_id'))
        if not row or row['release_id'] != record['release_id']:
            continue
        _finish(c, record, 'listed', row['listing_id'], f"庫存讀回確認：{row['status']}")
        confirmed += 1
    return confirmed


def stale_open(record, at=None, minutes=10):
    """An attempt still `submitting` long after it started lost its final write; humans may resolve it."""
    if record.get('status') != 'submitting':
        return record.get('status') == 'uncertain'
    try:
        started = datetime.fromisoformat(record['started_at'])
    except (KeyError, TypeError, ValueError):
        return True
    return ((at or datetime.now(timezone.utc)) - started).total_seconds() > minutes * 60
