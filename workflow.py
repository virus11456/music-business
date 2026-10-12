"""Sourcing records and listing preparation; no external purchase or listing POST."""
import csv
import hashlib
import io
import json
import re
from urllib.parse import urlsplit
from datetime import datetime, timezone
from db import connect, now
from config import money
from fx import convert,business_day

SUBMISSION_PREFIX='listing_submission:'
GRADES=('Mint (M)','Near Mint (NM or M-)','Very Good Plus (VG+)','Very Good (VG)','Good Plus (G+)','Good (G)','Fair (F)','Poor (P)')
SCHEMA='''
CREATE TABLE IF NOT EXISTS published_listings (source_url TEXT NOT NULL,release_id INTEGER NOT NULL,listing_id TEXT UNIQUE NOT NULL,recorded_at TEXT NOT NULL,PRIMARY KEY(source_url,release_id));
CREATE TABLE IF NOT EXISTS listing_exports (id INTEGER PRIMARY KEY, generated_at TEXT NOT NULL, currency TEXT NOT NULL, items TEXT NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS excluded_matches (source_url TEXT NOT NULL, release_id INTEGER NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(source_url,release_id));
CREATE TABLE IF NOT EXISTS sourcing_offers (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 vendor TEXT NOT NULL, source_url TEXT NOT NULL, amount TEXT NOT NULL,
 currency TEXT NOT NULL, media_cond TEXT NOT NULL, sleeve_cond TEXT NOT NULL,
 version_confirmed INTEGER NOT NULL DEFAULT 0, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS listing_drafts (
 id INTEGER PRIMARY KEY, release_id INTEGER NOT NULL REFERENCES releases,
 media_cond TEXT NOT NULL, sleeve_cond TEXT NOT NULL, price TEXT NOT NULL,
 currency TEXT NOT NULL, note TEXT NOT NULL, description TEXT NOT NULL,
 version_confirmed INTEGER NOT NULL, owned_confirmed INTEGER NOT NULL,
 created_at TEXT NOT NULL);
'''

def init_workflow(settings):
    with connect(settings.db_path) as c:
        c.executescript(SCHEMA)
        columns={r[1] for r in c.execute('PRAGMA table_info(sourcing_offers)')}
        for name,definition in [('owned_confirmed','INTEGER NOT NULL DEFAULT 0'),('sale_price','TEXT'),('sale_currency','TEXT'),('supply_confirmed','INTEGER NOT NULL DEFAULT 0'),('dispatch_days','INTEGER')]:
            if name not in columns:c.execute(f'ALTER TABLE sourcing_offers ADD COLUMN {name} {definition}')

    with connect(settings.db_path) as c:
        columns={r[1] for r in c.execute('PRAGMA table_info(listing_drafts)')}
        for name,definition in [('supply_confirmed','INTEGER NOT NULL DEFAULT 0'),('dispatch_days','INTEGER'),('source_url',"TEXT NOT NULL DEFAULT ''"),('source_offer_id','INTEGER')]:
            if name not in columns:c.execute(f'ALTER TABLE listing_drafts ADD COLUMN {name} {definition}')

    with connect(settings.db_path) as c:
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_draft_per_offer ON listing_drafts(source_offer_id) WHERE source_offer_id IS NOT NULL')

def supply_details(data):
    confirmed=data.get('supply_confirmed')=='yes'
    days=int(data['dispatch_days']) if data.get('dispatch_days') else None
    if days is not None and not 1<=days<=365:raise ValueError('出貨天數須介於 1 至 365')
    if confirmed and (not days or not data.get('source_url')):raise ValueError('請填確認貨源連結與付款後出貨天數')
    return int(confirmed),days

def web_url(value):
    url=urlsplit(value.strip())
    if url.scheme not in ('https','http') or not url.netloc or url.username or url.password:
        raise ValueError('請填有效網站連結')
    return value.strip()

def sheet_id(value):
    match=re.fullmatch(r'https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)(?:/[^\s]*)?',value.strip())
    if not match:
        raise ValueError('請填 Google Sheets 試算表連結')
    return match[1]

