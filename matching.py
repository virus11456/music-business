"""Discogs version suggestions. Catalog matches are evidence, never confirmation."""
import json
import re
import unicodedata
from db import connect,now
from discogs_client import DiscogsClient,APIError

SCHEMA='''CREATE TABLE IF NOT EXISTS version_searches (
 candidate_id INTEGER PRIMARY KEY REFERENCES platform_candidates(id),
 query TEXT NOT NULL, results TEXT NOT NULL, searched_at TEXT NOT NULL);'''
def init(settings):
 with connect(settings.db_path) as c:c.executescript(SCHEMA)
def normalized(value):
 return re.sub(r'[^\w]','',unicodedata.normalize('NFKC',str(value)).casefold())
def media(value):
 value=str(value).upper()
 if 'CD' in value:return 'CD'
 if any(x in value for x in ['CASSETTE','カセット','卡帶']):return 'Cassette'
 if any(x in value for x in ['VINYL','LP','黑膠','アナログ']):return 'Vinyl'
 return None

# Only remove explicit sales boilerplate; never guess translated album names.
def search_title(value):
 text=unicodedata.normalize('NFKC',str(value))
 text=re.sub(r'[<【\[](?:快速出貨|實在賣場|現貨|免運|促銷)[>】\]]',' ',text)
 text=re.sub(r'滿[額额][免冕]運|可?開發票|可?开发票|快速出貨|快速出货|官方正版|關芳正版',' ',text)
 return re.sub(r'\s+',' ',text).strip()[:160]

def search(settings,candidate_id,query=None,client=None):
 with connect(settings.db_path) as c:
  row=c.execute('SELECT * FROM platform_candidates WHERE id=?',(candidate_id,)).fetchone()
 if not row:raise ValueError('找不到來源商品')
 from source_match import source_catalog
 catalog=source_catalog(row)
 params={'type':'release','per_page':10,'page':1}
 if query:
  if not isinstance(query,str) or not 1<=len(query.strip())<=160:raise ValueError('搜尋詞最多 160 字')
  params['q']=query.strip()
 elif catalog:
  params['catno']=catalog
  if row['artist']:params['artist']=row['artist']
 else:params['q']=search_title(row['title']) or row['title'][:160]
 # Share the strict title/metadata rule with comparison admission.
 from source_match import identified_format,MERCH
 fmt=identified_format(row['format'],row['title'])
 if fmt:params['format']=fmt
 if MERCH.search(row['title']):
  params['skip_reason']='明確周邊商品，不查唱片版本'
  response={'results':[]}
 else:response=(client or DiscogsClient(settings)).get('/database/search',params)
 if not isinstance(response.get('results'),list):raise APIError('Discogs 搜尋結構不符')
 results=[]
 for r in response['results'][:10]:
  rid=r.get('id')
  if r.get('type')!='release' or isinstance(rid,bool) or not isinstance(rid,int) or rid<=0:continue
  cat=str(r.get('catno',''))
  formats=r.get('format',[])
  if not isinstance(formats,list):formats=[]
  evidence=[]
  if catalog and normalized(cat)==normalized(catalog):evidence.append('規格品番一致，仍需核對壓片')
  if fmt and fmt in formats:evidence.append('格式一致')
  results.append({'release_id':rid,'title':str(r.get('title',''))[:500],'country':str(r.get('country','未提供')),
                  'year':str(r.get('year','未提供')),'format':', '.join(map(str,formats)),
                  'catno':cat,'labels':', '.join(map(str,r.get('label',[]) or []))[:300],
                  'evidence':evidence or ['僅搜尋相關，版本未確認'], 'url':f'https://www.discogs.com/release/{rid}'})
 with connect(settings.db_path) as c:
  c.execute('INSERT OR REPLACE INTO version_searches VALUES(?,?,?,?)',(candidate_id,json.dumps(params,ensure_ascii=False),json.dumps(results,ensure_ascii=False),now()))
 return {'candidate_id':candidate_id,'suggestions':len(results)}

def state(settings):
 with connect(settings.db_path) as c:
  return {str(r['candidate_id']):{'query':json.loads(r['query']),'results':json.loads(r['results']),'searched_at':r['searched_at']} for r in c.execute('SELECT * FROM version_searches')}
