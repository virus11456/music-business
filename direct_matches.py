"""Cached local cross-matching of already fetched sources and Discogs releases."""
import hashlib,json,re
from matching import normalized
from source_match import evidence

def pairs(c,sources,targets):
    source_rows=sorted(([s['id'],s['title'],s['artist'],s['format'],s['catalog_no']] for s in sources),key=lambda r:r[0])
    target_rows=sorted(([r['release_id'],r['title'],r['artist'],r['format'],r['catno'],r.get('labels','')] for r in targets),key=lambda r:r[0])
    signature=hashlib.sha256(json.dumps([source_rows,target_rows],ensure_ascii=False).encode()).hexdigest()
    cached=c.execute("SELECT value FROM meta WHERE key='direct_matches_v2'").fetchone()
    if cached:
        try:
            data=json.loads(cached[0])
            if data['signature']==signature:return data['pairs']
        except (ValueError,KeyError,TypeError):pass
    result=[]
    for source in sources:
        catalog=normalized(source['catalog_no'])
        known_catalog=catalog not in ('','none','na','未確認')
        text=normalized(source['artist']+' '+source['title'])
        for target in targets:
            catalogs=[normalized(x) for x in target['catno'].split(',') if normalized(x) not in ('','none','na','未確認')]
            catalog_match=known_catalog and catalog in catalogs
            if known_catalog and catalogs and not catalog_match:continue
            artist=normalized(re.sub(r'\s+\(\d+\)$','',target['artist']))
            if not catalog_match and (len(artist)<2 or artist not in text):continue
            reasons=evidence(source,target)
            if reasons:result.append([source['id'],target['release_id'],reasons+['已抓取資料直接交叉比對']])
    c.execute("INSERT OR REPLACE INTO meta VALUES('direct_matches_v2',?)",(json.dumps({'signature':signature,'pairs':result},ensure_ascii=False),))
    return result