def get_workflow(settings):
    with connect(settings.db_path) as c:
        config=c.execute("SELECT value FROM meta WHERE key='google_sheet_id'").fetchone()
        offers=[]
        for row in c.execute('SELECT o.*,r.title,r.artist,r.format FROM sourcing_offers o JOIN releases r USING(release_id) ORDER BY o.id DESC').fetchall():
            offer=dict(row)
            s=c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(row['release_id'],)).fetchone()
            offer.update(net_twd=None,margin=None,status='缺少行情')
            if s and s['lowest_price'] is not None and s['currency']:
                try:
                    day=business_day()
                    sale,_=convert(c,row['sale_price'] or s['lowest_price'],row['sale_currency'] if row['sale_price'] else s['currency'],day)
                    purchase,_=convert(c,row['amount'],row['currency'],day)
                    net=sale-purchase-sale*settings.fee_pct-settings.shipping-settings.packing-settings.reserve
                    offer.update(net_twd=str(net.quantize(money('.01'))),margin=float(net/sale) if sale>0 else None)
                    stale=(datetime.now(timezone.utc)-datetime.fromisoformat(s['captured_at'])).days>2
                    offer['status']='行情已過期' if stale else '待核對版本' if not row['version_confirmed'] else '待核對品相與售價' if net>0 else '暫無利潤'
                except ValueError:
                    offer['status']='缺少有效匯率'
            offers.append(offer)
        drafts=[dict(r) for r in c.execute('SELECT d.*,r.title,r.artist,r.format FROM listing_drafts d JOIN releases r USING(release_id) ORDER BY d.id DESC')]
        for draft in drafts:
            draft['listing_status']='listed' if c.execute('SELECT 1 FROM published_listings WHERE source_url=? AND release_id=?',(draft['source_url'],draft['release_id'])).fetchone() else 'unlisted'
            draft['export_issues']=draft_export_issues(c,draft)
            submission=submission_record(c,draft['id'])
            draft['submission']={k:v for k,v in submission.items() if k in ('status','listing_id','reason','requested_status','started_at','finished_at','attempts')} if submission is not None else None
            draft['profit_review']=draft_profit_review(c,settings,draft)
    return {'exports':export_history(settings),'offers':offers,'drafts':drafts,'sheet_url':f'https://docs.google.com/spreadsheets/d/{config[0]}/edit' if config else None,'grades':GRADES}

def save_offer(c,data,parse_id,parse_currency,required):
    media=str(data.get('media_cond','未確認'))
    sleeve=str(data.get('sleeve_cond','未確認'))
    if media not in GRADES+('未確認',) or sleeve not in GRADES+('未確認','Generic','No Cover','Not Graded'):
        raise ValueError('品相無效')
    sale=money(data['sale_price']) if data.get('sale_price') else None
    if sale is not None and sale<=0:raise ValueError('預定售價必須大於零')
    supply,days=supply_details(data)
    values=(parse_id(required(data,'release_id')),required(data,'vendor'),web_url(required(data,'source_url',1500)),
       str(money(required(data,'amount'))),parse_currency(required(data,'currency')),media,sleeve,
       int(data.get('version_confirmed')=='yes'),now(),int(data.get('owned_confirmed')=='yes'),
       str(sale) if sale is not None else None,parse_currency(required(data,'sale_currency')) if sale is not None else None,supply,days)
    if data.get('offer_id'):
        changed=c.execute('UPDATE sourcing_offers SET release_id=?,vendor=?,source_url=?,amount=?,currency=?,media_cond=?,sleeve_cond=?,version_confirmed=?,recorded_at=?,owned_confirmed=?,sale_price=?,sale_currency=?,supply_confirmed=?,dispatch_days=? WHERE id=?',values+(int(data['offer_id']),)).rowcount
        if not changed:raise ValueError('找不到報價')
    else:
        c.execute('INSERT INTO sourcing_offers(release_id,vendor,source_url,amount,currency,media_cond,sleeve_cond,version_confirmed,recorded_at,owned_confirmed,sale_price,sale_currency,supply_confirmed,dispatch_days) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',values)

