"""Demand-first search: one tracked Discogs release -> platform source candidates."""
import json
from db import connect,now
import platforms
from source_match import evidence as match_evidence

def find(settings,rid,selected,query=None):
 with connect(settings.db_path) as c:
  release=c.execute('SELECT * FROM releases WHERE release_id=?',(rid,)).fetchone()
 if not release:raise ValueError('請先加入 Discogs 版本')
 query=(query or f"{release['artist']} {release['title']}").strip()[:120]
 result=platforms.search(settings,query,selected)
 with connect(settings.db_path) as c:
  # Only this search's successfully returned candidates. Old search results are not linked anew.
  runs=c.execute('SELECT * FROM platform_runs WHERE query=? ORDER BY id DESC LIMIT ?',(query,len(selected))).fetchall()
  stamps={r['platform']:r['recorded_at'] for r in runs if r['status']=='完成'}
  linked=0
  for candidate in c.execute('SELECT * FROM platform_candidates WHERE query=?',(query,)).fetchall():
   if stamps.get(candidate['platform'])!=candidate['captured_at']:continue
   evidence=match_evidence(candidate,release)
   if not evidence:continue
   match={'release_id':rid,'title':release['artist']+' — '+release['title'],'country':release['country'],'year':str(release['year']),
          'format':release['format'],'catno':release['catno'],'labels':'','evidence':evidence,'url':f'https://www.discogs.com/release/{rid}'}
   existing=c.execute('SELECT results FROM version_searches WHERE candidate_id=?',(candidate['id'],)).fetchone()
   suggestions=json.loads(existing[0]) if existing else []
   suggestions=[r for r in suggestions if r['release_id']!=rid]+[match]
   c.execute('INSERT OR REPLACE INTO version_searches VALUES(?,?,?,?)',(candidate['id'],json.dumps({'release_id':rid,'q':query}),json.dumps(suggestions,ensure_ascii=False),now()));linked+=1
 result['possible_matches']=linked
 return result
