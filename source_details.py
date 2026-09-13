"""Strict saved-product detail readers. No discovery, purchasing or listing."""
import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlsplit
import platforms


def text(value):
    return ' '.join(unescape(str(value)).replace('\u200e','').translate(str.maketrans('［］','[]')).split())


def detail_url(platform, external_id, source_url=None):
    if platform=='rottenblues':return __import__('rottenblues').detail_url(external_id,source_url)
    pattern=r'[0-9]+' if platform in ('tower','yahoo_tw') else r'[A-Za-z0-9]+'
    if platform not in ('tower','yahoo_tw','yahoo_jp') or not re.fullmatch(pattern,str(external_id)):
        raise ValueError('商品編號無效')
    return platforms.candidate(platform,external_id,'',None)['source_url']


def parse(platform, external_id, raw, source_url=None):
    if platform=='rottenblues':return __import__('rottenblues').parse_detail(external_id,source_url,raw)
    expected=detail_url(platform,external_id)
    root=platforms.Tree(raw).root
    def script(sid):
        nodes=[n for n in root.find('script') if n.attrs.get('id')==sid]
        if len(nodes)!=1:raise ValueError('商品頁結構改變')
        return json.loads(nodes[0].text())
    fmt=None;identity={}
    if platform=='yahoo_tw':
        item=script('isoredux-data')['item']
        if str(item.get('id'))!=str(external_id) or item.get('type')!=1 or item.get('status')!=2:
            raise ValueError('商品編號或狀態無法確認')
        amount=platforms.price(item.get('price'))
        span=item.get('priceRange') or {}
        low,high=platforms.price(span.get('lowPrice')),platforms.price(span.get('highPrice'))
        kind='current_bid' if item.get('bidInfo') else 'range' if low and high and low!=high else 'listed'
        availability='售完／無現貨' if item.get('totalQuantity')==0 else '未確認'
        title=item.get('title');currency='TWD'
    else:
        products=[]
        for node in root.find('script'):
            if node.attrs.get('type')!='application/ld+json':continue
            value=json.loads(node.text())
            values=value if isinstance(value,list) else [value]
            products.extend(v for v in values if isinstance(v,dict) and v.get('@type')=='Product')
        if len(products)!=1:raise ValueError('商品結構化資料不唯一')
        item=products[0];url=urlsplit(str(item.get('url','')))
        expected_host=urlsplit(expected).hostname
        paths=('/item/'+str(external_id),'/item/item/'+str(external_id)) if platform=='tower' else ('/jp/auction/'+str(external_id),)
        if url.scheme!='https' or url.hostname!=expected_host or url.path not in paths:
            raise ValueError('回傳其他商品')
        if platform=='tower' and str(item.get('itemId'))!=str(external_id):raise ValueError('商品編號不符')
        offer=item['offers']
        if not isinstance(offer,dict) or offer.get('priceCurrency')!='JPY':raise ValueError('價格幣別不符')
        amount=platforms.price(offer.get('price'));title=item.get('name');currency='JPY'
        stock=str(offer.get('availability','')).rsplit('/',1)[-1].lower()
        availability={'instock':'在庫あり','limitedavailability':'在庫わずか','outofstock':'無現貨','soldout':'售完','discontinued':'無現貨','preorder':'預購','backorder':'お取り寄せ'}.get(stock,'未確認')
        kind='listed'
        if platform=='tower':
            fmt=item.get('itemVariant')
            from identity_data import barcodes
            brand=item.get('brand')
            identity={'barcodes':barcodes([item.get(k) for k in ('gtin','gtin8','gtin12','gtin13','gtin14','sku')]),'labels':brand.get('name','') if isinstance(brand,dict) and isinstance(brand.get('name'),str) else ''}
            # Tower's Product name omits edition suffixes present in its visible
            # product heading. Retain those suffixes for the saved-title check.
            headings=root.find('h1','PC-item-info-title')
            if headings:
                if len(headings)!=1 or not isinstance(title,str) or not title.strip():
                    raise ValueError('商品頁結構改變')
                full_title=text(headings[0].text());base=text(title)
                suffix=full_title[len(base):] if full_title.startswith(base) else None
                if suffix is None or (suffix and not re.fullmatch(r'(?:\s*(?:＜[^＜＞]+＞|\[[^\[\]]+\]))+',suffix)):
                    raise ValueError('商品名稱變更，待重新配對')
                title=full_title
        if platform=='yahoo_jp':
            # A structured Offer can describe the current bid, not a buy-now price.
            kind='current_bid'
            end=offer.get('priceValidUntil')
            if end:
                until=datetime.fromisoformat(end.replace('Z','+00:00'))
                if until.tzinfo is None:raise ValueError('拍賣時間不含時區')
                if until<=datetime.now(timezone.utc):availability='拍賣已結束／無現貨'
                elif availability not in ('無現貨','售完'):availability='拍賣中／需確認結標'
            elif availability not in ('無現貨','售完'):availability='拍賣中／需確認結標'
    if not isinstance(title,str) or not title.strip() or amount is None:raise ValueError('商品名稱或價格缺失')
    return {**identity,'title':text(title),'format':fmt,'price':amount,'currency':currency,'price_kind':kind,'availability':availability}