def save_draft(c,data,parse_id,parse_currency,required):
    supply,days=supply_details(data)
    if data.get('version_confirmed')!='yes':
        raise ValueError('請確認版本正確')
    if data.get('owned_confirmed')!='yes' and not supply:
        raise ValueError('請確認持有商品，或確認可立即採購的庫存與出貨天數')
    media=required(data,'media_cond');sleeve=required(data,'sleeve_cond')
    if media not in GRADES or sleeve not in GRADES+('Generic','No Cover','Not Graded'):
        raise ValueError('請人工確認品相')
    price=money(required(data,'price'))
    if price<=0:
        raise ValueError('售價必須大於零')
    note=str(data.get('note','')).strip()[:500]
    description=f'Media: {media}. Sleeve: {sleeve}.'+(f' {note}' if note else '')
    rid=parse_id(required(data,'release_id'))
    offer_id=int(data['source_offer_id']) if data.get('source_offer_id') else None
    if offer_id is not None:
        offer=c.execute('SELECT * FROM sourcing_offers WHERE id=?',(offer_id,)).fetchone()
        if not offer or offer['release_id']!=rid:raise ValueError('草稿與來源報價版本不一致')
        if web_url(str(data.get('source_url','')))!=offer['source_url']:raise ValueError('草稿與來源報價連結不一致，請重新選取目前貨源')
    draft_id=int(data['draft_id']) if data.get('draft_id') else None
    if draft_id is not None:
        previous=c.execute('SELECT * FROM listing_drafts WHERE id=?',(draft_id,)).fetchone()
        if not previous:raise ValueError('草稿不存在')
        if previous['source_offer_id']!=offer_id:raise ValueError('不能更換草稿的來源報價')
    values=(rid,media,sleeve,str(price),parse_currency(required(data,'currency')),note,description,int(data.get('owned_confirmed')=='yes'),now(),supply,days,web_url(data['source_url']) if data.get('source_url') else '',offer_id)
    existing=c.execute('SELECT id FROM listing_drafts WHERE id=?',(draft_id,)).fetchone() if draft_id is not None else c.execute('SELECT id FROM listing_drafts WHERE source_offer_id=?',(offer_id,)).fetchone() if offer_id is not None else None
    if existing:
        c.execute('UPDATE listing_drafts SET release_id=?,media_cond=?,sleeve_cond=?,price=?,currency=?,note=?,description=?,owned_confirmed=?,created_at=?,supply_confirmed=?,dispatch_days=?,source_url=?,source_offer_id=? WHERE id=?',values+(existing['id'],))
    else:
        c.execute('INSERT INTO listing_drafts(release_id,media_cond,sleeve_cond,price,currency,note,description,version_confirmed,owned_confirmed,created_at,supply_confirmed,dispatch_days,source_url,source_offer_id) VALUES(?,?,?,?,?,?,?,1,?,?,?,?,?,?)',values)

def review_csv(settings):
    """Review export, deliberately NOT a live Discogs listing upload file."""
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['item_id','release_id','media_condition','sleeve_condition','price','currency','comments','status'])
    with connect(settings.db_path) as c:
        for r in c.execute('SELECT * FROM listing_drafts ORDER BY id'):
            # Spreadsheet imports should not interpret source notes as formulas.
            text=r['description']
            if text.startswith(('=','+','-','@')):
                text="'"+text
            writer.writerow([r['id'],r['release_id'],r['media_cond'],r['sleeve_cond'],r['price'],r['currency'],text,'待確認照片及刊登權限'])
    return '\ufeff'+output.getvalue()

def submission_record(c,draft_id):
    """Latest Discogs submission for a draft; a damaged record reads as an unresolved attempt, never as absent."""
    row=c.execute('SELECT value FROM meta WHERE key=?',(SUBMISSION_PREFIX+str(draft_id),)).fetchone()
    if not row:return None
    try:
        data=json.loads(row[0])
    except ValueError:
        data=None
    return data if isinstance(data,dict) else {'status':'damaged','reason':'送出紀錄損壞，請人工核對'}

def draft_export_issues(c,draft):
    """Recheck mutable source facts at download time, not only when drafting."""
    issues=[]
    if c.execute('SELECT 1 FROM published_listings WHERE source_url=? AND release_id=?',(draft['source_url'],draft['release_id'])).fetchone():issues.append('此貨源版本已登錄上架，避免重複匯出')
    if c.execute('SELECT 1 FROM excluded_matches WHERE source_url=? AND release_id=?',(draft['source_url'],draft['release_id'])).fetchone():issues.append('此貨源配對已被排除，請先核對或恢復配對')
    submission=submission_record(c,draft['id'])
    if submission is not None and submission.get('status') not in ('listed','failed'):issues.append('Discogs 刊登結果不明，請先讀回刊登狀態或人工核對；系統不會重送')
    def stale(value):
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(value)).total_seconds()
            return age<0 or age>48*3600
        except (ValueError,TypeError):return True
    if stale(draft['created_at']):issues.append('草稿確認已超過 48 小時，請編輯並重新確認')
    if not draft['version_confirmed']:issues.append('尚未確認版本')
    if draft['media_cond'] not in GRADES or draft['sleeve_cond'] not in GRADES+('Generic','No Cover','Not Graded'):issues.append('尚未確認品相')
    if not draft['owned_confirmed'] and not (draft['supply_confirmed'] and draft['source_url'] and draft['dispatch_days']):issues.append('尚未確認供貨與出貨時間')
    if draft['source_offer_id'] is not None:
        offer=c.execute('SELECT * FROM sourcing_offers WHERE id=?',(draft['source_offer_id'],)).fetchone()
        if not offer:issues.append('來源報價不存在')
        else:
            if offer['release_id']!=draft['release_id'] or not offer['version_confirmed']:issues.append('來源版本需重新核對')
            if offer['source_url']!=draft['source_url']:issues.append('來源報價連結已變更，請重新確認草稿貨源')
            if stale(offer['recorded_at']):issues.append('來源報價已過期，請先更新報價')
            if offer['recorded_at']>draft['created_at']:issues.append('來源報價已更新，請重新確認草稿')
            if not draft['owned_confirmed'] and not offer['supply_confirmed']:issues.append('來源已取消供貨確認')
    return issues

