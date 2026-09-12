"""Bounded own-inventory reads. Complete snapshots only; no marketplace writes."""
import json,re
from urllib.parse import quote
from db import connect,now
from discogs_client import DiscogsClient

KEY='discogs_inventory_snapshot'
PENDING='discogs_inventory_pending'

def state(settings):
 with connect(settings.db_path) as c:
  saved=c.execute('SELECT value FROM meta WHERE key=?',(KEY,)).fetchone()
  pending=c.execute('SELECT value FROM meta WHERE key=?',(PENDING,)).fetchone()
 return {'supported':True,'snapshot':json.loads(saved[0]) if saved else None,'next_page':json.loads(pending[0])['next_page'] if pending else 1}

def positive(value):
 if type(value) is not int or value<1:raise ValueError('Discogs 刊登資料格式無效')
 return value

def run(settings,client=None):
 client=client or DiscogsClient(settings)
 identity=client.get('/oauth/identity');username=identity.get('username')
 if not isinstance(username,str) or not username or len(username)>100:raise ValueError('無法確認 Discogs 帳號')
 with connect(settings.db_path) as c:
  pending=c.execute('SELECT value FROM meta WHERE key=?',(PENDING,)).fetchone()
  saved=c.execute('SELECT value FROM meta WHERE key=?',(KEY,)).fetchone()
 progress=json.loads(pending[0]) if pending else {'username':username,'next_page':1,'rows':[]}
 if progress['username']!=username or saved and json.loads(saved[0])['username']!=username:raise ValueError('Discogs 帳號與既有同步不同，請先核對帳號')
 page=progress['next_page']
 result=client.get('/users/'+quote(username,safe='')+'/inventory',{'page':page,'per_page':100})
 pagination=result.get('pagination');items=result.get('listings')
 if not isinstance(pagination,dict) or not isinstance(items,list):raise ValueError('Discogs 庫存格式改變，保留既有快照')
 pages=pagination.get('pages');total=pagination.get('items')
 if type(pages) is not int or not 0<=pages<=100 or type(total) is not int or total<0 or pagination.get('page')!=page or len(items)>100:raise ValueError('Discogs 分頁無效或超過 100 頁，保留既有快照')
 if page>1 and (pages!=progress['pages'] or total!=progress['total']):raise ValueError('庫存分頁數量已變動，請重設讀取進度')
 rows=[]
 for item in items:
  if not isinstance(item,dict) or not isinstance(item.get('release'),dict):raise ValueError('Discogs 刊登格式無效')
  status=item.get('status');external=item.get('external_id','')
  if not isinstance(status,str) or not status or not isinstance(external,str):raise ValueError('Discogs 刊登狀態無效')
  rows.append({'listing_id':positive(item.get('id')),'release_id':positive(item['release'].get('id')),'status':status[:80],'external_id':external[:150]})
 rows=progress['rows']+rows
 if len({r['listing_id'] for r in rows})!=len(rows):raise ValueError('庫存分頁有重複刊登，請重設讀取進度')
 complete=page>=pages
 if complete and len(rows)!=total:raise ValueError('庫存數量不完整，保留既有快照')
 if not complete and not items:raise ValueError('庫存出現空白中間頁，保留既有快照')
 with connect(settings.db_path) as c:
  if complete:
   # Link only exact known listing IDs or exported draft identifiers, never album names.
   linked=0
   for row in rows:
    known=c.execute('SELECT 1 FROM published_listings WHERE listing_id=? AND release_id=?',(str(row['listing_id']),row['release_id'])).fetchone()
    row['linked']=bool(known)
    match=re.fullmatch(r'simples-(\d+)-release-(\d+)',row['external_id'])
    if not known and match and int(match[2])==row['release_id']:
     draft=c.execute('SELECT * FROM listing_drafts WHERE id=? AND release_id=?',(int(match[1]),row['release_id'])).fetchone()
     exported=any(any(x.get('id')==int(match[1]) and x.get('release_id')==row['release_id'] for x in json.loads(e[0])) for e in c.execute('SELECT items FROM listing_exports WHERE generated_at>=?',(draft['created_at'],))) if draft else False
     if draft and draft['source_url'] and exported:
      row['linked']=True
      # Keep publishing history even when later sold/unlisted; do not infer absence.
      if row['status']=='For Sale':
       existing=c.execute('SELECT listing_id FROM published_listings WHERE source_url=? AND release_id=?',(draft['source_url'],row['release_id'])).fetchone()
       if existing and existing[0]!=str(row['listing_id']):row['linked']=False
       elif c.execute('SELECT 1 FROM published_listings WHERE listing_id=?',(str(row['listing_id']),)).fetchone():row['linked']=False
       else:c.execute('INSERT OR IGNORE INTO published_listings VALUES(?,?,?,?)',(draft['source_url'],row['release_id'],str(row['listing_id']),now()))
    linked+=int(row['linked'])
   snapshot={'username':username,'captured_at':now(),'rows':rows,'linked':linked,'total':len(rows)}
   c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(KEY,json.dumps(snapshot)))
   c.execute('DELETE FROM meta WHERE key=?',(PENDING,))
  else:
   c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(PENDING,json.dumps({'username':username,'next_page':page+1,'pages':pages,'total':total,'rows':rows})))
 return {'inventory_sync':True,'complete':complete,'received':len(rows),'next_page':1 if complete else page+1,'failed':0}
