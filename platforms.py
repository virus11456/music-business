"""Bounded public catalog searches. No seller filters, cookies, bidding or purchases."""
import json
import re
import time
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from db import connect, now

CATALOG=[
 {'id':'yahoo_tw','name':'Yahoo 台灣拍賣','url':'https://tw.bid.yahoo.com/','supported':True},
 {'id':'yahoo_jp','name':'Yahoo 日本拍賣','url':'https://auctions.yahoo.co.jp/','supported':True},
 {'id':'tower','name':'Tower Records 日本','url':'https://tower.jp/','supported':True},
 {'id':'ruten','name':'露天市集','url':'https://www.ruten.com.tw/','supported':True},
 {'id':'rottenblues','name':'Rotten Blues 爛調唱片','url':'https://www.rottenblues.com/','supported':True},
 {'id':'mercari','name':'Mercari 日本','url':'https://jp.mercari.com/','supported':False},
 {'id':'rakuten','name':'樂天市場日本','url':'https://www.rakuten.co.jp/','supported':True},
 {'id':'ebay','name':'eBay','url':'https://www.ebay.com/','supported':True},
 {'id':'diskunion','name':'Disk Union 專業唱片通路','url':'https://diskunion.net/','supported':False},
 {'id':'hmv','name':'HMV 日本中古唱片','url':'https://www.hmv.co.jp/used/','supported':False},
 {'id':'recordcity','name':'Record City 專業唱片通路','url':'https://www.recordcity.jp/en/','supported':False},
]
SCHEMA='''CREATE TABLE IF NOT EXISTS platform_candidates (
 id INTEGER PRIMARY KEY, platform TEXT NOT NULL, external_id TEXT NOT NULL,
 query TEXT NOT NULL, title TEXT NOT NULL, artist TEXT NOT NULL, format TEXT NOT NULL,
 catalog_no TEXT NOT NULL, price TEXT, currency TEXT NOT NULL, price_kind TEXT NOT NULL,
 availability TEXT NOT NULL, source_url TEXT NOT NULL, captured_at TEXT NOT NULL,
 UNIQUE(platform,external_id));
 CREATE TABLE IF NOT EXISTS platform_runs (
 id INTEGER PRIMARY KEY, platform TEXT NOT NULL, query TEXT NOT NULL,
 count INTEGER NOT NULL, status TEXT NOT NULL, recorded_at TEXT NOT NULL);
'''
def init(settings):
 with connect(settings.db_path) as c:c.executescript(SCHEMA)

def state(settings):
 with connect(settings.db_path) as c:
  return {'catalog':CATALOG,'candidates':[dict(r) for r in c.execute('SELECT * FROM platform_candidates ORDER BY captured_at DESC,id DESC LIMIT 200')],
          'runs':[dict(r) for r in c.execute('SELECT * FROM platform_runs ORDER BY id DESC LIMIT 15')]}

class Node:
 def __init__(self,tag='',attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[]
 def text(self):return ' '.join(x.text() if isinstance(x,Node) else x for x in self.children)
 def find(self,tag=None,cls=None):
  result=[]
  for n in self.children:
   if isinstance(n,Node):
    if (not tag or n.tag==tag) and (not cls or cls in n.attrs.get('class','').split()):result.append(n)
    result.extend(n.find(tag,cls))
  return result
class Tree(HTMLParser):
 def __init__(self,html):
  super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root];self.feed(html)
 def handle_starttag(self,tag,attrs):
  n=Node(tag,attrs);self.stack[-1].children.append(n)
  if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.stack.append(n)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==tag:del self.stack[i:];break
 def handle_data(self,data):self.stack[-1].children.append(data)

def price(value):
 try:
  d=Decimal(str(value).replace(',','').strip())
  return str(d) if d.is_finite() and d>0 else None
 except InvalidOperation:return None

def candidate(platform,eid,title,amount,kind='listed',availability='未確認',artist='',fmt='未確認',catalog=''):
 urls={'yahoo_tw':'https://tw.bid.yahoo.com/item/','yahoo_jp':'https://auctions.yahoo.co.jp/jp/auction/','tower':'https://tower.jp/item/','ruten':'https://www.ruten.com.tw/item/'}
 if not re.fullmatch(r'[A-Za-z0-9]+',str(eid)):raise ValueError('商品編號格式改變')
 return dict(platform=platform,external_id=str(eid),title=str(title)[:600],artist=artist[:300],format=fmt[:100],catalog_no=catalog[:100],price=price(amount),currency='TWD' if platform in ('yahoo_tw','ruten') else 'JPY',price_kind=kind,availability=availability,source_url=urls[platform]+str(eid))

