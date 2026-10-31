"""Discogs scarcity scan and scarcity-list sourcing: thresholds, budgets, album grouping, queue hygiene."""
import json,tempfile,unittest
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from config import Settings
from db import init,connect,now,snapshot
import ingest,platforms,matching,source_queue,demand_queue,sourcing,scheduler

def release(rid,want,have,lowest=12.5,sale=3,title='Album',artist='Artist',fmt='CD'):
    return {'id':rid,'title':title,'artists':[{'name':artist}],'formats':[{'name':fmt}],'country':'Japan','year':1980,
            'labels':[{'name':'Label','catno':f'CAT-{rid}'}],'community':{'want':want,'have':have},'lowest_price':lowest,'num_for_sale':sale}

class Client:
    def __init__(self,pages,releases):self.pages,self.releases,self.calls=pages,releases,[]
    def get(self,path,params=None):
        self.calls.append(path)
        if path=='/database/search':return self.pages[params['page']]
        return self.releases[int(path.rsplit('/',1)[1])]

class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db',token='t');init(self.s.db_path)
        with connect(self.s.db_path) as c:c.execute("INSERT INTO scan_targets(name,query_params,min_want_have) VALUES('日本卡帶','{\"format\":\"Cassette\",\"country\":\"Japan\"}',2)")
    def tearDown(self):self.tmp.cleanup()
    def releases(self):
        with connect(self.s.db_path) as c:return {r[0]:r[1] for r in c.execute('SELECT release_id,source_theme FROM releases')}
    def test_search_counts_rule_out_before_release_call_and_release_decides(self):
        page={'pagination':{'pages':2},'results':[
            {'type':'release','id':1,'community':{'want':40,'have':1}},    # below Want 50: no release call
            {'type':'release','id':2,'community':{'want':90,'have':60}},   # ratio 1.5 < 2: no release call
            {'type':'release','id':3,'community':{'want':120,'have':10}},  # passes, release confirms
            {'type':'release','id':4},                                     # no counts in search: release decides (fails)
            {'type':'release','id':5,'community':{'want':80,'have':0}}]}   # passes; Have 0 counts as 1
        client=Client({1:page},{3:release(3,120,10),4:release(4,10,10),5:release(5,80,0,lowest=None,sale=0)})
        result=ingest.scan(self.s,pages=1,client=client)
        self.assertEqual(client.calls,['/database/search','/releases/3','/releases/4','/releases/5'])
        self.assertEqual(result,{'discovered':2,'failed':0,'requests':4,'prefiltered':2,'budget_exhausted':False})
        self.assertEqual(self.releases(),{3:'日本卡帶',5:'日本卡帶'})
        with connect(self.s.db_path) as c:
            snaps={r['release_id']:(r['lowest_price'],r['currency'],r['num_for_sale'],r['want'],r['have']) for r in c.execute('SELECT * FROM snapshots')}
            # The page dropped below Want 50 (results are most-wanted first), so the next run starts the first year.
            self.assertEqual(json.loads(c.execute("SELECT value FROM meta WHERE key LIKE 'scan_cursor:%'").fetchone()[0]),{'segment':1,'page':1})
        self.assertEqual(snaps,{3:('12.5','USD',3,120,10),5:(None,None,0,80,0)})
    def test_budget_and_new_release_cap_stop_mid_page_without_skipping_it(self):
        page={'pagination':{'pages':5},'results':[{'type':'release','id':i,'community':{'want':100,'have':1}} for i in (1,2,3)]}
        client=Client({1:page},{i:release(i,100,1) for i in (1,2,3)})
        result=ingest.scan(self.s,pages=3,client=client,budget=3)
        self.assertEqual((result['discovered'],result['requests'],result['budget_exhausted']),(2,3,True))
        with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT next_page FROM scan_targets').fetchone()[0],1)
        # Next run resumes the same page; saved releases are skipped, the third is added, the page then advances.
        client=Client({1:page,2:{'pagination':{'pages':5},'results':[]}},{i:release(i,100,1) for i in (1,2,3)})
        result=ingest.scan(self.s,pages=1,client=client,max_new=5)
        self.assertEqual((result['discovered'],client.calls),(1,['/database/search','/releases/3']))
        with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT next_page FROM scan_targets').fetchone()[0],2)
        client=Client({2:{'pagination':{'pages':5},'results':[{'type':'release','id':i,'community':{'want':100,'have':1}} for i in (7,8)]}},{i:release(i,100,1) for i in (7,8)})
        self.assertEqual(ingest.scan(self.s,pages=1,client=client,max_new=1)['discovered'],1)
        self.assertEqual(sorted(self.releases()),[1,2,3,7])

class SegmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db',token='t');init(self.s.db_path)
    def tearDown(self):self.tmp.cleanup()
    def target(self,params):
        with connect(self.s.db_path) as c:c.execute('INSERT INTO scan_targets(name,query_params,min_want_have) VALUES(?,?,2)',('t',json.dumps(params)))
    def test_sorted_by_want_and_walks_years_after_the_overall_top(self):
        self.target({'format':'Vinyl','country':'Japan'})
        seen=[]
        class Sorted:
            def get(inner,path,params=None):
                seen.append({k:params.get(k) for k in ('year','page','sort','sort_order')})
                # Overall: two pages above the floor, then a page that dips under it. Each year: one page under it.
                if params.get('year') is None:
                    want={1:500,2:300,3:40}[params['page']]
                else:want=30
                return {'pagination':{'pages':200},'results':[{'type':'release','id':params['page']*1000+int(params.get('year') or 0),'community':{'want':want,'have':want}}]}
        ingest.scan(self.s,pages=6,client=Sorted())
        self.assertTrue(all(p['sort']=='want' and p['sort_order']=='desc' for p in seen))
        self.assertEqual([(p['year'],p['page']) for p in seen],[(None,1),(None,2),(None,3),('1950',1),('1951',1),('1952',1)])
        with connect(self.s.db_path) as c:cursor=json.loads(c.execute("SELECT value FROM meta WHERE key LIKE 'scan_cursor:%'").fetchone()[0])
        self.assertEqual(cursor,{'segment':4,'page':1})
    def test_artist_target_has_one_segment_and_wraps_after_the_last_page(self):
        self.target({'artist':'Casiopea','country':'Japan','format':'CD'})
        seen=[]
        class Two:
            def get(inner,path,params=None):
                seen.append((params.get('year'),params['page']))
                return {'pagination':{'pages':2},'results':[{'type':'release','id':params['page'],'community':{'want':900,'have':900}}]}
        ingest.scan(self.s,pages=5,client=Two())
        self.assertEqual(seen,[(None,1),(None,2)])  # stops after a full cycle instead of looping
        ingest.scan(self.s,pages=1,client=Two())
        self.assertEqual(seen[-1],(None,1))
    def test_years_cover_through_this_year(self):
        from datetime import date
        years=ingest.segments({'format':'Cassette'})
        self.assertEqual((years[0],years[1],years[-1]),(None,'1950',str(date.today().year)))
        self.assertEqual(ingest.segments({'format':'CD','year':'1975'}),[None])

class SharedBudgetTests(ScanTests):
    def test_each_target_gets_an_equal_share_of_the_night(self):
        with connect(self.s.db_path) as c:c.execute("INSERT INTO scan_targets(name,query_params,min_want_have) VALUES('日本黑膠','{\"format\":\"Vinyl\",\"country\":\"Japan\"}',2)")
        pages={1:{'pagination':{'pages':9},'results':[{'type':'release','id':i,'community':{'want':100,'have':1}} for i in range(1,11)]}}
        class Split(Client):
            def get(inner,path,params=None):
                if path=='/database/search' and params['format']=='Vinyl':
                    inner.calls.append('vinyl-search');return {'pagination':{'pages':9},'results':[{'type':'release','id':i,'community':{'want':100,'have':1}} for i in range(11,21)]}
                return super().get(path,params)
        client=Split(pages,{i:release(i,100,1) for i in range(1,21)})
        result=ingest.scan(self.s,pages=5,client=client,max_new=6)
        with connect(self.s.db_path) as c:themes=[r[0] for r in c.execute('SELECT source_theme FROM releases')]
        self.assertEqual((result['discovered'],themes.count('日本卡帶'),themes.count('日本黑膠'),result['budget_exhausted']),(6,3,3,True))

class DemandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db',token='t');init(self.s.db_path)
        platforms.init(self.s);matching.init(self.s);source_queue.init(self.s)
        rows=[(1,'The Beatles','Rubber Soul','CD','TOCP-1',318,1,3),(2,'The Beatles','Rubber Soul','Vinyl','AP-8156',719,3,0),
              (3,'Casiopea','Mint Jams','CD','ALCA-1',286,8,5),(4,'Queen','Jazz','CD','X-1',40,1,0),(5,'ABBA','Arrival','CD','Y-1',500,400,2)]
        with connect(self.s.db_path) as c:
            for rid,artist,title,fmt,catno,want,have,sale in rows:
                c.execute('INSERT INTO releases(release_id,title,artist,year,country,format,catno,added_at) VALUES(?,?,?,?,?,?,?,?)',(rid,title,artist,1980,'Japan',fmt,catno,now()))
                snapshot(c,rid,now(),'10','USD',sale,have,want)
    def tearDown(self):self.tmp.cleanup()
    def test_versions_with_plenty_for_sale_are_left_out(self):
        with connect(self.s.db_path) as c:snapshot(c,3,'2026-11-01T00:00:00+00:00','10','USD',12,8,286)
        self.assertEqual([a['title'] for a in demand_queue.scarcity(self.s)],['Rubber Soul'])
        self.assertEqual([a['title'] for a in demand_queue.scarcity(replace(self.s,demand_max_for_sale=20))],['Rubber Soul','Mint Jams'])
    def test_scarcity_groups_versions_by_album_and_puts_unsold_first(self):
        albums=demand_queue.scarcity(self.s)
        self.assertEqual([(a['artist'],a['title'],sorted(a['release_ids'])) for a in albums],[('The Beatles','Rubber Soul',[1,2]),('Casiopea','Mint Jams',[3])])
        self.assertTrue(albums[0]['unsold']);self.assertEqual(albums[0]['ratio'],318)
    def fake_search(self,s,query,selected,**kw):
        stamp=now()
        with connect(s.db_path) as c:
            for i,(fmt,title) in enumerate([('CD','The Beatles Rubber Soul CD TOCP-1'),('LP','The Beatles Rubber Soul LP'),('CD','Unrelated thing')]):
                c.execute('INSERT INTO platform_candidates(platform,external_id,query,title,artist,format,catalog_no,price,currency,price_kind,availability,source_url,captured_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,external_id) DO UPDATE SET captured_at=excluded.captured_at',
                          ('ruten',f'{query[:3]}{i}',query,title,'',fmt,'','500','TWD','listed','未確認',f'https://www.ruten.com.tw/item/show?{i}',stamp))
            c.execute('INSERT INTO platform_runs(platform,query,count,status,recorded_at) VALUES(?,?,?,?,?)',('ruten',query,3,'完成',stamp))
        return {'candidates':3,'failed_platforms':0,'platforms':[{'platform':'ruten','count':3,'status':'success'}]}
    def test_one_search_per_album_links_versions_and_keeps_results_out_of_reverse_queue(self):
        with patch('demand_queue.sourcing.platforms.search',side_effect=self.fake_search) as search:
            result=demand_queue.run(self.s,selected=['ruten'])
        self.assertEqual([c.args[1] for c in search.call_args_list],['The Beatles Rubber Soul','Casiopea Mint Jams'])
        self.assertEqual((result['albums'],result['versions'],result['eligible_albums'],result['candidates'],result['failed']),(2,3,2,6,0))
        with connect(self.s.db_path) as c:
            links={json.loads(r[0])[0]['release_id'] for r in c.execute("SELECT v.results FROM version_searches v JOIN platform_candidates p ON p.id=v.candidate_id WHERE p.query='The Beatles Rubber Soul'")}
            checks=dict(c.execute('SELECT candidate_id,status FROM source_checks').fetchall())
        self.assertEqual(links,{1,2})  # CD item -> CD version, LP item -> vinyl version
        self.assertEqual(sorted(checks.values()).count('matched'),2)
        self.assertEqual(source_queue.pending_count(self.s),0)
        # Within 7 days the same albums are skipped; after that they are searched again.
        with patch('demand_queue.sourcing.platforms.search',side_effect=self.fake_search) as search:
            again=demand_queue.run(self.s,selected=['ruten'])
        self.assertEqual((again['albums'],again['skipped_recent'],search.call_count),(0,2,0))
        with patch('demand_queue.sourcing.platforms.search',side_effect=self.fake_search) as search:
            later=demand_queue.run(self.s,selected=['ruten'],instant=datetime.now(timezone.utc)+timedelta(days=8))
        self.assertEqual(later['albums'],2)
    def test_album_limit_and_reverse_queue_checks_are_not_overwritten(self):
        with connect(self.s.db_path) as c:
            c.execute("INSERT INTO platform_candidates(id,platform,external_id,query,title,artist,format,catalog_no,price,currency,price_kind,availability,source_url,captured_at) VALUES(99,'ruten','The0','x','x','','CD','','1','TWD','listed','未確認','https://www.ruten.com.tw/item/show?99',?)",(now(),))
            c.execute("INSERT INTO source_checks VALUES(99,'old','unmatched','2026-01-01','2026-01-08T00:00:00+00:00')")
        with patch('demand_queue.sourcing.platforms.search',side_effect=self.fake_search) as search:
            result=demand_queue.run(self.s,limit=1,selected=['ruten'])
        self.assertEqual((result['albums'],search.call_count),(1,1))
        with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT fingerprint FROM source_checks WHERE candidate_id=99').fetchone()[0],'old')

class NightTests(unittest.TestCase):
    def test_night_reports_each_step_and_counts_failures(self):
        s=Settings(db_path=Path(tempfile.mkdtemp())/'t.db')
        with patch('ingest.scan',return_value={'discovered':3,'failed':1,'requests':40,'prefiltered':100,'budget_exhausted':False}) as scan,\
             patch('demand_queue.run',return_value={'albums':2,'failed':0}),patch('analyze.run',return_value={'scores_pruned':5}),\
             patch('sheet_sync.sync',return_value={'synced':True}):
            result=scheduler.night(s)
        self.assertEqual(scan.call_args.kwargs,{'pages':40,'budget':s.scan_budget,'max_new':s.scan_max_new})
        self.assertEqual((result['flow'],result['failed'],result['scores_pruned'],result['sheet_sync']),('demand_night',1,5,{'synced':True}))
        self.assertEqual(set(result['timings']),{'scan','demand','analyze','sheet_sync'})

if __name__=='__main__':unittest.main()
