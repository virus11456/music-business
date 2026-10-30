"""GET-only client; shared SQLite budget keeps overlapping jobs below 60/min."""
import json
import re
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from db import connect, now
from config import money

class APIError(RuntimeError):
    pass

class ListingRejected(APIError):
    """Discogs answered with a definite 4xx: nothing was created; the draft may be fixed and resent."""
    def __init__(self, code, message=''):
        super().__init__(f'Discogs 拒絕（HTTP {code}）' + (f'：{message}' if message else ''))
        self.code, self.message = code, message

class ListingUncertain(APIError):
    """Network loss, 5xx, or an unreadable reply: the listing may or may not exist. Never retry blindly."""

class DiscogsClient:
    def __init__(self, settings, transport=urlopen, clock=time.time, sleep=time.sleep):
        if not settings.token:
            raise APIError('請先在本機 .env 設定 DISCOGS_TOKEN')
        self.settings, self.transport, self.clock, self.sleep = settings, transport, clock, sleep

    def wait_turn(self):
        # Recheck after every wait: another process may extend a server cooldown.
        while True:
            with connect(self.settings.db_path) as c:
                c.execute('BEGIN IMMEDIATE')
                row = c.execute('SELECT next_at FROM api_budget WHERE id=1').fetchone()
                delay = max(0, (row[0] if row else 0)-self.clock())
                if delay <= 0:
                    c.execute('INSERT OR REPLACE INTO api_budget VALUES(1,?)',(self.clock()+1.1,))
                    return
            self.sleep(delay)

    def cooldown(self, seconds):
        with connect(self.settings.db_path) as c:
            c.execute('INSERT INTO api_budget VALUES(1,?) ON CONFLICT(id) DO UPDATE SET next_at=max(next_at,excluded.next_at)',
                      (self.clock()+seconds,))

    def get(self, path, params=None):
        if not (path.startswith(('/releases/', '/database/search', '/marketplace/stats/')) or path=='/oauth/identity' or re.fullmatch(r'/users/[A-Za-z0-9_%.-]+/inventory',path)):
            raise APIError('第一版僅允許已列出的唯讀端點')
        url = 'https://api.discogs.com'+path+('?' + urlencode(params) if params else '')
        request = Request(url,headers={'User-Agent':self.settings.user_agent,
            'Authorization':'Discogs token='+self.settings.token,'Accept':'application/json'})
        for attempt in range(4):
            self.wait_turn()
            try:
                with self.transport(request,timeout=30) as response:
                    remaining = response.headers.get('X-Discogs-Ratelimit-Remaining')
                    if remaining is not None:
                        try:
                            remaining = int(remaining)
                        except (ValueError, TypeError):
                            remaining = None
                    if remaining is not None:
                        with connect(self.settings.db_path) as c:
                            c.execute('INSERT OR REPLACE INTO api_health VALUES(1,?,?)',(remaining,now()))
                        if remaining < 5:
                            self.cooldown(60)
                    data = json.load(response)
                    if not isinstance(data,dict):
                        raise APIError('回傳格式不是 JSON object')
                    return data
            except HTTPError as exc:
                code = exc.code
                retry = code == 429 or 500 <= code < 600
                retry_after = exc.headers.get('Retry-After','60' if code==429 else str(2**attempt))
                exc.close()
                if not retry or attempt == 3:
                    raise APIError(f'Discogs HTTP {code}；未顯示含憑證的請求內容') from None
                try:
                    delay = max(2**attempt,float(retry_after))
                except ValueError:
                    delay = 60
                self.cooldown(delay)
            except (URLError, TimeoutError, OSError):
                if attempt == 3:
                    raise APIError('Discogs 連線失敗，已停止本筆抓取') from None
                self.cooldown(2**attempt)
        raise APIError('已達重試上限')

    def post(self, path, payload):
        """Single attempt marketplace write. Callers classify the outcome and must not auto-retry."""
        if path != '/marketplace/listings' or not isinstance(payload, dict):
            raise APIError('只允許建立 marketplace 刊登的寫入端點')
        request = Request('https://api.discogs.com'+path, data=json.dumps(payload).encode(), method='POST',
                          headers={'User-Agent': self.settings.user_agent, 'Authorization': 'Discogs token='+self.settings.token,
                                   'Accept': 'application/json', 'Content-Type': 'application/json'})
        self.wait_turn()
        try:
            with self.transport(request, timeout=30) as response:
                self._record_health(response.headers.get('X-Discogs-Ratelimit-Remaining'))
                status = getattr(response, 'status', 201)
                raw = response.read(100001)
        except HTTPError as exc:
            code = exc.code
            try:
                raw = exc.read(4000)
            except Exception:
                raw = b''
            exc.close()
            if code == 429:
                self.cooldown(60)
            if 400 <= code < 500:
                raise ListingRejected(code, _error_message(raw)) from None
            raise ListingUncertain(f'Discogs HTTP {code}，刊登結果不明') from None
        except (URLError, TimeoutError, OSError):
            raise ListingUncertain('Discogs 連線中斷或逾時，刊登結果不明') from None
        if len(raw) > 100000:
            raise ListingUncertain('Discogs 回應過大，刊登結果不明')
        try:
            data = json.loads(raw)
        except ValueError:
            raise ListingUncertain('Discogs 回應格式無效，刊登結果不明') from None
        if status not in (200, 201) or not isinstance(data, dict):
            raise ListingUncertain(f'Discogs HTTP {status}，刊登結果不明')
        return data

    def _record_health(self, remaining):
        try:
            remaining = int(remaining)
        except (ValueError, TypeError):
            return
        with connect(self.settings.db_path) as c:
            c.execute('INSERT OR REPLACE INTO api_health VALUES(1,?,?)', (remaining, now()))
        if remaining < 5:
            self.cooldown(60)

