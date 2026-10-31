"""Demand-first search: one tracked Discogs release -> platform source candidates."""
import json
from db import connect,now
import platforms
from source_match import evidence as match_evidence

def find(settings,rid,selected,query=None):
 result=find_many(settings,[rid],selected,query)
 result.pop('returned_ids',None)
 return result

def find_many(settings,rids,selected,query=None):
 """One platform search, linked against every listed version (one album, many pressings)."""
 with connect(settings.db_path) as c:
  releases=[r for r in (c.execute('SELECT * FROM releases WHERE release_id=?',(rid,)).fetchone() for rid in dict.fromkeys(rids)) if r]
 if not releases:raise ValueError('請先加入 Discogs 版本')
 first=releases[0]
 query=(query or f"{first['artist']} {first['title']}").strip()[:120]
 result=platforms.search(settings,query,selected)
 with connect(settings.db_path) as c:
  # Only this search's successfully returned candidates. Old search results are not linked anew.
  runs=c.execute('SELECT * FROM platform_runs WHERE query=? ORDER BY id DESC LIMIT ?',(query,len(selected))).fetchall()
  stamps={r['platform']:r['recorded_at'] for r in runs if r['status']=='完成'}
  linked=0;returned=[]
  for candidate in c.execute('SELECT * FROM platform_candidates WHERE query=?',(query,)).fetchall():
   if stamps.get(candidate['platform'])!=candidate['captured_at']:continue
   returned.append(candidate['id'])
   existing=c.execute('SELECT results FROM version_searches WHERE candidate_id=?',(candidate['id'],)).fetchone()
   suggestions=json.loads(existing[0]) if existing else []
   matched=False
   for release in releases:
    rid=release['release_id']
    evidence=match_evidence(candidate,release)
    if not evidence:continue
    match={'release_id':rid,'title':release['artist']+' — '+release['title'],'country':release['country'],'year':str(release['year']),
           'format':release['format'],'catno':release['catno'],'labels':'','evidence':evidence,'url':f'https://www.discogs.com/release/{rid}'}
    suggestions=[r for r in suggestions if r['release_id']!=rid]+[match];matched=True;linked+=1
   if matched:
    c.execute('INSERT OR REPLACE INTO version_searches VALUES(?,?,?,?)',(candidate['id'],json.dumps({'release_id':first['release_id'],'q':query}),json.dumps(suggestions,ensure_ascii=False),now()))
 result['possible_matches']=linked
 result['returned_ids']=returned
 return result
