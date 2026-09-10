"""Reproducible complete business flow with isolated, explicitly synthetic inputs."""
import csv,io,json,tempfile,threading,time,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from config import Settings
from db import init,connect
from server import Dashboard,handler
import platforms,sheet_sync

FORMATS={990000001:'Vinyl',990000002:'CD',990000003:'Cassette'}

def run_flow(settings,sync_callback=None):
    init(settings.db_path);app=Dashboard(settings)
    http=ThreadingHTTPServer(('127.0.0.1',0),handler(app));thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{http.server_port}'
    def post(path,data):
        with urlopen(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','X-CSRF-Token':app.csrf,'Origin':'http://127.0.0.1:5173'}),timeout=10) as r:result=json.load(r)
        if result.get('accepted'):
            deadline=time.monotonic()+10
            while app.active and time.monotonic()<deadline:time.sleep(.01)
            assert not app.active,'Background work timeout'
            assert app.state()['jobs'][0]['status']=='success',app.state()['jobs'][0]
        return result
    def discogs(path,params=None):
        rid=int(path.rsplit('/',1)[1])
        if '/marketplace/' in path:return {'num_for_sale':2,'lowest_price':{'value':75,'currency':'USD'}}
        return {'id':rid,'title':'TEST ONLY '+FORMATS[rid],'artists':[{'name':'Test Artist'}],'formats':[{'name':FORMATS[rid]}],'year':2000,'country':'Japan','labels':[{'catno':'TEST-'+str(rid)}],'community':{'want':500,'have':100}}
    html=''.join(f'<div class="TOL-item-search-result-PC-result-list-display-item"><span class="result-display-contents-category-text">{"LP" if fmt=="Vinyl" else fmt}</span><a class="tr-item-block" href="https://tower.jp/item/{rid}"></a><div class="tr-item-block-info-item-name"><a>TEST ONLY {fmt}</a></div><span class="is-text-amount">&yen;1,980</span>在庫あり 規格品番： TEST-{rid} |</div>' for rid,fmt in FORMATS.items())
    real_search=platforms.search
    def search(s,q,selected):return real_search(s,q,selected,fetcher=lambda url:html)
    def sync(s):
        tables,_=sheet_sync.build_tables(s)
        return {'synced':True,'test_transport':True,'source_rows':len(tables['Sources'])-1}
    try:
        with patch('discogs_client.DiscogsClient.get',side_effect=discogs),patch('sourcing.platforms.search',side_effect=search),patch('platforms.time.sleep'),patch('sheet_sync.sync',side_effect=sync):
            for rid in FORMATS:
                post('/api/releases',{'release':str(rid)})
                post('/api/decisions',{'release_id':rid,'choice':'want'})
                post('/api/pipeline/run',{'release_id':rid,'platforms':['tower']})
            rows=app.state()['workflow']['comparisons'];assert len(rows)==3, [(r['release_id'],r.get('source')) for r in rows]
            assert all(not r['ready'] and r['gross_twd'] is None for r in rows)
            for cc,rate in [('USD','32'),('JPY','.22')]:post('/api/fx',{'currency':cc,'rate':rate,'date':date.today().isoformat(),'source':'TEST ONLY synthetic rate'})
            for rid in FORMATS:
                data={'release_id':rid,'vendor':'TEST ONLY supplier','source_url':f'https://tower.jp/item/{rid}','amount':'4500','currency':'JPY','sale_price':'80','sale_currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7'}
                post('/api/offers',data)
                row=next(r for r in app.state()['workflow']['comparisons'] if r['release_id']==rid)
                assert row['ready'],row['issues']
                assert (row['gross_twd'],row['net_twd'])==('1570.00','612.80')
                draft={**data,'price':'80','currency':'USD','source_offer_id':row['offer']['id']}
                post('/api/drafts',draft);post('/api/drafts',{**draft,'note':'TEST revised draft'})
                try:
                    post('/api/drafts',{**draft,'release_id':next(x for x in FORMATS if x!=rid)})
                    raise AssertionError('Mismatched source offer accepted')
                except HTTPError as error:
                    assert error.code==400
                    error.close()
            drafts=app.state()['workflow']['drafts'];assert len(drafts)==3
            assert all(d['owned_confirmed']==0 and d['supply_confirmed']==1 and d['note']=='TEST revised draft' for d in drafts)
            ids='&'.join('id='+str(d['id']) for d in drafts)
            with urlopen(base+'/api/drafts/quicklister?currency=USD&'+ids) as r:export=list(csv.DictReader(io.StringIO(r.read().decode())))
            assert len(export)==3 and {r['format'] for r in export}==set(FORMATS.values())
            assert all(r['price']=='80' and r['sleeve_condition']=='No Cover' for r in export)
        if sync_callback:sync_callback(settings)
        return {'formats':list(FORMATS.values()),'matched_rows':3,'drafts':3,'export_rows':3,'gross_twd':1570,'net_twd':612.8,'synthetic':True}
    finally:http.shutdown();http.server_close();thread.join()

class FullWorkflowTests(unittest.TestCase):
    def test_three_formats_demand_to_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=run_flow(Settings(db_path=Path(tmp)/'isolated.db',token='TEST-NOT-REAL'))
            self.assertEqual(result['export_rows'],3)