def parse_yahoo_tw(html):
 root=Tree(html).root
 script=next((n for n in root.find('script') if n.attrs.get('id')=='isoredux-data'),None)
 if not script:raise ValueError('搜尋頁結構改變，請改用來源連結')
 hits=json.loads(script.text())['search']['ecsearch']['hits']
 out=[]
 for h in hits:
  cc=h.get('pres_data',{}).get('currency')
  if cc!='TWD':continue
  lo,hi=price(h.get('ec_min_price')),price(h.get('ec_max_price'))
  kind='range' if lo and hi and Decimal(lo)!=Decimal(hi) else 'listed'
  out.append(candidate('yahoo_tw',h['ec_productid'],h['ec_title'],h.get('ec_price'),kind))
 return out

def parse_yahoo_jp(html):
 root=Tree(html).root;cards=root.find('li','Product');out=[]
 if not cards and not any(t in html for t in ('一致する商品はありません','見つかりません')):raise ValueError('搜尋頁結構改變')
 for card in cards:
  a=next((a for a in card.find('a') if a.attrs.get('data-auction-id')),None)
  if not a:continue
  out.append(candidate('yahoo_jp',a.attrs['data-auction-id'],a.attrs.get('data-auction-title',''),a.attrs.get('data-auction-price'),'current_bid','拍賣中／需確認結標'))
 return out

def parse_tower(html):
 root=Tree(html).root;cards=root.find('div','TOL-item-search-result-PC-result-list-display-item');out=[]
 if not cards and tower_pages(html)!=0 and not any(t in html for t in ('該当する商品がありません','検索結果 0')):raise ValueError('搜尋頁結構改變')
 for card in cards:
  formats=card.find('span','result-display-contents-category-text');fmt=formats[0].text().strip() if formats else ''
  if not re.search(r'CD|SACD|LP|7\"|12\"|10\"|カセット|Cassette|アナログ',fmt,re.I):continue
  a=next((a for a in card.find('a','tr-item-block') if re.fullmatch(r'https://tower.jp/item/\d+',a.attrs.get('href',''))),None)
  if not a:continue
  titles=card.find('div','tr-item-block-info-item-name');title_links=titles[0].find('a') if titles else []
  artists=card.find('span','artist-link');p=card.find('span','is-text-amount')
  amounts=[re.search(r'[\d,]+',n.text()) for n in p];amounts=[m[0] for m in amounts if m]
  text=card.text();status=next((s for s in ('現在オンラインショップ取扱なし','予約受付中','お取り寄せ','在庫わずか','在庫あり') if s in text),'未確認')
  cat=re.search(r'規格品番：\s*([^|]+)',text)
  out.append(candidate('tower',a.attrs['href'].rsplit('/',1)[-1],title_links[0].text().strip() if title_links else '',amounts[-1] if amounts else None,'listed',status,artists[0].text().strip() if artists else '',fmt,cat[1].strip() if cat else ''))
 return out

def tower_pages(html):
 # Read the product pager, not the separate artist-name modal's pager.
 match=re.search(r'querySelector\([\"\']\.common-pagination[\"\']\);\s*const totalPages = Math\.ceil\((\d+)\s*/\s*(\d+)\)',html)
 if not match:return None
 total,size=map(int,match.groups())
 if size<=0:raise ValueError('Tower 分頁資料無效')
 return (total+size-1)//size

def parse_ruten(raw):
 items=json.loads(raw)
 if not isinstance(items,list):raise ValueError('露天商品資料結構改變')
 out=[]
 for item in items:
  if item.get('Currency')!='TWD':continue
  prices=item.get('PriceRange',[])
  if len(prices)!=2:raise ValueError('露天價格資料結構改變')
  kind='current_bid' if item.get('SaleType')!='buy' else 'range' if prices[0]!=prices[1] else 'listed'
  status={1:'來源標示有庫存',2:'預購'}.get(item.get('StockStatus'),'未確認')
  out.append(candidate('ruten',item['ProdId'],item['ProdName'],prices[0],kind,status))
 return out

def parse_rottenblues(raw):
 return __import__('rottenblues').parse_catalog(raw)[0]

def parse_rakuten(raw):
 return __import__('api_sources').parse('rakuten',raw)[0]

def parse_ebay(raw):
 return __import__('api_sources').parse('ebay',raw)[0]

PARSERS={'rottenblues':parse_rottenblues,'yahoo_tw':parse_yahoo_tw,'yahoo_jp':parse_yahoo_jp,'tower':parse_tower,'ruten':parse_ruten,'rakuten':parse_rakuten,'ebay':parse_ebay}
def search_url(platform,query,page=1):
 q=quote(query,safe='')
 if not isinstance(page,int) or not 1<=page<=1000:raise ValueError('搜尋頁數無效')
 return {'rottenblues':f'https://www.rottenblues.com/products.json?limit=40&page={page}',
         'yahoo_tw':f'https://tw.bid.yahoo.com/search/auction/product?p={q}'+(f'&pg={page}' if page>1 else ''),
         'yahoo_jp':f'https://auctions.yahoo.co.jp/search/search?p={q}&ei=utf-8'+(f'&b={(page-1)*50+1}&n=50' if page>1 else ''),
         'tower':f'https://tower.jp/search/item/{q}'+(f'?page={page}' if page>1 else ''),
         'ruten':f'https://rtapi.ruten.com.tw/api/search/v4/index.php/core/prod?q={q}&type=direct&sort=rnk%2Fdc&limit=40&offset={(page-1)*40+1}'}[platform]