def draft_profit_review(c,settings,draft):
    """Estimate using the draft sale price, retaining current source evidence."""
    from comparisons import calculate
    offer=c.execute('SELECT * FROM sourcing_offers WHERE id=?',(draft['source_offer_id'],)).fetchone()
    fields=('sale_twd','cost_twd','gross_twd','fees_twd','net_twd','net_margin')
    if not offer or offer['release_id']!=draft['release_id']:
        return {**{key:None for key in fields},'ready':False,'issues':['尚未連結相同版本的進貨報價，無法估算利潤']}
    values={**dict(offer),'title':draft['title'],'sale_price':draft['price'],'sale_currency':draft['currency']}
    source=c.execute('SELECT * FROM platform_candidates WHERE source_url=?',(offer['source_url'],)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='platform_candidates'").fetchone() else None
    row=calculate(c,settings,values,source,True)
    issues=list(dict.fromkeys(row['issues']+draft_export_issues(c,draft)))
    return {**{key:row[key] for key in fields},'ready':row['ready'] and not issues,'issues':issues}

def export_history(settings):
    with connect(settings.db_path) as c:
        return [{**dict(r),'items':json.loads(r['items'])} for r in c.execute('SELECT id,generated_at,currency,items FROM listing_exports ORDER BY id DESC LIMIT 20')]

def quicklister_csv(settings,ids,seller_currency):
    """Export selected drafts using the documented Quicklister schema, never publish."""
    if not ids or len(ids)>500 or len(ids)!=len(set(ids)):raise ValueError('請選擇 1 至 500 筆不同草稿')
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['artist','title','catno','format','year','media_condition','sleeve_condition','price','comments','external_id','accept_offer'])
    items=[]
    with connect(settings.db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        for draft_id in ids:
            r=c.execute('SELECT d.*,r.artist,r.title,r.catno,r.format,r.year FROM listing_drafts d JOIN releases r USING(release_id) WHERE d.id=?',(draft_id,)).fetchone()
            if not r:raise ValueError('草稿不存在')
            issues=draft_export_issues(c,r)
            if issues:raise ValueError(f"草稿 #{draft_id}："+'；'.join(issues))
            if r['currency']!=seller_currency:raise ValueError('選取商品幣別必須與 Discogs 賣家設定相同，請分批匯出')
            description=r['description']
            if r['dispatch_days']:description+=f" Dispatch within {r['dispatch_days']} days after payment."
            values=[r['artist'],r['title'],r['catno'],r['format'],r['year'],r['media_cond'],r['sleeve_cond'],r['price'],description[:500],f"simples-{r['id']}-release-{r['release_id']}",'N']
            writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in values])
            items.append({key:r[key] for key in ('id','release_id','artist','title','format','price','media_cond','sleeve_cond')})
        content=output.getvalue()
        c.execute('INSERT INTO listing_exports(generated_at,currency,items,content_sha256) VALUES(?,?,?,?)',(now(),seller_currency,json.dumps(items,ensure_ascii=False),hashlib.sha256(content.encode()).hexdigest()))
    return content

class BatchDraftError(ValueError):
    pass

def create_batch(settings,offer_ids,parse_id,parse_currency,required):
    """Validate all selections before writing; preserve already edited drafts."""
    import comparisons
    if not isinstance(offer_ids,list) or not 1<=len(offer_ids)<=50 or any(type(x) is not int or x<=0 for x in offer_ids) or len(set(offer_ids))!=len(offer_ids):
        raise BatchDraftError('請選擇 1 至 50 筆不同的已核對報價')
    rows={r['offer']['id']:r for r in comparisons.build(settings) if r['offer']}
    for oid in offer_ids:
        row=rows.get(oid)
        if not row or not row['ready']:
            raise BatchDraftError(f'報價 #{oid} 尚未備妥：'+('；'.join(row['issues']) if row else '找不到報價'))
    created=skipped=0
    with connect(settings.db_path) as c:
        for oid in offer_ids:
            if c.execute('SELECT 1 FROM listing_drafts WHERE source_offer_id=?',(oid,)).fetchone():
                skipped+=1;continue
            offer=rows[oid]['offer']
            data={**offer,'source_offer_id':oid,'price':offer['sale_price'],'currency':offer['sale_currency']}
            for field in ('version_confirmed','owned_confirmed','supply_confirmed'):data[field]='yes' if offer.get(field) else ''
            save_draft(c,data,parse_id,parse_currency,required);created+=1
    return {'saved':True,'created':created,'skipped':skipped,'message':f'已建立 {created} 件草稿；{skipped} 件已有草稿，保留原內容'}
