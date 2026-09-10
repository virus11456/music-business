"""Sourcing records and listing preparation; no external purchase or listing POST."""
import csv
import io
import json
import re
from urllib.parse import urlsplit
from datetime import datetime, timezone
from db import connect, now
from config import money
from fx import convert

GRADES=('Mint (M)','Near Mint (NM or M-)','Very Good Plus (VG+)','Very Good (VG)','Good Plus (G+)','Good (G)','Fair (F)','Poor (P)')
SCHEMA='''
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
        for name,definition in [('owned_confirmed','INTEGER NOT NULL DEFAULT 0'),('sale_price','TEXT'),('sale_currency','TEXT')]:
            if name not in columns:c.execute(f'ALTER TABLE sourcing_offers ADD COLUMN {name} {definition}')

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
                    day=datetime.now(timezone.utc).date().isoformat()
                    sale,_=convert(c,s['lowest_price'],s['currency'],day)
                    purchase,_=convert(c,row['amount'],row['currency'],day)
                    net=sale-purchase-sale*settings.fee_pct-settings.shipping-settings.packing-settings.reserve
                    offer.update(net_twd=str(net.quantize(money('.01'))),margin=float(net/sale) if sale>0 else None)
                    stale=(datetime.now(timezone.utc)-datetime.fromisoformat(s['captured_at'])).days>2
                    offer['status']='行情已過期' if stale else '待核對版本' if not row['version_confirmed'] else '待核對品相與售價' if net>0 else '暫無利潤'
                except ValueError:
                    offer['status']='缺少有效匯率'
            offers.append(offer)
        drafts=[dict(r) for r in c.execute('SELECT d.*,r.title,r.artist FROM listing_drafts d JOIN releases r USING(release_id) ORDER BY d.id DESC')]
    return {'offers':offers,'drafts':drafts,'sheet_url':f'https://docs.google.com/spreadsheets/d/{config[0]}/edit' if config else None,'grades':GRADES}

def save_offer(c,data,parse_id,parse_currency,required):
    media=str(data.get('media_cond','未確認'))
    sleeve=str(data.get('sleeve_cond','未確認'))
    if media not in GRADES+('未確認',) or sleeve not in GRADES+('未確認',):
        raise ValueError('品相無效')
    sale=money(data['sale_price']) if data.get('sale_price') else None
    if sale is not None and sale<=0:raise ValueError('預定售價必須大於零')
    values=(parse_id(required(data,'release_id')),required(data,'vendor'),web_url(required(data,'source_url',1500)),
       str(money(required(data,'amount'))),parse_currency(required(data,'currency')),media,sleeve,
       int(data.get('version_confirmed')=='yes'),now(),int(data.get('owned_confirmed')=='yes'),
       str(sale) if sale is not None else None,parse_currency(required(data,'sale_currency')) if sale is not None else None)
    if data.get('offer_id'):
        changed=c.execute('UPDATE sourcing_offers SET release_id=?,vendor=?,source_url=?,amount=?,currency=?,media_cond=?,sleeve_cond=?,version_confirmed=?,recorded_at=?,owned_confirmed=?,sale_price=?,sale_currency=? WHERE id=?',values+(int(data['offer_id']),)).rowcount
        if not changed:raise ValueError('找不到報價')
    else:
        c.execute('INSERT INTO sourcing_offers(release_id,vendor,source_url,amount,currency,media_cond,sleeve_cond,version_confirmed,recorded_at,owned_confirmed,sale_price,sale_currency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',values)

def save_draft(c,data,parse_id,parse_currency,required):
    if data.get('owned_confirmed')!='yes' or data.get('version_confirmed')!='yes':
        raise ValueError('請確認已持有商品且版本正確')
    media=required(data,'media_cond');sleeve=required(data,'sleeve_cond')
    if media not in GRADES or sleeve not in GRADES+('Generic','No Cover','Not Graded'):
        raise ValueError('請人工確認品相')
    price=money(required(data,'price'))
    if price<=0:
        raise ValueError('售價必須大於零')
    note=str(data.get('note','')).strip()[:500]
    description=f'Media: {media}. Sleeve: {sleeve}.'+(f' {note}' if note else '')
    c.execute('INSERT INTO listing_drafts(release_id,media_cond,sleeve_cond,price,currency,note,description,version_confirmed,owned_confirmed,created_at) VALUES(?,?,?,?,?,?,?,1,1,?)',
      (parse_id(required(data,'release_id')),media,sleeve,str(price),parse_currency(required(data,'currency')),note,description,now()))

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
