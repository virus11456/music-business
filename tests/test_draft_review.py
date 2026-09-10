import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from db import init,connect
from config import Settings
import demo,workflow
from server import release_id,required
from cli import currency

class DraftReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);workflow.init_workflow(self.s)
  self.data={'release_id':'900000001','vendor':'TEST','source_url':'https://example.com/test','amount':'4500','currency':'USD','price':'80','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7'}
  with connect(self.s.db_path) as c:
   workflow.save_offer(c,self.data,release_id,currency,required)
   self.data['source_offer_id']=c.execute('SELECT id FROM sourcing_offers').fetchone()[0]
   workflow.save_draft(c,self.data,release_id,currency,required)
   self.id=c.execute('SELECT id FROM listing_drafts').fetchone()[0]
 def tearDown(self):self.tmp.cleanup()
 def export(self):return workflow.quicklister_csv(self.s,[self.id],'USD')
 def test_edit_preserves_id_and_changes_export(self):
  with connect(self.s.db_path) as c:workflow.save_draft(c,{**self.data,'draft_id':self.id,'price':'85','note':'TEST updated'},release_id,currency,required)
  self.assertIn('85,',self.export());self.assertIn('TEST updated',self.export())
  self.assertEqual(len(workflow.get_workflow(self.s)['drafts']),1)
 def test_stale_draft_is_visible_and_blocked_then_reconfirmed(self):
  old=(datetime.now(timezone.utc)-timedelta(hours=49)).isoformat()
  with connect(self.s.db_path) as c:c.execute('UPDATE listing_drafts SET created_at=?',(old,))
  self.assertTrue(workflow.get_workflow(self.s)['drafts'][0]['export_issues'])
  with self.assertRaisesRegex(ValueError,'48 小時'):self.export()
  with connect(self.s.db_path) as c:workflow.save_draft(c,{**self.data,'draft_id':self.id},release_id,currency,required)
  self.assertIn('80,',self.export())
 def test_revoked_source_cannot_be_bypassed_by_redrafting(self):
  with connect(self.s.db_path) as c:
   c.execute('UPDATE sourcing_offers SET supply_confirmed=0')
   workflow.save_draft(c,{**self.data,'draft_id':self.id},release_id,currency,required)
  with self.assertRaisesRegex(ValueError,'取消供貨'):self.export()
 def test_link_cannot_be_removed_on_edit(self):
  with connect(self.s.db_path) as c:
   with self.assertRaisesRegex(ValueError,'不能更換'):workflow.save_draft(c,{**self.data,'draft_id':self.id,'source_offer_id':''},release_id,currency,required)
 def test_updated_source_requires_review(self):
  older=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
  with connect(self.s.db_path) as c:c.execute('UPDATE listing_drafts SET created_at=?',(older,))
  with self.assertRaisesRegex(ValueError,'報價已更新'):self.export()