def fetch(url):
 # Official APIs pass a prepared Request (with their own auth headers); sites pass a URL.
 req=url if isinstance(url,Request) else Request(url,headers={'User-Agent':'SimplesRecordResearch/0.1','Accept':'text/html'})
 url=req.full_url
 opener=urlopen
 if urlsplit(url).hostname=='tw.bid.yahoo.com':
  from yahoo_transport import open_yahoo
  opener=open_yahoo
 with opener(req,timeout=25) as response:
  if urlsplit(response.url).hostname!=urlsplit(url).hostname:raise ValueError('來源重新導向，請人工確認')
  raw=response.read(5_000_001)
  if len(raw)>5_000_000:raise ValueError('搜尋頁過大')
  return raw.decode('utf-8')

def search(settings,query,selected,fetcher=fetch,page=1,full_page=False):
 if not isinstance(query,str) or not 1<=len(query.strip())<=120:raise ValueError('請填搜尋詞，最多 120 字')
 if not isinstance(selected,list) or not selected or len(selected)>len(PARSERS) or any(p not in PARSERS for p in selected):raise ValueError('請選擇已支援的平台')
 query=query.strip();total=0;failed=0;reports=[]
 for platform in dict.fromkeys(selected):
  try:
   with connect(settings.db_path) as c:
    previous=c.execute('SELECT recorded_at FROM platform_runs WHERE platform=? ORDER BY id DESC LIMIT 1',(platform,)).fetchone()
   if previous:
    from datetime import datetime,timezone
    elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(previous[0])).total_seconds()
    if elapsed<3:time.sleep(3-elapsed)
   api=platform in __import__('api_sources').PLATFORMS
   raw=fetcher(__import__('api_sources').request(settings,platform,query,page) if api else search_url(platform,query,page))
   if platform=='ruten':
    hits=json.loads(raw)['Rows']
    ids=[str(h['Id']) for h in hits[:40]]
    if any(not re.fullmatch(r'[0-9]+',i) for i in ids):raise ValueError('露天商品編號格式改變')
    if ids:
     time.sleep(3)
     raw=fetcher('https://rtapi.ruten.com.tw/api/prod/v3/index.php/prod?id='+','.join(ids))
    else:raw='[]'
   more=None
   if platform=='rottenblues':rows,more=__import__('rottenblues').parse_catalog(raw,query)
   elif api:rows,more=__import__('api_sources').parse(platform,raw,page)
   else:rows=PARSERS[platform](raw)[:50 if platform=='yahoo_jp' and (page>1 or full_page) else 40]
   total_pages=tower_pages(raw) if platform=='tower' and full_page else None
   if platform=='tower' and full_page and total_pages is None:raise ValueError('Tower 分頁結構改變，停止推進頁碼')
   stamp=now()
   with connect(settings.db_path) as c:
    for row in rows:
     row.update(query=query,captured_at=stamp)
     identity={k:row.pop(k) for k in ('barcodes','labels') if k in row}
     cols=list(row)
     c.execute(f"INSERT INTO platform_candidates ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(platform,external_id) DO UPDATE SET "+','.join(f'{k}=excluded.{k}' for k in cols if k not in ('platform','external_id')),list(row.values()))
     if identity:
      saved=c.execute('SELECT * FROM platform_candidates WHERE platform=? AND external_id=?',(platform,row['external_id'])).fetchone()
      __import__('identity_data').save_source(c,saved,identity)
    c.execute('INSERT INTO platform_runs(platform,query,count,status,recorded_at) VALUES(?,?,?,?,?)',(platform,query,len(rows),'完成' if rows else '沒有符合商品',stamp))
   total+=len(rows)
   report={'platform':platform,'count':len(rows),'status':'success' if rows else 'empty'}
   if more is not None:report.update(has_more=more,**({} if api else {'search_scope':'catalog_page'}))
   if total_pages is not None:report.update(has_more=page<total_pages,total_pages=total_pages)
   reports.append(report)
  except Exception as e:
   status=f'來源拒絕連線（HTTP {e.code}），請人工開啟平台' if isinstance(e,HTTPError) else '讀取失敗或頁面結構改變；請人工開啟平台'
   with connect(settings.db_path) as c:c.execute('INSERT INTO platform_runs(platform,query,count,status,recorded_at) VALUES(?,?,?,?,?)',(platform,query,0,status,now()))
   failed+=1
   reports.append({'platform':platform,'count':0,'status':'failed'})
 return {'candidates':total,'failed_platforms':failed,'platforms':reports}
