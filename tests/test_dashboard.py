import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from config import Settings
from db import init,connect
import demo
import analyze
import workflow
import sheet_sync
from server import Dashboard,handler,release_id

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=Settings(db_path=Path(self.temp.name)/'test.sqlite3',token='NEVER_EXPOSE_THIS')
        init(self.settings.db_path);demo.seed(self.settings);analyze.run(self.settings)
        self.app=Dashboard(self.settings)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}'
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()
    def post(self,path,data,token=True,origin='http://127.0.0.1:5173'):
        headers={'Content-Type':'application/json','Origin':origin}
        if token:headers['X-CSRF-Token']=self.app.csrf
        return urlopen(Request(self.url+path,data=json.dumps(data).encode(),headers=headers),timeout=10)
    def test_state_does_not_expose_secrets(self):
        with urlopen(self.url+'/api/state') as response:
            raw=response.read().decode()
        self.assertNotIn('NEVER_EXPOSE_THIS',raw)
        self.assertEqual(len(json.loads(raw)['records']),4)
    def test_csrf_blocks_mutation(self):
        with self.assertRaises(HTTPError) as result:self.post('/api/decisions',{'release_id':900000001,'choice':'want'},token=False)
        self.assertEqual(result.exception.code,403)
    def test_cross_origin_blocks_mutation(self):
        with self.assertRaises(HTTPError) as result:self.post('/api/decisions',{'release_id':900000001,'choice':'want'},origin='https://evil.example')
        self.assertEqual(result.exception.code,403)
    def test_decision_roundtrip(self):
        with self.post('/api/decisions',{'release_id':900000001,'choice':'want'}) as r:self.assertEqual(r.status,200)
        r=next(r for r in self.app.state()['records'] if r['release_id']==900000001)
        self.assertEqual(r['decision']['decision'],'want')
    def test_offer_roundtrip(self):
        data={'release_id':900000001,'vendor':'Test vendor','source_url':'https://example.com/record','amount':'4500','currency':'JPY','media_cond':'未確認','sleeve_cond':'未確認'}
        with self.post('/api/offers',data) as r:self.assertEqual(r.status,200)
        offer=self.app.state()['workflow']['offers'][0]
        self.assertEqual(offer['net_twd'],'472.00');self.assertEqual(offer['status'],'待核對版本')
    def test_listing_requires_human_checks(self):
        data={'release_id':900000001,'media_cond':'Very Good (VG)','sleeve_cond':'Very Good (VG)','price':'70','currency':'USD'}
        with self.assertRaises(HTTPError) as r:self.post('/api/drafts',data)
        self.assertEqual(r.exception.code,400)
        data.update(owned_confirmed='yes',version_confirmed='yes')
        with self.post('/api/drafts',data):pass
        self.assertEqual(len(self.app.state()['workflow']['drafts']),1)
        self.assertIn('待確認照片及刊登權限',workflow.review_csv(self.settings))
    def test_sheet_config_validation_and_persistence(self):
        with self.assertRaises(HTTPError):self.post('/api/sheets/config',{'url':'https://evil.example/'})
        with self.post('/api/sheets/config',{'url':'https://docs.google.com/spreadsheets/d/test123/edit'}):pass
        self.assertEqual(self.app.state()['workflow']['sheet_url'],'https://docs.google.com/spreadsheets/d/test123/edit')
    def test_release_urls(self):
        self.assertEqual(release_id('https://www.discogs.com/release/123-title'),123)
        with self.assertRaises(ValueError):release_id('https://www.discogs.com/master/123')
    def test_source_text_not_formula(self):
        self.assertEqual(sheet_sync.cell('=IMPORTXML("evil")'),{'userEnteredValue':{'stringValue':'=IMPORTXML("evil")'}})
    def test_sync_preserves_existing_inputs(self):
        with connect(self.settings.db_path) as c:c.execute("INSERT INTO meta VALUES('google_sheet_id','test123')")
        captured=[]
        self_outer=self
        class Response:
            status_code=200
            def __init__(self,data):self.data=data
            def json(self):return self.data
        class Session:
            def request(self,method,url,**kwargs):
                if url.endswith('/values:batchGet'):
                    tables,_=sheet_sync.build_tables(self_outer.settings)
                    return Response({'valueRanges':[{'values':rows} for name,rows in tables.items() if name!='Inputs']})
                if method=='GET':return Response({'sheets':[{'properties':{'title':'SIMPLES_Inputs','sheetId':10},'developerMetadata':[{'metadataKey':'simples_owner','metadataValue':'record_business_v1'}]}]})
                captured.extend(kwargs['json']['requests']);return Response({})
        sheet_sync.sync(self.settings,Session())
        self.assertFalse(any(r.get('updateCells',{}).get('range',{}).get('sheetId')==10 for r in captured))
    def test_sync_refuses_unowned_sheet(self):
        with connect(self.settings.db_path) as c:c.execute("INSERT INTO meta VALUES('google_sheet_id','test123')")
        class Response:
            status_code=200
            def json(self):return {'sheets':[{'properties':{'title':'SIMPLES_Discogs','sheetId':1}}]}
        class Session:
            def request(self,*a,**k):return Response()
        with self.assertRaises(ValueError):sheet_sync.sync(self.settings,Session())


    def test_exclude_restore_persists_and_blocks_export(self):
        data={'release_id':900000001,'vendor':'TEST','source_url':'https://example.com/test-only','amount':'4500','currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7','price':'80'}
        with self.post('/api/offers',data):pass
        with self.post('/api/drafts',data):pass
        draft=self.app.state()['workflow']['drafts'][0]
        change={'release_id':900000001,'source_url':data['source_url'],'excluded':True}
        with self.post('/api/comparisons/exclude',change):pass
        # Recreate application and refresh the offer: neither removes an exclusion.
        self.assertTrue(Dashboard(self.settings).state()['workflow']['comparisons'][0]['excluded'])
        with self.post('/api/offers',{**data,'offer_id':self.app.state()['workflow']['offers'][0]['id']}):pass
        self.assertFalse(self.app.state()['workflow']['comparisons'][0]['ready'])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+f"/api/drafts/quicklister?currency=USD&id={draft['id']}")
        self.assertIn('已被排除',json.load(error.exception)['error']);error.exception.close()
        with self.post('/api/comparisons/exclude',{**change,'excluded':False}):pass
        self.assertFalse(self.app.state()['workflow']['comparisons'][0]['excluded'])
        with urlopen(self.url+f"/api/drafts/quicklister?currency=USD&id={draft['id']}") as response:self.assertEqual(response.status,200)

    def test_supplier_offer_to_comparison_draft_and_quicklister(self):
        import csv,io
        data={'release_id':900000001,'vendor':'TEST SUPPLIER','source_url':'https://example.com/test-only','amount':'4500','currency':'JPY','media_cond':'Very Good (VG)','sleeve_cond':'Very Good Plus (VG+)','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7','sale_price':'80','sale_currency':'USD'}
        with self.post('/api/offers',data):pass
        comparison=self.app.state()['workflow']['comparisons'][0]
        self.assertTrue(comparison['ready']);self.assertEqual(comparison['net_twd'],'612.80')
        tables,formulas=sheet_sync.build_tables(self.settings)
        self.assertEqual(len(tables['Sources'][0]),len(tables['Sources'][1]))
        self.assertEqual(len(tables['Discogs'][0]),len(tables['Discogs'][1]))
        self.assertEqual(tables['Sources'][1][10:15],[80.0,'USD',False,True,7])
        self.assertIn((1,11),formulas)
        with self.post('/api/drafts',{**data,'price':'80','currency':'USD'}):pass
        draft=self.app.state()['workflow']['drafts'][0]
        self.assertEqual(draft['owned_confirmed'],0)
        with urlopen(self.url+f"/api/drafts/quicklister?currency=USD&id={draft['id']}") as response:
            rows=list(csv.DictReader(io.StringIO(response.read().decode())))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['price'],'80')
        self.assertIn('Dispatch within 7 days',rows[0]['comments'])
        with self.assertRaises(HTTPError) as err:
            urlopen(self.url+f"/api/drafts/quicklister?currency=JPY&id={draft['id']}")
        self.assertEqual(err.exception.code,400);err.exception.close()

    def test_remote_auth_preflight_and_csv(self):
        import os
        from unittest.mock import patch
        from remote_access import RemoteAccess
        token='x'*40;origin='https://music-business.vercel.app'
        with patch.dict(os.environ,{'REMOTE_ACCESS_TOKEN':token,'FRONTEND_ORIGIN':origin,'PUBLIC_API_ORIGIN':'https://api.example.com'}):
            self.app.access=RemoteAccess()
        h={'Host':'api.example.com','Origin':origin}
        with urlopen(Request(self.url+'/api/state',headers=h,method='OPTIONS')) as r:
            self.assertEqual(r.status,204);self.assertEqual(r.headers['Access-Control-Allow-Origin'],origin)
        for path in ['/api/state','/api/drafts/export']:
            with self.assertRaises(HTTPError) as error:urlopen(Request(self.url+path,headers=h))
            self.assertEqual(error.exception.code,401);error.exception.close()
            with urlopen(Request(self.url+path,headers={**h,'Authorization':'Bearer '+token})) as r:
                self.assertEqual(r.status,200);self.assertEqual(r.headers['Access-Control-Allow-Origin'],origin)

if __name__=='__main__':unittest.main()
