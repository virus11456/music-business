"""Bounded priority refresh with an oldest-first reserve; no extra requests."""
import json,hashlib
from datetime import datetime,timezone,timedelta
from decimal import Decimal,InvalidOperation
from db import connect,now

def key(url):return 'purchase_priority_'+hashlib.sha256(url.encode()).hexdigest()

def set_purchases(settings,urls,enabled):
    if not isinstance(urls,list) or not 1<=len(urls)<=200 or not isinstance(enabled,bool) or any(not isinstance(u,str) or len(u)>2000 for u in urls):
        raise ValueError('請提供 1 至 200 個已存商品連結及優先狀態')
    with connect(settings.db_path) as c:
        for url in set(urls):
            if not c.execute('SELECT 1 FROM platform_candidates WHERE source_url=?',(url,)).fetchone():raise ValueError('找不到已存貨源')
        for url in set(urls):
            if enabled:c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key(url),json.dumps({'source_url':url,'saved_at':now()})))
            else:c.execute('DELETE FROM meta WHERE key=?',(key(url),))
    return {'message':'已更新採購清單的刷新優先順序'}

def scores(settings):
    result={}
    with connect(settings.db_path) as c:
        for r in c.execute("SELECT value FROM meta WHERE key LIKE 'purchase_priority_%'"):
            try:result[json.loads(r[0])['source_url']]=(1,Decimal(0),0)
            except (ValueError,KeyError,TypeError):pass
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'sourcing_offers','published_listings','excluded_matches'}<=tables:return result
    import comparisons
    for row in comparisons.build(settings):
        if row['excluded'] or row['format']!=row['source_format'] or not row['format'] or '來源與 Discogs 條碼不一致' in row['issues']:continue
        try:gross=Decimal(row.get('gross_twd') or '0')
        except InvalidOperation:gross=Decimal(0)
        if not gross.is_finite():gross=Decimal(0)
        want=row.get('want') or 0
        if not isinstance(want,int) or isinstance(want,bool):want=0
        url=row['source_url'];purchase=result.get(url,(0,Decimal(0),0))[0]
        result[url]=max(result.get(url,(purchase,Decimal(0),0)),(purchase,max(gross,Decimal(0)),max(want,0)))
    return result

def select(c,platform,limit,priorities,instant=None):
    if limit==0:return [],{'priority':0,'rotation':0}
    instant=instant or datetime.now(timezone.utc)
    retry=(instant-timedelta(hours=1)).isoformat()
    rows=[dict(r) for r in c.execute("SELECT p.*,a.attempted_at AS refresh_attempted_at FROM platform_candidates p LEFT JOIN source_refresh_attempts a ON a.candidate_id=p.id WHERE p.platform=? AND (a.attempted_at IS NULL OR a.attempted_at<=?) ORDER BY coalesce(a.attempted_at,''),p.captured_at,p.id",(platform,retry))]
    due=[]
    for row in rows:
        score=priorities.get(row['source_url'],(0,Decimal(0),0))
        high=bool(score[0] or score[1]>0 or score[2]>=100)
        try:age=instant-datetime.fromisoformat(row['captured_at'])
        except (ValueError,TypeError):age=timedelta(days=365)
        if age>=timedelta(hours=6 if high else 24):due.append(row)
    reserve=max(1,limit//4)
    rotation=due[:reserve]
    ids={r['id'] for r in rotation}
    rest=[r for r in due if r['id'] not in ids]
    rest.sort(key=lambda r:priorities.get(r['source_url'],(0,Decimal(0),0)),reverse=True)
    selected=rotation+rest[:max(0,limit-len(rotation))]
    return selected,{'priority':sum(priorities.get(r['source_url'],(0,Decimal(0),0))>(0,Decimal(0),99) for r in selected[len(rotation):]),'rotation':len(rotation)}
