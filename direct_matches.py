"""Cached local cross-matching of already fetched sources and Discogs releases."""
import hashlib,json,re
from matching import normalized
from source_match import evidence,source_catalog

def pairs(c,sources,targets):
    source_rows=sorted(([s['id'],s['title'],s['artist'],s['format'],s['catalog_no'],__import__('identity_data').source_codes(s),s.get('labels','')] for s in sources),key=lambda r:r[0])
    target_rows=sorted(([r['release_id'],r['title'],r['artist'],r['format'],r['catno'],r.get('labels',''),r.get('barcodes',[])] for r in targets),key=lambda r:r[0])
    signature=hashlib.sha256(json.dumps([source_rows,target_rows],ensure_ascii=False).encode()).hexdigest()
    cached=c.execute("SELECT value FROM meta WHERE key='direct_matches_v4'").fetchone()
    if cached:
        try:
            data=json.loads(cached[0])
            if data['signature']==signature:return data['pairs']
        except (ValueError,KeyError,TypeError):pass
    result=compute(sources,targets)
    c.execute("INSERT OR REPLACE INTO meta VALUES('direct_matches_v4',?)",(json.dumps({'signature':signature,'pairs':result},ensure_ascii=False),))
    return result

def compute(sources,targets):
    """Same pairs and order as checking every source against every target, without the full cross product.

    A pair can only pass on a shared catalogue number, a shared barcode or the artist name appearing in the
    source text, so each source only visits the targets indexed under those keys."""
    from identity_data import source_codes
    prepared=[];by_catalog={};by_barcode={};by_artist={}
    for index,target in enumerate(targets):
        catalogs=[normalized(x) for x in target['catno'].split(',') if normalized(x) not in ('','none','na','未確認')]
        # A release without an artist cannot match by artist name (the old per-pair loop raised here instead).
        artist=normalized(re.sub(r'\s+\(\d+\)$','',target['artist'] or ''))
        codes=set(target.get('barcodes',[]))
        prepared.append((target,catalogs,artist,codes))
        for catalog in set(catalogs):by_catalog.setdefault(catalog,[]).append(index)
        for code in codes:by_barcode.setdefault(code,[]).append(index)
        if len(artist)>=2:by_artist.setdefault(artist,[]).append(index)
    result=[]
    for source in sources:
        catalog=normalized(source_catalog(source))
        known_catalog=catalog not in ('','none','na','未確認')
        text=normalized(source['artist']+' '+source['title'])
        codes=set(source_codes(source))
        reach=set(by_catalog.get(catalog,[])) if known_catalog else set()
        for code in codes:reach.update(by_barcode.get(code,[]))
        for artist,indexes in by_artist.items():
            if artist in text:reach.update(indexes)
        for index in sorted(reach):
            target,catalogs,artist,target_codes=prepared[index]
            catalog_match=known_catalog and catalog in catalogs
            if known_catalog and catalogs and not catalog_match:continue
            barcode_match=bool(codes&target_codes)
            if not catalog_match and not barcode_match and (len(artist)<2 or artist not in text):continue
            reasons=evidence(source,target)
            if reasons:result.append([source['id'],target['release_id'],reasons+['已抓取資料直接交叉比對']])
    return result
