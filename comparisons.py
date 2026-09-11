"""Transparent source-to-release comparisons; potential matches never imply ownership."""
import json
from datetime import datetime,timezone
from decimal import Decimal
from db import connect
from fx import convert,business_day
from matching import media
from source_match import evidence as match_evidence,identified_format

def amount(v):return str(v.quantize(Decimal('.01'))) if v is not None else None
def stale(stamp):
 try:
  age=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()
  return age<0 or age>172800
 except (TypeError,ValueError):return True

def build(settings):
 rows=[]
 with connect(settings.db_path) as c:
  candidates={r['source_url']:dict(r) for r in c.execute('SELECT * FROM platform_candidates')}
  offers=[dict(r) for r in c.execute('SELECT o.*,r.title,r.artist FROM sourcing_offers o JOIN releases r USING(release_id) ORDER BY o.id DESC')]
  covered=set()
  for o in offers:
   source=candidates.get(o['source_url']);covered.add((o['source_url'],o['release_id']))
   rows.append(calculate(c,settings,o,source,True))
  if c.execute("SELECT 1 FROM sqlite_master WHERE name='version_searches'").fetchone():
   for search in c.execute('SELECT v.*,p.source_url FROM version_searches v JOIN platform_candidates p ON p.id=v.candidate_id'):
    source=candidates[search['source_url']]
    for r in json.loads(search['results']):
     target=c.execute('SELECT * FROM releases WHERE release_id=?',(r['release_id'],)).fetchone()
     if not target:
      target={'title':r['title'].split(' - ',1)[-1],'format':r.get('format',''),'catno':r.get('catno','')}
     target=dict(target)
     label=c.execute('SELECT value FROM meta WHERE key=?',(f"release_labels_{r['release_id']}",)).fetchone()
     target['labels']=label[0] if label else r.get('labels','')
     if not label and target['labels']:
      c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(f"release_labels_{r['release_id']}",target['labels']))
     reasons=match_evidence(source,target)
     excluded=c.execute('SELECT 1 FROM excluded_matches WHERE source_url=? AND release_id=?',(source['source_url'],r['release_id'])).fetchone()
     if not reasons and not excluded:continue
     r['evidence']=reasons
     if (source['source_url'],r['release_id']) in covered:continue
     o={'id':None,'release_id':r['release_id'],'title':r['title'],'artist':'','vendor':source['platform'],
        'source_url':source['source_url'],'version_confirmed':0,'owned_confirmed':0,'sale_price':None,'sale_currency':None,
        'amount':None,'currency':source['currency'],'media_cond':'未確認','sleeve_cond':'未確認','recorded_at':source['captured_at']}
     row=calculate(c,settings,o,source,False);row['evidence']=r['evidence'];rows.append(row)
  present={(r['source_url'],r['release_id']) for r in rows}
  import direct_matches
  targets={r['release_id']:dict(r) for r in c.execute('SELECT * FROM releases')}
  for rid,target in targets.items():
   label=c.execute('SELECT value FROM meta WHERE key=?',(f'release_labels_{rid}',)).fetchone()
   target['labels']=label[0] if label else ''
  sources_by_id={s['id']:s for s in candidates.values()}
  for sid,rid,reasons in direct_matches.pairs(c,list(candidates.values()),list(targets.values())):
   source=sources_by_id[sid];target=targets[rid]
   if (source['source_url'],rid) in present:continue
   o={'id':None,'release_id':rid,'title':target['title'],'artist':target['artist'],'vendor':source['platform'],
      'source_url':source['source_url'],'version_confirmed':0,'owned_confirmed':0,'sale_price':None,'sale_currency':None,
      'amount':None,'currency':source['currency'],'media_cond':'未確認','sleeve_cond':'未確認','recorded_at':source['captured_at']}
   row=calculate(c,settings,o,source,False);row['evidence']=reasons;rows.append(row)
   present.add((source['source_url'],rid))
  for excluded in c.execute('SELECT * FROM excluded_matches'):
   if (excluded['source_url'],excluded['release_id']) in present:continue
   source=candidates.get(excluded['source_url'])
   if not source:continue
   target=c.execute('SELECT * FROM releases WHERE release_id=?',(excluded['release_id'],)).fetchone()
   o={'id':None,'release_id':excluded['release_id'],'title':target['title'] if target else f"Discogs #{excluded['release_id']}",'artist':'','vendor':source['platform'],
      'source_url':source['source_url'],'version_confirmed':0,'owned_confirmed':0,'sale_price':None,'sale_currency':None,
      'amount':None,'currency':source['currency'],'media_cond':'未確認','sleeve_cond':'未確認','recorded_at':source['captured_at']}
   rows.append(calculate(c,settings,o,source,False))
 return rows

