"""Local-only dashboard API. Shares the CLI database and business logic."""
from fx import business_day
import argparse
import json
import secrets
import sqlite3
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs

import analyze
import pipeline
from remote_access import RemoteAccess
from scheduler import Scheduler
import ingest
import workflow
import sheet_sync
import platforms
import matching
import comparisons
import source_queue
import sourcing
from cli import currency
from config import Settings, load_env, money
from db import connect, decide, init, job, latest_decision, now
from discogs_client import APIError, DiscogsClient

def release_id(value):
    import re
    match = re.fullmatch(r'(?:https://www\.discogs\.com/(?:[a-z]{2}/)?release/)?(\d+)(?:-[^\s]*)?/?', str(value).strip())
    if not match or int(match[1]) <= 0:
        raise ValueError('請填入正確的 Discogs release ID 或版本連結')
    return int(match[1])

def required(data, key, limit=300):
    value = str(data.get(key, '')).strip()
    if not value or len(value)>limit:
        raise ValueError('請填寫有效的 '+key)
    return value

class Dashboard:
    def __init__(self, settings):
        self.settings=settings
        self.access=RemoteAccess()
        self.csrf=secrets.token_urlsafe(32)
        self.lock=threading.Lock()
        self.active=None
        self.scheduler=Scheduler(self)
        workflow.init_workflow(settings)
        platforms.init(settings)
        matching.init(settings)
        source_queue.init(settings)

    def state(self):
        with connect(self.settings.db_path) as c:
            records=[]
            for row in c.execute('SELECT * FROM releases ORDER BY added_at DESC').fetchall():
                r=dict(row)
                snap=c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(r['release_id'],)).fetchone()
                score=c.execute('SELECT * FROM scores WHERE release_id=? ORDER BY id DESC LIMIT 1',(r['release_id'],)).fetchone()
                cost=c.execute('SELECT * FROM costs WHERE release_id=? ORDER BY recorded_at DESC,id DESC LIMIT 1',(r['release_id'],)).fetchone()
                decision=latest_decision(c,r['release_id'])
                r.update(snapshot=dict(snap) if snap else None,
                    analysis=json.loads(score['components']) if score else None,
                    scored_at=score['scored_at'] if score else None,
                    cost=dict(cost) if cost else None,decision=dict(decision) if decision else None)
                r['history']=[dict(h) for h in c.execute('SELECT captured_at,lowest_price,currency FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 30',(r['release_id'],))][::-1]
                records.append(r)
            targets=[]
            for row in c.execute('SELECT * FROM scan_targets ORDER BY id DESC'):
                r=dict(row)
                r['params']=json.loads(r.pop('query_params'))
                targets.append(r)
            jobs=[dict(j) for j in c.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 10')]
            fx=[dict(r) for r in c.execute('SELECT * FROM fx_rates ORDER BY rate_date DESC,currency LIMIT 30')]
            health=c.execute('SELECT * FROM api_health WHERE id=1').fetchone()
            mode=c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
        return {'schedule':self.scheduler.state(),'csrf':self.csrf,'records':records,'targets':targets,'jobs':jobs,'fx':fx,'workflow':{**workflow.get_workflow(self.settings),'comparisons':comparisons.build(self.settings),'source_queue':source_queue.state(self.settings),'platforms':{**platforms.state(self.settings),'matches':matching.state(self.settings)}},
            'api':dict(health) if health else None,'active':self.active,'mode':mode[0] if mode else 'live',
            'configured':{'ai_listing':__import__('ai_listing').configured(),'discogs':bool(self.settings.token),'telegram':bool(self.settings.telegram_token and self.settings.telegram_chat),'sheets':sheet_sync.configured()},
            'assumptions':{'fee_pct':str(self.settings.fee_pct),'shipping':str(self.settings.shipping),
                           'packing':str(self.settings.packing),'reserve':str(self.settings.reserve),'min_margin':str(self.settings.min_margin)}}

    def start(self, name, operation):
        if not self.lock.acquire(blocking=False):
            raise ValueError('上一個工作仍在執行，請稍候')
        self.active={'name':name,'started_at':now()}
        def worker():
            try:
                with job(self.settings.db_path,name) as detail:
                    result=operation()
                    if result:
                        detail.update(result)
            except Exception:
                # Job records contain sanitized error type; never expose request headers/token.
                pass
            finally:
                self.active=None
                self.lock.release()
        threading.Thread(target=worker,daemon=True).start()
        return {'accepted':True,'message':'工作已開始，完成後畫面會自動更新'}

    def mutate(self,path,data):
        s=self.settings
        if path=='/api/sourcing/reverse':
            if not s.token:raise ValueError('尚未設定 Discogs')
            with connect(s.db_path) as c:
                mode=c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if mode and mode[0]=='demo':raise ValueError('示範庫不能抓入真實資料')
            query=required(data,'query',120) if data.get('query') else None
            selected=data.get('platforms')
            if query and (not isinstance(selected,list) or not selected or len(selected)>4 or any(p not in platforms.PARSERS for p in selected)):raise ValueError('請選擇平台')
            return self.start('先找貨 → 反查需求 → 比價同步',lambda:source_queue.run(s,query,selected))
        if path in ('/api/refresh','/api/releases','/api/scan','/api/platforms/match','/api/sourcing/find','/api/pipeline/run'):
            with connect(s.db_path) as c:
                mode=c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if mode and mode[0]=='demo':
                raise ValueError('示範庫不能抓入真實資料')
            if not s.token:
                raise ValueError('請先在本機 .env 設定 Discogs token')
        if path=='/api/pipeline/run':
            rid=release_id(required(data,'release_id'))
            selected=data.get('platforms')
            if not isinstance(selected,list) or not selected or len(selected)>4 or any(p not in platforms.PARSERS for p in selected):raise ValueError('請選擇平台')
            query=required(data,'query',120) if data.get('query') else None
            return self.start('完整更新與比價同步',lambda:pipeline.run(s,[rid],selected,query))
        if path=='/api/sourcing/find':
            rid=release_id(required(data,'release_id'))
            selected=data.get('platforms')
            if not isinstance(selected,list) or not selected or len(selected)>4 or any(p not in platforms.PARSERS for p in selected):raise ValueError('請選擇平台')
            query=required(data,'query',120) if data.get('query') else None
            return self.start('依 Discogs 需求找貨',lambda:sourcing.find(s,rid,selected,query))
        if path=='/api/platforms/match':
            candidate_id=int(required(data,'candidate_id'))
            query=data.get('query')
            if query is not None and (not isinstance(query,str) or len(query)>160):
                raise ValueError('搜尋詞無效')
            if not s.token:raise ValueError('尚未設定 Discogs')
            return self.start('搜尋 Discogs 版本',lambda:matching.search(s,candidate_id,query))
        if path=='/api/platforms/search':
            query=required(data,'query',120)
            selected=data.get('platforms')
            if not isinstance(selected,list) or not selected or len(selected)>4 or any(p not in platforms.PARSERS for p in selected):
                raise ValueError('請選擇已支援的平台')
            with connect(s.db_path) as c:
                mode=c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if mode and mode[0]=='demo':
                raise ValueError('請切換至正式資料庫')
            return self.start('跨平台搜尋',lambda:platforms.search(s,query,selected))
        if path=='/api/releases':
            rid=release_id(required(data,'release'))
            def add():
                ingest.fetch_one(DiscogsClient(s),s,rid)
                return analyze.run(s)
            return self.start('加入唱片',add)
        if path=='/api/refresh':
            def refresh():
                result=ingest.run(s)
                result.update(analyze.run(s))
                return result
            return self.start('更新行情',refresh)
        if path=='/api/analyze':
            return self.start('重新評分',lambda:analyze.run(s))
        if path=='/api/sheets/sync':
            if not sheet_sync.configured():
                raise ValueError('尚未設定 Google Sheets 帳號授權')
            return self.start('同步 Google Sheets',lambda:sheet_sync.sync(s))
        if path=='/api/scan':
            with connect(s.db_path) as c:
                if not c.execute('SELECT 1 FROM scan_targets WHERE enabled=1').fetchone():
                    raise ValueError('請先新增並啟用至少一個掃描主題')
            def scan():
                result=ingest.scan(s,pages=1)
                fetched=ingest.run(s)
                result['failed']+=fetched['failed']
                result['fetched']=fetched['success']
                result.update(analyze.run(s))
                return result
            return self.start('掃描與抓價',scan)
        # Serialize short changes against background jobs; no hidden competing mutations.
        if not self.lock.acquire(blocking=False):
            raise ValueError('行情工作執行中，請完成後再儲存')
        try:
            if path=='/api/drafts/suggest-note':
                import ai_listing
                return ai_listing.suggest(s,release_id(required(data,'draft_id')))
            if path=='/api/assumptions':
                from config import business_values
                values=business_values(data)
                with connect(s.db_path) as c:c.execute("INSERT OR REPLACE INTO meta VALUES('business_assumptions',?)",(json.dumps({k:str(v) for k,v in values.items()}),))
                for key,value in values.items():setattr(s,key,float(value) if key=='min_margin' else value)
                analyze.run(s)
                return {'saved':True,'message':'費用設定已儲存並重新計算；Sheets Inputs 保留原設定'}
            if path=='/api/drafts/batch':
                return workflow.create_batch(s,data.get('offer_ids'),release_id,currency,required)
            with connect(s.db_path) as c:
                if path=='/api/sheets/config':
                    sid=workflow.sheet_id(required(data,'url',1500))
                    c.execute("INSERT OR REPLACE INTO meta VALUES('google_sheet_id',?)",(sid,))
                elif path=='/api/offers':
                    workflow.save_offer(c,data,release_id,currency,required)
                elif path=='/api/listings/register':
                    rid=release_id(required(data,'release_id'));url=workflow.web_url(required(data,'source_url',1500))
                    listing=required(data,'listing_id',30)
                    if not listing.isascii() or not listing.isdigit() or int(listing)<=0:raise ValueError('請填 Discogs 刊登編號')
                    if not c.execute('SELECT 1 FROM releases WHERE release_id=?',(rid,)).fetchone():raise ValueError('版本尚未追蹤')
                    if not c.execute('SELECT 1 FROM platform_candidates WHERE source_url=? UNION SELECT 1 FROM sourcing_offers WHERE source_url=?',(url,url)).fetchone():raise ValueError('找不到貨源')
                    c.execute('INSERT INTO published_listings VALUES(?,?,?,?) ON CONFLICT(source_url,release_id) DO UPDATE SET listing_id=excluded.listing_id,recorded_at=excluded.recorded_at',(url,rid,listing,now()))
                elif path=='/api/listings/unregister':
                    c.execute('DELETE FROM published_listings WHERE source_url=? AND release_id=?',(workflow.web_url(required(data,'source_url',1500)),release_id(required(data,'release_id'))))
                elif path=='/api/comparisons/exclude':
                    rid=release_id(required(data,'release_id'));url=workflow.web_url(required(data,'source_url'))
                    if not isinstance(data.get('excluded'),bool):raise ValueError('排除狀態無效')
                    exists=c.execute('SELECT 1 FROM platform_candidates WHERE source_url=? UNION SELECT 1 FROM sourcing_offers WHERE source_url=?',(url,url)).fetchone()
                    if not exists:raise ValueError('找不到貨源')
                    if data['excluded']:c.execute('INSERT OR REPLACE INTO excluded_matches VALUES(?,?,?)',(url,rid,now()))
                    else:c.execute('DELETE FROM excluded_matches WHERE source_url=? AND release_id=?',(url,rid))
                elif path=='/api/drafts':
                    workflow.save_draft(c,data,release_id,currency,required)
                elif path=='/api/decisions':
                    rid=release_id(required(data,'release_id'))
                    target=data.get('target')
                    cc=currency(data['currency']) if data.get('currency') else None
                    decide(c,rid,required(data,'choice'),target,cc)
                elif path=='/api/costs':
                    rid=release_id(required(data,'release_id'))
                    amount=money(required(data,'amount'))
                    c.execute('INSERT INTO costs(release_id,source,cost_amount,cost_currency,grading,recorded_at) VALUES(?,?,?,?,?,?)',
                        (rid,required(data,'source'),str(amount),currency(required(data,'currency')),str(data.get('grading',''))[:100],now()))
                elif path=='/api/fx':
                    day=date.fromisoformat(required(data,'date'))
                    if day>date.fromisoformat(business_day()):
                        raise ValueError('匯率日期不能在未來')
                    rate=money(required(data,'rate'))
                    cc=currency(required(data,'currency'))
                    if rate<=0 or cc=='TWD':
                        raise ValueError('請填寫外幣對台幣的正數匯率')
                    c.execute('INSERT OR REPLACE INTO fx_rates VALUES(?,?,?,?)',(cc,day.isoformat(),str(rate),required(data,'source')))
                elif path=='/api/targets':
                    ratio=float(data.get('ratio',1.5))
                    if not 0<=ratio<=1000000:
                        raise ValueError('請填有效需求比值')
                    params={'artist':required(data,'artist'),'country':required(data,'country'),'format':required(data,'format')}
                    c.execute('INSERT INTO scan_targets(name,query_params,min_want_have) VALUES(?,?,?)',
                        (required(data,'name'),json.dumps(params),ratio))
                elif path=='/api/targets/toggle':
                    if not isinstance(data.get('enabled'),bool):
                        raise ValueError('啟用狀態無效')
                    changed=c.execute('UPDATE scan_targets SET enabled=? WHERE id=?',(int(data['enabled']),int(data['id']))).rowcount
                    if not changed:
                        raise ValueError('找不到掃描主題')
                else:
                    raise ValueError('找不到這個操作')
            if path in ('/api/costs','/api/fx'):
                analyze.run(s)
            return {'saved':True,'message':'已儲存'}
        finally:
            self.lock.release()

def handler(dashboard):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def local(self):
            host=urlsplit('//'+self.headers.get('Host','')).hostname
            return host in ('127.0.0.1','localhost','::1')

        def end_headers(self):
            if dashboard.access.token and self.headers.get('Origin')==dashboard.access.origin:
                self.send_header('Access-Control-Allow-Origin',dashboard.access.origin)
                self.send_header('Vary','Origin')
            super().end_headers()

        def authorized(self):
            status=dashboard.access.allowed(self.headers)
            if status!=200:
                self.respond(status,{'error':'請登入工作室' if status==401 else '不允許此來源連線'})
                return False
            return True

        def do_OPTIONS(self):
            if not dashboard.access.token or self.headers.get('Origin')!=dashboard.access.origin:
                return self.respond(403,{'error':'不允許此來源連線'})
            self.send_response(204)
            self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-CSRF-Token')
            self.send_header('Access-Control-Max-Age','600')
            self.end_headers()

        def respond(self,status,data):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.authorized():return
            if urlsplit(self.path).path=='/api/drafts/quicklister':
                try:
                    query=parse_qs(urlsplit(self.path).query)
                    ids=[int(v) for v in query.get('id',[])]
                    seller_currency=currency(query.get('currency',[''])[0])
                except (ValueError,TypeError):
                    return self.respond(400,{'error':'請選取草稿，且全部幣別須與你確認的 Discogs 賣家幣別一致'})
                try:body=workflow.quicklister_csv(dashboard.settings,ids,seller_currency).encode()
                except ValueError as error:return self.respond(400,{'error':str(error)})
                self.send_response(200)
                self.send_header('Content-Type','text/csv; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="discogs-quicklister.csv"')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body);return
            if self.path=='/api/drafts/export':
                body=workflow.review_csv(dashboard.settings).encode()
                self.send_response(200)
                self.send_header('Content-Type','text/csv; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="listing-review.csv"')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path!='/api/state':
                return self.respond(404,{'error':'找不到頁面'})
            try:
                self.respond(200,dashboard.state())
            except Exception:
                self.respond(500,{'error':'資料讀取失敗，請檢查本機服務'})

        def do_POST(self):
            if not self.authorized():return
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),dashboard.csrf):
                return self.respond(403,{'error':'頁面驗證已過期，請重新整理'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self.respond(415,{'error':'不支援的資料格式'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:
                    return self.respond(413,{'error':'資料長度無效'})
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):
                    raise ValueError('資料格式無效')
                result=dashboard.mutate(self.path,data)
                self.respond(202 if result.get('accepted') else 200,result)
            except workflow.BatchDraftError as error:
                self.respond(400,{'error':str(error)})
            except (ValueError,KeyError,TypeError):
                self.respond(400,{'error':'資料無效或系統忙碌，請檢查欄位並等待目前工作完成'})
            except sqlite3.IntegrityError:
                self.respond(400,{'error':'資料重複或找不到對應唱片，請確認輸入'})
            except Exception:
                self.respond(500,{'error':'操作未完成，請查看工作紀錄'})
    return Handler

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=8765)
    args=p.parse_args()
    load_env()
    settings=Settings()
    init(settings.db_path)
    dashboard=Dashboard(settings)
    http=ThreadingHTTPServer(('127.0.0.1',args.port),handler(dashboard))
    dashboard.scheduler.start()
    print(f'Local API ready: http://127.0.0.1:{args.port}',flush=True)
    try:http.serve_forever()
    finally:
        dashboard.scheduler.stop()
        http.server_close()
