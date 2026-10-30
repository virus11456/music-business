"""Persistent source-first work queue. No purchase or listing side effects."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from db import connect, now
import platforms, matching, ingest, analyze, sheet_sync
from discogs_client import DiscogsClient
from source_match import evidence

SCHEMA='''CREATE TABLE IF NOT EXISTS source_checks (
 candidate_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
 status TEXT NOT NULL, checked_at TEXT NOT NULL, retry_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_topics (
 query TEXT PRIMARY KEY, platforms TEXT NOT NULL, collected_at TEXT);
CREATE TABLE IF NOT EXISTS source_pages (query TEXT NOT NULL,platform TEXT NOT NULL,next_page INTEGER NOT NULL,PRIMARY KEY(query,platform));
'''

def init(settings):
    with connect(settings.db_path) as c:c.executescript(SCHEMA)

def fingerprint(row):
    # Price/stock changes recalculate profit but do not change a version identity.
    values=[row[k] for k in ('title','artist','format','catalog_no')]
    if isinstance(row,dict) and (row.get('barcodes') or row.get('labels')):values.extend([row.get('barcodes',[]),row.get('labels','')])
    return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()

def needs_check(row,instant):
    """Expired or unusable cache timestamps must not hide saved source work."""
    if row['saved_fingerprint']!=fingerprint(row):return True
    try:
        retry=datetime.fromisoformat(row['retry_at'])
        if retry.tzinfo is None:return True
    except (TypeError,ValueError):return True
    return retry<=instant

def _pending_count(c,instant):
    import identity_data
    saved=identity_data.identities(c)
    rows=c.execute('SELECT p.*,s.fingerprint AS saved_fingerprint,s.retry_at FROM platform_candidates p LEFT JOIN source_checks s ON s.candidate_id=p.id')
    return sum(needs_check(identity_data.enrich(c,r,saved),instant) for r in rows)

def pending_count(settings):
    with connect(settings.db_path) as c:
        return _pending_count(c,datetime.now(timezone.utc))

def state(settings):
    with connect(settings.db_path) as c:
        statuses={r[0]:r[1] for r in c.execute('SELECT status,count(*) FROM source_checks GROUP BY status')}
        total=c.execute('SELECT count(*) FROM platform_candidates').fetchone()[0]
        return {'total':total,'unchecked':total-sum(statuses.values()),'pending':_pending_count(c,datetime.now(timezone.utc)),'statuses':statuses,
                'topics':[dict(r) for r in c.execute('SELECT * FROM source_topics ORDER BY query')]}

def run(settings,query=None,selected=None,limit=20,source_platform=None):
    if source_platform is not None and (not isinstance(source_platform,str) or source_platform not in platforms.PARSERS or query):raise ValueError('指定來源只能比對已保存商品')
    init(settings)
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=40:raise ValueError('每批比對 1 至 40 件')
    result={'flow':'source_first','checked':0,'cached':0,'matched':0,'unmatched':0,'market_updated':0,'errors':[],'sheet_sync':None}
    import time
    from concurrent.futures import ThreadPoolExecutor
    timings={};mark=time.perf_counter()
    def lap(name):
        nonlocal mark
        now_mark=time.perf_counter();timings[name]=round(now_mark-mark,1);mark=now_mark
    if query:
        report={'candidates':0,'failed_platforms':0,'platforms':[]}
        def collect(platform):
            with connect(settings.db_path) as c:
                previous=c.execute('SELECT next_page FROM source_pages WHERE query=? AND platform=?',(query,platform)).fetchone()
            page=previous[0] if previous else 1
            batch=platforms.search(settings,query,[platform],page=page,full_page=True)
            if not batch['failed_platforms']:
                has_more=batch['platforms'][0].get('has_more',bool(batch['candidates']))
                next_page=page+1 if has_more and page<1000 else 1
                with connect(settings.db_path) as c:c.execute('INSERT OR REPLACE INTO source_pages VALUES(?,?,?)',(query,platform,next_page))
            return page,batch
        # Different sites in parallel; each site still receives one request at a time.
        chosen=list(dict.fromkeys(selected))
        with ThreadPoolExecutor(max_workers=max(1,len(chosen)),thread_name_prefix='collect') as pool:
            batches=list(pool.map(collect,chosen))
        for page,batch in batches:
            report['candidates']+=batch['candidates'];report['failed_platforms']+=batch['failed_platforms']
            report['platforms'].extend([{**p,'page':page} for p in batch['platforms']])
        result['collection']=report
        with connect(settings.db_path) as c:
            c.execute('INSERT OR REPLACE INTO source_topics VALUES(?,?,?)',(query,json.dumps(selected),now()))
    lap('collect')
    import source_refresh
    result['source_refresh']=source_refresh.run(settings)
    lap('source_refresh')
    if result['source_refresh']['failed'] or result['source_refresh']['missing']:
        result['errors'].append({'step':'source_refresh','error':'部分平台報價未刷新'})
    instant=datetime.now(timezone.utc)
    with connect(settings.db_path) as c:
        candidates=[__import__('identity_data').enrich(c,r) for r in c.execute("SELECT p.*,s.fingerprint AS saved_fingerprint,s.retry_at FROM platform_candidates p LEFT JOIN source_checks s ON s.candidate_id=p.id ORDER BY (s.checked_at IS NOT NULL),CASE WHEN trim(lower(p.catalog_no)) NOT IN ('','none','未確認') THEN 0 ELSE 1 END,coalesce(s.checked_at,''),p.id")]
    if source_platform:
        candidates=[row for row in candidates if row['platform']==source_platform]
        result['source_platform']=source_platform
    due=[]
    for row in candidates:
        if not needs_check(row,instant):
            result['cached']+=1
        else:due.append(row)
    client=DiscogsClient(settings)
    refreshed=set()
    for row in due[:limit]:
        status='failed'
        try:
            matching.search(settings,row['id'],client=client)
            with connect(settings.db_path) as c:
                matches=json.loads(c.execute('SELECT results FROM version_searches WHERE candidate_id=?',(row['id'],)).fetchone()[0])
            admitted=[]
            for target in matches:
                target={**target,'title':target['title'].split(' - ',1)[-1]}
                if evidence(row,target):admitted.append(target)
            # At most ten search suggestions per source, each release fetched once per batch.
            for target in admitted:
                rid=target['release_id']
                if rid in refreshed:continue
                with connect(settings.db_path) as c:
                    latest=c.execute('SELECT captured_at FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(rid,)).fetchone()
                if not latest or instant-datetime.fromisoformat(latest[0])>timedelta(hours=6):
                    ingest.fetch_one(client,settings,rid);result['market_updated']+=1
                refreshed.add(rid)
            status='matched' if admitted else 'unmatched'
            result[status]+=1
        except Exception as exc:
            result['errors'].append({'step':'reverse_match','candidate_id':row['id'],'error':type(exc).__name__})
        with connect(settings.db_path) as c:
            delay=timedelta(hours=1) if status=='failed' else timedelta(days=7 if status=='unmatched' else 30)
            c.execute('INSERT OR REPLACE INTO source_checks VALUES(?,?,?,?,?)',(row['id'],fingerprint(row),status,now(),(instant+delay).isoformat()))
        result['checked']+=1
    lap('reverse_match')
    # Existing matches keep current demand/price without repeating version searches.
    with connect(settings.db_path) as c:
        stale_ids=[r[0] for r in c.execute('SELECT r.release_id FROM releases r LEFT JOIN snapshots s ON s.id=(SELECT id FROM snapshots WHERE release_id=r.release_id ORDER BY captured_at DESC LIMIT 1) ORDER BY coalesce(s.captured_at,\'\') LIMIT 20')]
    for rid in stale_ids:
        if rid in refreshed:continue
        with connect(settings.db_path) as c:latest=c.execute('SELECT captured_at FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(rid,)).fetchone()
        if latest and instant-datetime.fromisoformat(latest[0])<timedelta(hours=6):continue
        try:ingest.fetch_one(client,settings,rid);result['market_updated']+=1
        except Exception as exc:result['errors'].append({'step':'market','release_id':rid,'error':type(exc).__name__})
    lap('market')
    from fx import refresh_reference
    try:result['fx']=refresh_reference(settings)
    except Exception as exc:result['errors'].append({'step':'fx','error':type(exc).__name__})
    lap('fx')
    analyze.run(settings)
    lap('analyze')
    try:result['sheet_sync']=sheet_sync.sync(settings)
    except Exception as exc:result['errors'].append(__import__('sync_failure').report(exc))
    lap('sheet_sync')
    result['timings']=timings
    result['pending']=max(0,len(due)-result['checked'])
    result['failed']=len(result['errors'])+result.get('collection',{}).get('failed_platforms',0)
    return result