def calculate(c,s,o,source,confirmed_offer):
 release=c.execute('SELECT format,catno FROM releases WHERE release_id=?',(o['release_id'],)).fetchone()
 snapshot=c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(o['release_id'],)).fetchone()
 row={'key':f"offer-{o['id']}" if confirmed_offer else f"candidate-{source['id']}-{o['release_id']}",'offer':o if confirmed_offer else None,
      'candidate_id':source['id'] if source else None,'source_title':source['title'] if source else o['title'],
      'format':identified_format(release['format']) if release else None,'source_format':identified_format(source['format'],source['title']) if source else None,
      'catalog_no':release['catno'] if release else '', 'source_catalog_no':source['catalog_no'] if source else '',
      'release_id':o['release_id'],'release_title':o['title'],'vendor':o['vendor'],'source_url':o['source_url'],
      'source_at':source['captured_at'] if source else None,'cost_at':o['recorded_at'],
      'source_price':source['price'] if source else None,'source_currency':source['currency'] if source else o['currency'],
      'price_kind':source['price_kind'] if source else 'manual','availability':source['availability'] if source else '人工報價',
      'version_confirmed':bool(o['version_confirmed']),'has_market':bool(snapshot),'market_price':snapshot['lowest_price'] if snapshot else None,
      'market_currency':snapshot['currency'] if snapshot else None,'market_at':snapshot['captured_at'] if snapshot else None,
      'want':snapshot['want'] if snapshot else None,'have':snapshot['have'] if snapshot else None,
      'sale_basis':'人工預定售價' if o.get('sale_price') else 'Discogs 最低掛牌價（非成交價）',
      'sale_twd':None,'source_twd':None,'cost_twd':None,'spread_twd':None,'gross_twd':None,'gross_margin':None,
      'fees_twd':None,'net_twd':None,'net_margin':None,'ready':False,'issues':[]}
 label=c.execute('SELECT value FROM meta WHERE key=?',(f"release_labels_{o['release_id']}",)).fetchone()
 row['labels']=label[0] if label else ''
 row['excluded']=bool(c.execute('SELECT 1 FROM excluded_matches WHERE source_url=? AND release_id=?',(o['source_url'],o['release_id'])).fetchone())
 issues=row['issues']
 if row['excluded']:issues.append('已人工排除此配對')
 if row['format'] and row['source_format'] and row['format']!=row['source_format']:issues.append('來源與 Discogs 格式不一致')
 day=business_day()
 def twd(value,currency,label):
  if value is None or not currency:return None
  try:return convert(c,value,currency,day)[0]
  except ValueError:
   issues.append(label+'缺有效匯率');return None
 sale=twd(o.get('sale_price') or (snapshot['lowest_price'] if snapshot else None),o.get('sale_currency') if o.get('sale_price') else snapshot['currency'] if snapshot else None,'售價')
 sale_value=o.get('sale_price') or (snapshot['lowest_price'] if snapshot else None)
 sale_currency=o.get('sale_currency') if o.get('sale_price') else snapshot['currency'] if snapshot else None
 row['sale_usd']=None
 if sale_value is not None and sale_currency=='USD':row['sale_usd']=str(Decimal(str(sale_value)))
 elif sale is not None:
  try:row['sale_usd']=str(sale/convert(c,1,'USD',day)[0])
  except (ValueError,ArithmeticError):pass
 buy=twd(source['price'],source['currency'],'標價') if source else None
 cost=twd(o['amount'],o['currency'],'成本') if o['amount'] is not None else None
 row['cost_basis']='confirmed_total' if o['amount'] is not None else 'source_price'
 estimated_cost=cost if o['amount'] is not None else buy
 row.update(sale_twd=amount(sale),source_twd=amount(buy),cost_twd=amount(cost),spread_twd=amount(sale-buy) if sale is not None and buy is not None else None)
 if sale is not None and estimated_cost is not None and sale>0:
  gross=sale-estimated_cost;fees=sale*s.fee_pct+s.shipping+s.packing+s.reserve;net=gross-fees
  row.update(gross_twd=amount(gross),gross_margin=float(gross/sale),fees_twd=amount(fees),net_twd=amount(net),net_margin=float(net/sale))
 if not o['version_confirmed']:issues.append('待核對版本')
 if o['amount'] is None:issues.append('依来源標價估算，未含進貨運費與代購費')
 if not o.get('sale_price'):issues.append('待確認預定售價')
 if not snapshot or snapshot['lowest_price'] is None:issues.append('待抓 Discogs 行情')
 elif stale(snapshot['captured_at']):issues.append('行情超過兩天')
 if stale(o['recorded_at']):issues.append('報價超過兩天')
 if o['media_cond']=='未確認' or o['sleeve_cond']=='未確認':issues.append('待確認品相')
 if not o.get('owned_confirmed') and not o.get('supply_confirmed'):issues.append('待確認可採購庫存與出貨時間')
 if source and not o.get('owned_confirmed'):
  if source['price_kind']=='current_bid':issues.append('拍賣價格尚未確定')
  if source['availability'] in ('現在オンラインショップ取扱なし','予約受付中','お取り寄せ','預購'):issues.append('貨源無現貨或待調貨')
 if sale is None or sale<=0:issues.append('缺有效售價')
 if row['net_margin'] is not None and (Decimal(row['net_twd'])<=0 or row['net_margin']<s.min_margin):issues.append('未達淨利門檻')
 row['ready']=not issues and row['net_twd'] is not None
 row['status']='已人工排除' if row['excluded'] else '可建立上架草稿' if row['ready'] else '待補資料／確認' if issues else '待檢查'
 if not confirmed_offer and not row['excluded']:row['status']='已找到候選，待核對版本'
 listing=c.execute('SELECT listing_id,recorded_at FROM published_listings WHERE source_url=? AND release_id=?',(o['source_url'],o['release_id'])).fetchone()
 row['listing_status']='listed' if listing else 'unlisted'
 row['listing_id']=listing['listing_id'] if listing else None
 if listing:row['ready']=False;row['status']='已上架（人工登錄）'
 return row
