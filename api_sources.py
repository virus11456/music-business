"""Official marketplace APIs: Rakuten Ichiba Item Search and eBay Browse. Read-only keyword searches."""
import base64
import json
import re
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

RAKUTEN_SEARCH = 'https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701'
EBAY_TOKEN = 'https://api.ebay.com/identity/v1/oauth2/token'
EBAY_SEARCH = 'https://api.ebay.com/buy/browse/v1/item_summary/search'
EBAY_MUSIC = '11233'  # eBay category "Music": records, CDs and cassettes
PLATFORMS = ('rakuten', 'ebay')
PAGE_SIZE = {'rakuten': 30, 'ebay': 40}
RAKUTEN_LAST_PAGE = 100   # documented page range 1-100
EBAY_LAST_OFFSET = 9950   # Browse search stops at 10,000 results
AGENT = 'SimplesRecordResearch/0.1'

def keyword(query, limit=128):
    """Rakuten caps keyword at 128 single-byte characters, so trim by UTF-8 length."""
    text = query.strip()
    while len(text.encode()) > limit:
        text = text[:-1]
    return text.strip()

_token = {'value': None, 'expires': 0.0, 'client': None}
_lock = threading.Lock()

def ebay_token(settings, opener=urlopen, clock=time.time):
    """Application token (client credentials), reused until a minute before it expires."""
    if not (settings.ebay_client_id and settings.ebay_client_secret):
        raise ValueError('尚未設定 eBay API 金鑰')
    with _lock:
        if _token['value'] and _token['client'] == settings.ebay_client_id and clock() < _token['expires'] - 60:
            return _token['value']
        basic = base64.b64encode(f'{settings.ebay_client_id}:{settings.ebay_client_secret}'.encode()).decode()
        body = urlencode({'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'}).encode()
        req = Request(EBAY_TOKEN, data=body, headers={'Authorization': 'Basic ' + basic, 'User-Agent': AGENT,
                                                      'Content-Type': 'application/x-www-form-urlencoded'})
        with opener(req, timeout=25) as response:
            data = json.load(response)
        token, life = data.get('access_token'), data.get('expires_in')
        if not isinstance(token, str) or not token or not isinstance(life, int) or life <= 0:
            raise ValueError('eBay 授權回應格式不符')
        _token.update(value=token, expires=clock() + life, client=settings.ebay_client_id)
        return token

def request(settings, platform, query, page=1):
    if platform == 'rakuten':
        if not (settings.rakuten_app_id and settings.rakuten_access_key):
            raise ValueError('尚未設定樂天 API 金鑰')
        if not 1 <= page <= RAKUTEN_LAST_PAGE:
            raise ValueError('樂天搜尋頁數超出範圍')
        params = {'applicationId': settings.rakuten_app_id, 'keyword': keyword(query), 'hits': PAGE_SIZE['rakuten'],
                  'page': page, 'formatVersion': 2, 'availability': 1}
        # The access key goes in a header so it never appears in a URL.
        return Request(RAKUTEN_SEARCH + '?' + urlencode(params),
                       headers={'accessKey': settings.rakuten_access_key, 'Accept': 'application/json', 'User-Agent': AGENT})
    if platform == 'ebay':
        offset = (page - 1) * PAGE_SIZE['ebay']
        if not 0 <= offset <= EBAY_LAST_OFFSET:
            raise ValueError('eBay 搜尋頁數超出範圍')
        params = {'q': query.strip()[:100], 'category_ids': EBAY_MUSIC, 'limit': PAGE_SIZE['ebay'], 'offset': offset}
        return Request(EBAY_SEARCH + '?' + urlencode(params),
                       headers={'Authorization': 'Bearer ' + ebay_token(settings), 'Accept': 'application/json',
                                'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US', 'User-Agent': AGENT})
    raise ValueError('不支援的 API 平台')

def _url(value, host):
    try:
        parts = urlsplit(str(value))
    except ValueError:
        return None
    ok = parts.scheme == 'https' and parts.hostname and (parts.hostname == host or parts.hostname.endswith('.' + host))
    return str(value) if ok else None

def _price(value):
    from platforms import price
    return price(value)

def _row(platform, eid, title, amount, currency, kind, availability, url):
    return dict(platform=platform, external_id=eid, title=str(title)[:600], artist='', format='未確認', catalog_no='',
                price=_price(amount), currency=currency, price_kind=kind, availability=availability, source_url=url)

def parse(platform, raw, page=1):
    """Rows in the shared platform_candidates shape, plus whether another page exists."""
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('error') or data.get('errors'):
        raise ValueError('API 回應錯誤或格式改變')
    rows = []
    if platform == 'rakuten':
        items = data.get('Items', data.get('items'))
        if not isinstance(items, list):
            raise ValueError('樂天回應缺少商品清單')
        for entry in items:
            item = entry.get('Item', entry.get('item', entry)) if isinstance(entry, dict) else None
            if not isinstance(item, dict):
                raise ValueError('樂天商品格式改變')
            code, url = str(item.get('itemCode', '')), _url(item.get('itemUrl'), 'rakuten.co.jp')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', code) or not url:
                continue
            stock = '來源標示有庫存' if item.get('availability') == 1 else '缺貨'
            rows.append(_row('rakuten', code, item.get('itemName', ''), item.get('itemPrice'), 'JPY', 'listed', stock, url))
        pages = data.get('pageCount', data.get('page_count'))
        more = isinstance(pages, int) and page < min(pages, RAKUTEN_LAST_PAGE)
        return rows, more
    if platform == 'ebay':
        items = data.get('itemSummaries', [])  # absent when nothing matched
        if not isinstance(items, list):
            raise ValueError('eBay 回應缺少商品清單')
        for item in items:
            if not isinstance(item, dict):
                continue
            legacy = str(item.get('legacyItemId') or '')
            if not legacy and isinstance(item.get('itemId'), str) and item['itemId'].count('|') == 2:
                legacy = item['itemId'].split('|')[1]
            url = _url(item.get('itemWebUrl'), 'ebay.com')
            if not re.fullmatch(r'\d{1,20}', legacy) or not url:
                continue
            options = item.get('buyingOptions') or []
            fixed = 'FIXED_PRICE' in options
            price = item.get('price') if fixed or not item.get('currentBidPrice') else item.get('currentBidPrice')
            price = price if isinstance(price, dict) else {}
            currency = str(price.get('currency', '')).upper()
            if not re.fullmatch(r'[A-Z]{3}', currency):
                continue
            rows.append(_row('ebay', legacy, item.get('title', ''), price.get('value'), currency,
                             'listed' if fixed else 'current_bid', '來源標示有庫存' if fixed else '拍賣中／需確認結標', url))
        total = data.get('total')
        offset = (page - 1) * PAGE_SIZE['ebay']
        more = isinstance(total, int) and offset + PAGE_SIZE['ebay'] < total and offset + PAGE_SIZE['ebay'] <= EBAY_LAST_OFFSET
        return rows, more
    raise ValueError('不支援的 API 平台')