def _error_message(raw):
    """Discogs error bodies carry a plain message; keep it short and free of control characters."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ''
    message = data.get('message') if isinstance(data, dict) else ''
    if not isinstance(message, str):
        return ''
    return ''.join(ch for ch in message if ch.isprintable())[:200]

def integer(value, name):
    if value is None:
        return None
    if isinstance(value,bool) or not isinstance(value,int) or value < 0:
        raise APIError('欄位型別不符：'+name)
    return value

def parse_release(data, expected_id):
    if data.get('id') != expected_id or not isinstance(data.get('title'),str):
        raise APIError('release id / title 不符，請重新 probe')
    community = data.get('community') or {}
    if not isinstance(community,dict):
        raise APIError('community 格式不符')
    return {'release_id':expected_id,'title':data['title'],
            'artist':', '.join(a['name'] for a in data.get('artists',[]) if isinstance(a,dict) and isinstance(a.get('name'),str)),
            'year':integer(data.get('year'),'year'),'country':data.get('country'),
            'format':', '.join(f['name'] for f in data.get('formats',[]) if isinstance(f,dict) and isinstance(f.get('name'),str)),
            'barcodes':__import__('identity_data').barcodes([v.get('value') for v in (data.get('identifiers') or []) if isinstance(v,dict) and v.get('type')=='Barcode']),
            'labels':', '.join(l['name'] for l in data.get('labels',[]) if isinstance(l,dict) and isinstance(l.get('name'),str)),
            'catno':', '.join(l['catno'] for l in data.get('labels',[]) if isinstance(l,dict) and isinstance(l.get('catno'),str)),
            'have':integer(community.get('have'),'have'),'want':integer(community.get('want'),'want')}

def parse_release_market(data, currency):
    """Lowest price and supply carried on the release itself, or None when the stats call is still needed.

    The release's lowest_price is always USD (curr_abbr is ignored there), so only a USD market can use it.
    Checked against /marketplace/stats on production releases: same value and count, null when none for sale."""
    if currency != 'USD' or 'num_for_sale' not in data or 'lowest_price' not in data:
        return None
    supply = integer(data['num_for_sale'],'num_for_sale')
    price = data['lowest_price']
    if price is None:
        return None,None,supply
    if isinstance(price,bool) or not isinstance(price,(int,float)):
        raise APIError('lowest_price 格式不符')
    return str(money(price)),'USD',supply

def parse_stats(data):
    if 'num_for_sale' not in data or 'lowest_price' not in data:
        raise APIError('marketplace stats 缺少預期欄位，請重新 probe；不寫入猜測值')
    supply = integer(data['num_for_sale'],'num_for_sale')
    price = data['lowest_price']
    if price is None:
        return None,None,supply
    if not isinstance(price,dict) or 'value' not in price or not isinstance(price.get('currency'),str):
        raise APIError('lowest_price 格式不符')
    currency = price['currency'].upper()
    if len(currency)!=3 or not currency.isalpha():
        raise APIError('幣別格式不符')
    return str(money(price['value'])),currency,supply
