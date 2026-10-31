"""Demand-first sourcing from the scarcity list: high Want, low Have -> platform search, one query per album."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from db import connect, now
import identity_data
import sourcing
import source_queue

PREFIX='demand_search:'
RECENT=timedelta(days=7)
# Rotten Blues search only filters one catalogue page, so an album query there finds almost nothing.
PLATFORMS=['yahoo_tw','yahoo_jp','ruten','tower','rakuten','ebay']

def album_key(artist,title):
    text=unicodedata.normalize('NFKC',f'{artist or ""}|{title or ""}').casefold()
    return re.sub(r'\s+',' ',text).strip()

def scarcity(settings,min_want=None,min_ratio=None):
    """Albums whose tracked versions pass the Want and Want/Have floors, most promising first."""
    min_want=settings.scan_min_want if min_want is None else min_want
    min_ratio=settings.demand_min_ratio if min_ratio is None else min_ratio
    albums={}
    with connect(settings.db_path) as c:
        rows=c.execute('''SELECT r.release_id,r.artist,r.title,s.want,s.have,s.num_for_sale FROM releases r
            JOIN snapshots s ON s.id=(SELECT id FROM snapshots WHERE release_id=r.release_id ORDER BY captured_at DESC LIMIT 1)''').fetchall()
    for r in rows:
        if r['want'] is None or r['have'] is None or r['want']<min_want:continue
        if r['num_for_sale'] is not None and r['num_for_sale']>=settings.demand_max_for_sale:continue
        ratio=r['want']/max(r['have'],1)
        if ratio<min_ratio:continue
        key=album_key(r['artist'],r['title'])
        album=albums.setdefault(key,{'key':key,'artist':r['artist'],'title':r['title'],'release_ids':[],'ratio':0,'want':0,'unsold':False})
        album['release_ids'].append(r['release_id'])
        album['ratio']=max(album['ratio'],ratio);album['want']=max(album['want'],r['want'])
        album['unsold']=album['unsold'] or not r['num_for_sale']
    # Nobody selling on Discogs first, then the scarcest version, then the largest demand.
    return sorted(albums.values(),key=lambda a:(not a['unsold'],-a['ratio'],-a['want'],a['key']))

def _meta_key(key):
    return PREFIX+hashlib.sha256(key.encode()).hexdigest()[:16]

def run(settings,limit=None,selected=None,instant=None):
    limit=settings.demand_albums if limit is None else limit
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=500:raise ValueError('每次找貨 1 至 500 張專輯')
    selected=selected or PLATFORMS
    instant=instant or datetime.now(timezone.utc)
    source_queue.init(settings)
    result={'albums':0,'versions':0,'eligible_albums':0,'skipped_recent':0,'candidates':0,'linked':0,'failed_platforms':0,'errors':[]}
    albums=scarcity(settings);result['eligible_albums']=len(albums)
    for album in albums:
        if result['albums']>=limit:break
        meta=_meta_key(album['key'])
        with connect(settings.db_path) as c:
            last=c.execute('SELECT value FROM meta WHERE key=?',(meta,)).fetchone()
        try:
            if last and instant-datetime.fromisoformat(json.loads(last[0])['at'])<RECENT:
                result['skipped_recent']+=1;continue
        except (ValueError,KeyError,TypeError):pass
        query=f"{album['artist']} {album['title']}".strip()[:120]
        try:
            found=sourcing.find_many(settings,album['release_ids'],selected,query)
        except Exception as exc:
            result['errors'].append({'step':'demand_search','album':query[:80],'error':type(exc).__name__});continue
        result['albums']+=1;result['versions']+=len(album['release_ids'])
        result['candidates']+=found['candidates'];result['linked']+=found['possible_matches'];result['failed_platforms']+=found['failed_platforms']
        ids=found.get('returned_ids',[])
        with connect(settings.db_path) as c:
            linked={r[0] for r in c.execute(f"SELECT candidate_id FROM version_searches WHERE candidate_id IN ({','.join('?'*len(ids))})",ids)} if ids else set()
            # This album search already linked what it could; keep new items out of the reverse-match queue for 30 days.
            # Items the reverse queue checked before keep their own status.
            for cid in ids:
                # Same enriched identity the reverse queue fingerprints, or the item would look changed and be due again.
                row=identity_data.enrich(c,c.execute('SELECT * FROM platform_candidates WHERE id=?',(cid,)).fetchone())
                c.execute('INSERT OR IGNORE INTO source_checks VALUES(?,?,?,?,?)',(cid,source_queue.fingerprint(row),'matched' if cid in linked else 'unmatched',now(),(instant+timedelta(days=30)).isoformat()))
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(meta,json.dumps({'at':instant.isoformat(),'query':query},ensure_ascii=False)))
    result['failed']=len(result['errors'])+result['failed_platforms']
    return result
