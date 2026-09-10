import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from config import Settings
from db import init,connect
import demo,workflow
from server import Dashboard

class BatchDraftTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);self.app=Dashboard(self.s)
  self.ids=[]
  for fmt in ('Vinyl','CD','Cassette'):
   data={'release_id':900000001,'vendor':'TEST '+fmt,'source_url':'https://example.com/'+fmt,'amount':'4500','currency':'JPY','sale_price':'80','sale_currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7'}
   self.app.mutate('/api/offers',data)
   self.ids.append(self.app.state()['workflow']['offers'][0]['id'])
 def tearDown(self):self.tmp.cleanup()
 def batch(self,ids=None):return self.app.mutate('/api/drafts/batch',{'offer_ids':self.ids if ids is None else ids})
 def test_batch_preserves_existing_edits_and_is_idempotent(self):
  self.assertEqual(self.batch()['created'],3)
  with connect(self.s.db_path) as c:c.execute("UPDATE listing_drafts SET note='TEST edit',price='85'")
  result=self.batch();self.assertEqual(result['created'],0);self.assertEqual(result['skipped'],3)
  self.assertTrue(all(d['note']=='TEST edit' and d['price']=='85' for d in self.app.state()['workflow']['drafts']))
 def test_one_invalid_selection_creates_nothing(self):
  with connect(self.s.db_path) as c:c.execute('UPDATE sourcing_offers SET version_confirmed=0 WHERE id=?',(self.ids[-1],))
  with self.assertRaises(workflow.BatchDraftError):self.batch()
  self.assertEqual(self.app.state()['workflow']['drafts'],[])
 def test_exclusion_rechecked_at_submission(self):
  self.app.mutate('/api/comparisons/exclude',{'release_id':900000001,'source_url':'https://example.com/CD','excluded':True})
  with self.assertRaises(workflow.BatchDraftError):self.batch()
  self.assertEqual(self.app.state()['workflow']['drafts'],[])
 def test_invalid_ids_and_limit(self):
  for ids in ([],[True],[1,1],list(range(1,52)),['1'],[999]):
   with self.subTest(ids=ids),self.assertRaises(workflow.BatchDraftError):self.batch(ids)

 def test_write_failure_rolls_back_and_releases_lock(self):
  original=workflow.save_draft
  calls=0
  def fail_second(*args,**kwargs):
   nonlocal calls
   calls+=1
   if calls==2:raise RuntimeError('TEST simulated storage failure')
   return original(*args,**kwargs)
  with patch('workflow.save_draft',side_effect=fail_second):
   with self.assertRaises(RuntimeError):self.batch()
  self.assertEqual(self.app.state()['workflow']['drafts'],[])
  self.assertEqual(self.batch()['created'],3)
