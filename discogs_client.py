"""GET-only client; shared SQLite budget keeps overlapping jobs below 60/min."""
import json
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from db import connect, now
from config import money

class APIError(RuntimeError):
    pass

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
        if not path.startswith(('/releases/', '/database/search', '/marketplace/stats/')):
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
            'labels':', '.join(l['name'] for l in data.get('labels',[]) if isinstance(l,dict) and isinstance(l.get('name'),str)),
            'catno':', '.join(l['catno'] for l in data.get('labels',[]) if isinstance(l,dict) and isinstance(l.get('catno'),str)),
            'have':integer(community.get('have'),'have'),'want':integer(community.get('want'),'want')}

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
