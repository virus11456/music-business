"""Refresh saved platform quotes without discovering products or changing manual offers."""
from datetime import datetime,timezone,timedelta
import re
from db import connect,now
import platforms

def _ruten(settings,fetcher=None,limit=20):
    if not isinstance(limit,int) or not 1<=limit<=40:raise ValueError('每批刷新 1 至 40 件')
    instant=datetime.now(timezone.utc)
    cutoff=(instant-timedelta(hours=6)).isoformat()
    retry=(instant-timedelta(hours=1)).isoformat()
    with connect(settings.db_path) as c:
        c.execute('CREATE TABLE IF NOT EXISTS source_refresh_attempts(candidate_id INTEGER PRIMARY KEY,attempted_at TEXT NOT NULL,status TEXT NOT NULL)')
        rows=[dict(r) for r in c.execute("SELECT p.* FROM platform_candidates p LEFT JOIN source_refresh_attempts a ON a.candidate_id=p.id WHERE p.platform='ruten' AND p.captured_at<=? AND (a.attempted_at IS NULL OR a.attempted_at<=?) ORDER BY coalesce(a.attempted_at,''),p.captured_at,p.id LIMIT ?",(cutoff,retry,limit))]
    report={'platform':'ruten','attempted':len(rows),'updated':0,'missing':0,'failed':0}
    if not rows:return report
    stamp=now()
    try:
        ids=[str(r['external_id']) for r in rows]
        if any(not re.fullmatch(r'[0-9]+',i) for i in ids):raise ValueError('商品編號無效')
        raw=(fetcher or platforms.fetch)('https://rtapi.ruten.com.tw/api/prod/v3/index.php/prod?id='+','.join(ids))
        items=platforms.parse_ruten(raw)
        found={str(item['external_id']):item for item in items}
        if len(found)!=len(items) or not set(found)<=set(ids):raise ValueError('來源回傳商品編號不符')
    except Exception:
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
            c.execute('INSERT OR REPLACE INTO source_refresh_attempts VALUES(?,?,?)',(row['id'],stamp,status))
    return report


def run(settings,fetcher=None,limit=20,detail_limit=2,sleeper=None):
    """Ruten bulk refresh plus at most two saved details per other platform."""
    if not isinstance(detail_limit,int) or isinstance(detail_limit,bool) or not 0<=detail_limit<=5:
        raise ValueError('各平台商品頁刷新 0 至 5 件')
    import time
    import source_details
    report=_ruten(settings,fetcher,limit)
    reports=[dict(report)]
    instant=datetime.now(timezone.utc)
    cutoff=(instant-timedelta(hours=6)).isoformat()
    retry=(instant-timedelta(hours=1)).isoformat()
    for platform in ('yahoo_tw','yahoo_jp','tower'):
        with connect(settings.db_path) as c:
            rows=[dict(r) for r in c.execute("SELECT p.* FROM platform_candidates p LEFT JOIN source_refresh_attempts a ON a.candidate_id=p.id WHERE p.platform=? AND p.captured_at<=? AND (a.attempted_at IS NULL OR a.attempted_at<=?) ORDER BY coalesce(a.attempted_at,''),p.captured_at,p.id LIMIT ?",(platform,cutoff,retry,detail_limit))]
        part={'platform':platform,'attempted':len(rows),'updated':0,'missing':0,'failed':0}
        for row in rows:
            # Keep a gap from collection requests and between detail requests.
            (sleeper or time.sleep)(3)
            stamp=now();status='failed'
            try:
                raw=(fetcher or platforms.fetch)(source_details.detail_url(platform,row['external_id']))
                item=source_details.parse(platform,row['external_id'],raw)
                from source_match import identified_format
                old_format=identified_format(row['format'],row['title'])
                new_format=identified_format(item.get('format'))
                if (old_format and new_format and old_format!=new_format) or source_details.text(item['title'])!=source_details.text(row['title']):
                    status='identity_changed';raise ValueError('商品名稱變更，待重新配對')
                with connect(settings.db_path) as c:
                    c.execute('UPDATE platform_candidates SET price=?,currency=?,price_kind=?,availability=?,captured_at=? WHERE id=?',
                        (item['price'],item['currency'],item['price_kind'],item['availability'],stamp,row['id']))
                status='updated';part['updated']+=1
            except Exception:
                part['failed']+=1
            with connect(settings.db_path) as c:
                c.execute('INSERT OR REPLACE INTO source_refresh_attempts VALUES(?,?,?)',(row['id'],stamp,status))
        reports.append(part)
    return {'platform':'all','platforms':reports,**{key:sum(p[key] for p in reports) for key in ('attempted','updated','missing','failed')}}
