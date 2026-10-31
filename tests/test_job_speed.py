"""Faster jobs must produce the same records: parallel sites, single-pass matching, warmed responses."""
import json,os,random,re,sqlite3,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from config import Settings
from db import init,connect,now
import demo,workflow,platforms,matching,source_queue,source_refresh,direct_matches
from matching import normalized
from source_match import evidence,source_catalog

def reference_pairs(sources,targets):
    # The pre-optimisation loop, kept verbatim as the behavioural reference.
    result=[]
    for source in sources:
        catalog=normalized(source_catalog(source))
        known_catalog=catalog not in ('','none','na','未確認')
        text=normalized(source['artist']+' '+source['title'])
        for target in targets:
            catalogs=[normalized(x) for x in target['catno'].split(',') if normalized(x) not in ('','none','na','未確認')]
            catalog_match=known_catalog and catalog in catalogs
            if known_catalog and catalogs and not catalog_match:continue
            artist=normalized(re.sub(r'\s+\(\d+\)$','',target['artist']))
            barcode_match=bool(set(__import__('identity_data').source_codes(source))&set(target.get('barcodes',[])))
            if not catalog_match and not barcode_match and (len(artist)<2 or artist not in text):continue
            reasons=evidence(source,target)
            if reasons:result.append([source['id'],target['release_id'],reasons+['已抓取資料直接交叉比對']])
    return result

class DirectMatchTests(unittest.TestCase):
    def test_single_pass_matching_equals_the_reference_loop(self):
        random.seed(7)
        artists=['The Beatles','Queen','ABBA','Prince (2)','A','Pink Floyd']
        targets=[{'release_id':i,'title':f'Album {i%9}','artist':random.choice(artists),'format':random.choice(['Vinyl, LP','CD','Cassette']),
                  'catno':random.choice(['',f'CAT-{i%7:04d}',f'CAT-{i%7:04d}, ALT-{i%3:03d}','none']),'labels':'','barcodes':random.choice([[],['04988006123456']])} for i in range(1,80)]
        sources=[{'id':j,'title':f'{random.choice(artists)} Album {j%9} '+random.choice(['LP','CD','カセット',f'CAT-{j%7:04d} LP','']),'artist':random.choice(['',random.choice(artists)]),
                  'format':random.choice(['LP','CD','','Cassette']),'catalog_no':random.choice(['',f'CAT-{j%7:04d}','未確認']),'barcodes':random.choice([[],['04988006123456'],['4988006123456']]),'labels':''} for j in range(1,160)]
        c=sqlite3.connect(':memory:');c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        expected=reference_pairs(sources,targets)
        self.assertTrue(expected)
        self.assertEqual(direct_matches.pairs(c,sources,targets),expected)
    def test_indexed_matching_equals_the_reference_loop_across_seeds_and_scales(self):
        artists=['The Beatles','Queen','ABBA','Prince (2)','A','Pink Floyd','Casiopea','山下達郎','Sleep']
        for seed in range(5):
            random.seed(seed)
            targets=[{'release_id':i,'title':f'Album {i%13}','artist':random.choice(artists+[None,'']),'format':random.choice(['Vinyl, LP','CD','Cassette']),
                      'catno':random.choice(['',f'CAT-{i%11:04d}',f'CAT-{i%11:04d}, ALT-{i%5:03d}','none','未確認']),'labels':'','barcodes':random.choice([[],['04988006123456'],['4988006000017']])} for i in range(1,300)]
            sources=[{'id':j,'title':f'{random.choice(artists)} Album {j%13} '+random.choice(['LP','CD','カセット',f'CAT-{j%11:04d} LP','ALT-002','']),'artist':random.choice(['',random.choice(artists)]),
                      'format':random.choice(['LP','CD','','Cassette']),'catalog_no':random.choice(['',f'CAT-{j%11:04d}','未確認','none']),'barcodes':random.choice([[],['04988006123456'],['4988006000017']]),'labels':''} for j in range(1,400)]
            safe=[{**t,'artist':t['artist'] or ''} for t in targets]  # the reference loop predates the None-artist guard
            self.assertEqual(direct_matches.compute(sources,targets),reference_pairs(sources,safe),seed)

    def test_release_without_artist_is_skipped_by_name_instead_of_failing(self):
        c=sqlite3.connect(':memory:');c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        targets=[{'release_id':1,'title':'Album','artist':None,'format':'CD','catno':'','labels':'','barcodes':[]},
                 {'release_id':2,'title':'Album','artist':'Queen','format':'CD','catno':'CAT-1','labels':'','barcodes':[]}]
        sources=[{'id':1,'title':'Queen Album CD CAT-1','artist':'','format':'CD','catalog_no':'CAT-1','barcodes':[],'labels':''}]
        self.assertEqual([p[:2] for p in direct_matches.pairs(c,sources,targets)],[[1,2]])

class ParallelRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db');init(self.s.db_path);platforms.init(self.s)
        with connect(self.s.db_path) as c:
            n=1
            for platform,ids in [('tower',['11','12']),('yahoo_tw',['21','22']),('yahoo_jp',['a31','a32'])]:
                for ext in ids:
                    url=platforms.candidate(platform,ext,'',None)['source_url']
                    c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(n,platform,ext,'q','Album','Artist','CD','','100','JPY','fixed','x',url,'2020-01-01T00:00:00+00:00'));n+=1
    def tearDown(self):self.tmp.cleanup()
    def test_sites_run_side_by_side_and_each_site_stays_sequential(self):
        lock=threading.Lock();active={};peak={'all':0};per_site={}
        def fetcher(url):
            host=url.split('/')[2]
            with lock:
                active[host]=active.get(host,0)+1;per_site[host]=max(per_site.get(host,0),active[host])
                peak['all']=max(peak['all'],sum(active.values()))
            time.sleep(.2)
            with lock:active[host]-=1
            return 'not a product page'
        started=time.perf_counter()
        report=source_refresh.run(self.s,fetcher,detail_limit=2,sleeper=lambda s:None)
        elapsed=time.perf_counter()-started
        self.assertEqual([p['platform'] for p in report['platforms']],['ruten','yahoo_tw','yahoo_jp','tower','rottenblues'])
        self.assertEqual(report['attempted'],6);self.assertEqual(report['failed'],6)
        self.assertEqual(set(per_site.values()),{1});self.assertGreaterEqual(peak['all'],2)
        self.assertLess(elapsed,.9)  # sequential would take 6 x 0.2s
        with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM source_refresh_attempts').fetchone()[0],6)

class ParallelCollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'q.db',token='test')
        init(self.s.db_path);demo.seed(self.s);workflow.init_workflow(self.s);platforms.init(self.s);matching.init(self.s);source_queue.init(self.s)
    def tearDown(self):self.tmp.cleanup()
    def test_collection_runs_sites_in_parallel_keeps_order_pages_and_reports_timings(self):
        calls=[]
        def search(settings,query,selected,page=1,full_page=False):
            calls.append((selected[0],page,threading.current_thread().name));time.sleep(.2)
            failed=selected[0]=='ruten'
            return {'candidates':0 if failed else 3,'failed_platforms':int(failed),'platforms':[{'platform':selected[0],'count':3,'status':'failed' if failed else 'success','has_more':selected[0]=='tower'}]}
        with connect(self.s.db_path) as c:c.execute("INSERT INTO source_pages VALUES('Artist','yahoo_jp',4)")
        started=time.perf_counter()
        with patch('source_queue.platforms.search',side_effect=search),patch('source_refresh.run',return_value={'failed':0,'missing':0}),patch('source_queue.analyze.run',return_value={'scored':2,'scores_pruned':7}),patch('source_queue.sheet_sync.sync',return_value={'synced':True}),patch('fx.refresh_reference',return_value={'cached':True}),patch('source_queue.DiscogsClient'):
            result=source_queue.run(self.s,'Artist',['tower','yahoo_jp','ruten'])
        elapsed=time.perf_counter()-started
        self.assertLess(elapsed,.5)
        self.assertEqual([p['platform'] for p in result['collection']['platforms']],['tower','yahoo_jp','ruten'])
        self.assertEqual({(p,pg) for p,pg,_ in calls},{('tower',1),('yahoo_jp',4),('ruten',1)})
        self.assertEqual(result['collection']['failed_platforms'],1)
        with connect(self.s.db_path) as c:pages=dict(c.execute("SELECT platform,next_page FROM source_pages WHERE query='Artist'").fetchall())
        self.assertEqual(pages,{'tower':2,'yahoo_jp':1})  # failed site keeps no page progress
        self.assertEqual(set(result['timings']),{'collect','source_refresh','reverse_match','market','fx','analyze','sheet_sync'})
        self.assertTrue(all(isinstance(v,float) and v>=0 for v in result['timings'].values()))
        self.assertEqual(result['scores_pruned'],7)

class WarmTests(unittest.TestCase):
    def test_warm_prepares_the_signed_in_response(self):
        import sheet_primary
        from sheet_primary import PrimaryStore
        from tests.test_state_performance import Repository
        from server import Dashboard
        store=PrimaryStore(Repository())
        with patch.dict(os.environ,{'DATA_BACKEND':'google_sheets','GOOGLE_SPREADSHEET_ID':'x'*30}),patch.object(sheet_primary,'_store',store):
            app=Dashboard(Settings());app.warm();app.warm()
            for _ in range(300):
                if not app._warming:break
                time.sleep(.01)
            self.assertFalse(app._warming)
            self.assertEqual(app.payload(False,True)[3]['cache'],'hit')
    def test_warm_does_nothing_without_the_sheet_store(self):
        from server import Dashboard
        tmp=tempfile.TemporaryDirectory();s=Settings(db_path=Path(tmp.name)/'w.db');init(s.db_path);demo.seed(s)
        try:
            app=Dashboard(s);app.warm();self.assertFalse(getattr(app,'_warming',False))
        finally:tmp.cleanup()
