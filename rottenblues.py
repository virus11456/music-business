"""Rotten Blues public Shopify catalog, paged locally; no private/admin API."""
import json
import re
import unicodedata
from decimal import Decimal
from urllib.parse import quote, unquote, urlsplit, parse_qs

BASE = 'https://www.rottenblues.com'
PAGE_SIZE = 40
ALL_QUERY = 'Rotten Blues 全部唱片'


def plain(value):
    from platforms import Tree
    return ' '.join(Tree(str(value or '')).root.text().split())


def handle(value):
    if not isinstance(value, str) or not value or len(value)>500 or any(x in value for x in '/?#\\') or value in ('.','..'):
        raise ValueError('商品編號無效')
    return quote(value, safe='')


def detail_url(external_id, source_url):
    u=urlsplit(str(source_url));parts=u.path.split('/')
    if u.scheme!='https' or u.netloc!='www.rottenblues.com' or len(parts)!=3 or parts[1]!='products' or not str(external_id).isdigit() or parse_qs(u.query)!={'variant':[str(external_id)]}:
        raise ValueError('商品編號無效')
    return BASE+'/products/'+handle(unquote(parts[2]))+'.js'


def product_rows(item, cents=False):
    from platforms import price
    from source_match import identified_format, MERCH
    from identity_data import barcodes
    if not isinstance(item,dict) or not isinstance(item.get('title'),str) or not item['title'].strip():raise ValueError('商品頁結構改變')
    title=plain(item['title']);slug=handle(item.get('handle'))
    variants=item.get('variants')
    if not isinstance(variants,list) or not variants or len(variants)>100:raise ValueError('商品頁結構改變')
    body=plain(item.get('description') if cents else item.get('body_html'))
    tags=item.get('tags',[])
    if isinstance(tags,str):tags=tags.split(',')
    if not isinstance(tags,list):raise ValueError('商品頁結構改變')
    fmt=identified_format(item.get('type' if cents else 'product_type'), title)
    if not fmt or MERCH.search(title):return []
    preorder=bool(re.search(r'預購|予約|pre[ -]?order',' '.join(map(str,tags))+' '+body+' '+title,re.I))
    catalog=re.search(r'(?:規格品番|唱片編號|Catalog(?:ue)?(?:\s*(?:No\.?|Number))?|品番)\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9./-]{2,80})',body,re.I)
    label=re.search(r'(?:Label|レーベル|唱片公司)\s*[:：]\s*([^|;；]{1,100})',body,re.I)
    out=[];seen=set()
    for v in variants:
        eid=str(v.get('id',''))
        if not eid.isdigit() or eid in seen:raise ValueError('商品編號不符')
        seen.add(eid)
        if v.get('price_currency','TWD')!='TWD':raise ValueError('價格幣別不符')
        amount=price(v.get('price'))
        if amount is None:raise ValueError('商品名稱或價格缺失')
        if cents:amount=str(Decimal(amount)/100)
        variant_title=plain(v.get('title',''))
        full=title+(f' [{variant_title}]' if variant_title and variant_title!='Default Title' else '')
        stock='售罄' if v.get('available') is False else '預購' if preorder else '來源標示有庫存' if v.get('available') is True else '未確認'
        out.append(dict(platform='rottenblues',external_id=eid,title=full[:600],artist='',format=fmt,catalog_no=catalog[1] if catalog else '',price=amount,currency='TWD',price_kind='listed',availability=stock,source_url=BASE+'/products/'+slug+'?variant='+eid,barcodes=barcodes(v.get('barcode')),labels=label[1].strip() if label else ''))
    return out


def parse_catalog(raw, query=ALL_QUERY):
    from source_match import identified_format
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get('products'),list):raise ValueError('商品頁結構改變')
    products=data['products']
    if len(products)>PAGE_SIZE:raise ValueError('商品頁結構改變')
    rows=[row for item in products for row in product_rows(item)]
    q=unicodedata.normalize('NFKC',query).strip().casefold()
    if q!=ALL_QUERY.casefold():
        fmt=identified_format(query) if q in ('cd','黑膠','vinyl','lp','卡帶','cassette') else None
        rows=[r for r in rows if (r['format']==fmt if fmt else all(t in unicodedata.normalize('NFKC',r['title']).casefold() for t in q.split()))]
    return rows,len(products)==PAGE_SIZE


def parse_detail(external_id, source_url, raw):
    expected=detail_url(external_id,source_url)
    item=json.loads(raw)
    if not isinstance(item,dict) or BASE+'/products/'+handle(item.get('handle'))+'.js'!=expected:raise ValueError('回傳其他商品')
    rows=product_rows(item,cents=True)
    found=[r for r in rows if r['external_id']==str(external_id)]
    if len(found)!=1:raise ValueError('回傳其他商品')
    return found[0]
