"""Refresh saved platform quotes without discovering products or changing manual offers."""
from datetime import datetime,timezone,timedelta
import re
from urllib.error import HTTPError, URLError
import json
from db import connect,now
import platforms

def failure_reason(error):
    # Never expose exception bodies, request headers or returned HTML in job history.
    if isinstance(error,HTTPError):return 'http_'+str(error.code)
    if isinstance(error,TimeoutError):return 'timeout'
    if isinstance(error,URLError):return 'connection'
    if isinstance(error,json.JSONDecodeError):return 'invalid_json'
    if isinstance(error,KeyError):return 'missing_field'
    reasons={
        '商品名稱變更，待重新配對':'title_changed',
        '商品格式變更，待重新配對':'format_changed',
        '商品編號或狀態無法確認':'unknown_state',
        '商品頁結構改變':'page_structure',
        '商品結構化資料不唯一':'product_structure',
        '回傳其他商品':'wrong_product',
        '商品編號不符':'wrong_product',
        '來源回傳商品編號不符':'wrong_product',
        '商品編號無效':'invalid_id',
        '價格幣別不符':'currency',
        '商品名稱或價格缺失':'missing_price_or_title',
        '拍賣時間不含時區':'auction_time',
    }
    return reasons.get(str(error),'unclassified')


def failure_item(row,reason):
    result={'external_id':str(row['external_id']),'reason':reason}
    if row['platform']=='rottenblues':result['source_url']=row['source_url']
    return result


def _ruten(settings,fetcher=None,limit=20,priorities=None):
    if not isinstance(limit,int) or not 1<=limit<=40:raise ValueError('每批刷新 1 至 40 件')
    instant=datetime.now(timezone.utc)
    cutoff=(instant-timedelta(hours=6)).isoformat()
    retry=(instant-timedelta(hours=1)).isoformat()
    with connect(settings.db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS source_refresh_attempts(candidate_id INTEGER PRIMARY KEY,attempted_at TEXT NOT NULL,status TEXT NOT NULL)')
        rows,selection=__import__('refresh_priority').select(c,'ruten',limit,priorities or {})
    report={'platform':'ruten','attempted':len(rows),'updated':0,'missing':0,'failed':0,'failures':[],'selection':selection}
    if not rows:return report
    stamp=now()
    try:
        ids=[str(r['external_id']) for r in rows]
        if any(not re.fullmatch(r'[0-9]+',i) for i in ids):raise ValueError('商品編號無效')
        raw=(fetcher or platforms.fetch)('https://rtapi.ruten.com.tw/api/prod/v3/index.php/prod?id='+','.join(ids))
        items=platforms.parse_ruten(raw)
        found={str(item['external_id']):item for item in items}
        if len(found)!=len(items) or not set(found)<=set(ids):raise ValueError('來源回傳商品編號不符')
    except Exception as error:
        report['failures']=[failure_item(row,failure_reason(error)) for row in rows]
        report['failed']=len(rows)
        with connect(settings.db_path) as c:
            for row in rows:c.execute('INSERT OR REPLACE INTO source_refresh_attempts VALUES(?,?,?)',(row['id'],stamp,'failed'))
        return report
    with connect(settings.db_path) as c:
        for row in rows:
            item=found.get(str(row['external_id']))
            status='missing'
            if item and item['title']==row['title']:
                # Identity changes need a new source search; never refresh an old match's clock.
                c.execute('UPDATE platform_candidates SET price=?,currency=?,price_kind=?,availability=?,captured_at=? WHERE id=?',
                          (item['price'],item['currency'],item['price_kind'],item['availability'],stamp,row['id']))
                report['updated']+=1;status='updated'
            elif item:report['failed']+=1;status='identity_changed'
            else:report['missing']+=1
            if status!='updated':report['failures'].append(failure_item(row,'title_changed' if item else 'not_returned'))
            c.execute('INSERT OR REPLACE INTO source_refresh_attempts VALUES(?,?,?)',(row['id'],stamp,status))
    return report


def run(settings,fetcher=None,limit=20,detail_limit=2,sleeper=None):
    """Ruten bulk refresh plus at most two saved details per other platform."""
    if not isinstance(detail_limit,int) or isinstance(detail_limit,bool) or not 0<=detail_limit<=5:
        raise ValueError('各平台商品頁刷新 0 至 5 件')
    import time
    import source_details
    priorities=__import__('refresh_priority').scores(settings)
    report=_ruten(settings,fetcher,limit,priorities)
    reports=[dict(report)]
    instant=datetime.now(timezone.utc)
    cutoff=(instant-timedelta(hours=6)).isoformat()
    retry=(instant-timedelta(hours=1)).isoformat()
    for platform in ('yahoo_tw','yahoo_jp','tower','rottenblues'):
        with connect(settings.db_path) as c:
            rows,selection=__import__('refresh_priority').select(c,platform,detail_limit,priorities)
        part={'platform':platform,'attempted':len(rows),'updated':0,'missing':0,'failed':0,'failures':[],'selection':selection}
        for row in rows:
            # Keep a gap from collection requests and between detail requests.
            (sleeper or time.sleep)(3)
            stamp=now();status='failed'
            try:
                raw=(fetcher or platforms.fetch)(source_details.detail_url(platform,row['external_id'],row['source_url']))
                item=source_details.parse(platform,row['external_id'],raw,row['source_url'])
                from source_match import identified_format
                old_format=identified_format(row['format'],row['title'])
                new_format=identified_format(item.get('format'))
                if old_format and new_format and old_format!=new_format:
                    status='identity_changed';raise ValueError('商品格式變更，待重新配對')
                if source_details.text(item['title'])!=source_details.text(row['title']):
                    status='identity_changed';raise ValueError('商品名稱變更，待重新配對')
                with connect(settings.db_path) as c:
                    c.execute('UPDATE platform_candidates SET price=?,currency=?,price_kind=?,availability=?,captured_at=? WHERE id=?',
                        (item['price'],item['currency'],item['price_kind'],item['availability'],stamp,row['id']))
                    __import__('identity_data').save_source(c,row,item)
                status='updated';part['updated']+=1
            except Exception as error:
                part['failed']+=1
                part['failures'].append(failure_item(row,failure_reason(error)))
            with connect(settings.db_path) as c:
                c.execute('INSERT OR REPLACE INTO source_refresh_attempts VALUES(?,?,?)',(row['id'],stamp,status))
        reports.append(part)
    return {'platform':'all','platforms':reports,**{key:sum(p[key] for p in reports) for key in ('attempted','updated','missing','failed')}}
