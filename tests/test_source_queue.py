import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from db import init,connect,now
from config import Settings
import demo,workflow,platforms,matching,source_queue,comparisons

class SourceQueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db',token='test')
  init(self.s.db_path);demo.seed(self.s);workflow.init_workflow(self.s);platforms.init(self.s);matching.init(self.s);source_queue.init(self.s)
  with connect(self.s.db_path) as c:
   c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(1,'tower','1','test','Test','Artist','CD','','200','JPY','listed','在庫あり','https://tower.jp/item/1',now()))
 def tearDown(self):self.tmp.cleanup()
 def cycle(self,results,limit=20):
  def search(s,cid,client=None):
   with connect(s.db_path) as c:c.execute('INSERT OR REPLACE INTO version_searches VALUES(?,?,?,?)',(cid,'{}',json.dumps(results),now()))
  with patch('source_queue.matching.search',side_effect=search) as search_mock,patch('source_queue.ingest.fetch_one'),patch('source_queue.analyze.run'),patch('source_queue.sheet_sync.sync',return_value={'synced':True}),patch('fx.refresh_reference',return_value={'cached':True}):
   report=source_queue.run(self.s,limit=limit);return report,search_mock.call_count
 def test_catalog_evidence_is_processed_before_ambiguous_titles(self):
  with connect(self.s.db_path) as c:
   c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(2,'tower','2','test','Precise record','Artist','CD','ABC-1','200','JPY','listed','在庫あり','https://tower.jp/item/2',now()))
  result,calls=self.cycle([],limit=1)
  self.assertEqual(calls,1);self.assertEqual(result['pending'],1)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT candidate_id FROM source_checks').fetchone()[0],2)
 def test_negative_results_persist_and_price_changes_do_not_repeat_search(self):
  self.assertEqual(self.cycle([])[1],1)
  self.assertEqual(self.cycle([])[1],0)
  with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET price='250',captured_at=?",(now(),))
  self.assertEqual(self.cycle([])[1],0)
  with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET catalog_no='NEW-1'")
  self.assertEqual(self.cycle([])[1],1)
 def test_expired_negative_retried_and_registered_when_matching_arrives(self):
  self.cycle([])
  with connect(self.s.db_path) as c:
   c.execute("UPDATE source_checks SET retry_at='2000-01-01'")
   c.execute("UPDATE platform_candidates SET title='Moonlight Tokyo',format='Vinyl'")
  result,calls=self.cycle([{'release_id':900000001,'title':'Artist - Moonlight Tokyo','format':'Vinyl','catno':''}])
  self.assertEqual(calls,1);self.assertEqual(result['matched'],1)
 def test_profit_estimate_does_not_require_manual_offer(self):
  with connect(self.s.db_path) as c:
   target=c.execute('SELECT * FROM releases WHERE release_id=900000001').fetchone()
   c.execute('UPDATE platform_candidates SET title=?,format=?',(target['title'],target['format']))
   c.execute('INSERT INTO version_searches VALUES(?,?,?,?)',(1,'{}',json.dumps([{'release_id':900000001,'title':target['title']}]),now()))
  row=comparisons.build(self.s)[0]
  self.assertEqual(row['gross_twd'],'2356.00');self.assertEqual(row['listing_status'],'unlisted');self.assertFalse(row['ready'])
  with connect(self.s.db_path) as c:c.execute('INSERT INTO published_listings VALUES(?,?,?,?)',('https://tower.jp/item/1',900000001,'123',now()))
  row=comparisons.build(self.s)[0];self.assertEqual(row['listing_status'],'listed');self.assertFalse(row['ready'])

 def test_missing_fx_never_invents_profit(self):
  with connect(self.s.db_path) as c:
   target=c.execute('SELECT * FROM releases WHERE release_id=900000001').fetchone()
   c.execute('UPDATE platform_candidates SET title=?,format=?',(target['title'],target['format']))
   c.execute('INSERT INTO version_searches VALUES(?,?,?,?)',(1,'{}',json.dumps([{'release_id':900000001,'title':target['title']}]),now()))
   c.execute('DELETE FROM fx_rates')
  self.assertIsNone(comparisons.build(self.s)[0]['gross_twd'])

 def test_pending_count_includes_changes_and_expired_results(self):
  self.assertEqual(source_queue.pending_count(self.s),1)
  self.cycle([])
  self.assertEqual(source_queue.pending_count(self.s),0)
  with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET price='300'")
  self.assertEqual(source_queue.pending_count(self.s),0)
  with connect(self.s.db_path) as c:c.execute("UPDATE source_checks SET retry_at='2000-01-01'")
  self.assertEqual(source_queue.pending_count(self.s),1)

 def test_cached_identity_still_refreshes_old_market_without_research(self):
  self.cycle([])
  with connect(self.s.db_path) as c:c.execute("UPDATE snapshots SET captured_at='2020-01-01T00:00:00+00:00'")
  with patch('source_queue.matching.search') as search,patch('source_queue.ingest.fetch_one') as fetch,patch('source_queue.analyze.run'),patch('source_queue.sheet_sync.sync',return_value={'synced':True}),patch('fx.refresh_reference',return_value={'cached':True}):
   report=source_queue.run(self.s)
  search.assert_not_called();self.assertGreater(fetch.call_count,0)
  self.assertEqual(report['market_updated'],fetch.call_count);self.assertEqual(report['cached'],1)
  self.assertTrue(report['sheet_sync']['synced'])
