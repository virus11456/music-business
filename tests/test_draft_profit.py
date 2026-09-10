import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from config import Settings
from db import init,connect
from server import Dashboard
import demo

class DraftProfitTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);self.app=Dashboard(self.s)
  self.app.mutate('/api/offers',{'release_id':900000001,'vendor':'TEST','source_url':'https://example.com/test','amount':'4500','currency':'JPY','sale_price':'80','sale_currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7'})
  self.app.mutate('/api/drafts/batch',{'offer_ids':[1]})
 def tearDown(self):self.tmp.cleanup()
 def review(self):return self.app.state()['workflow']['drafts'][0]['profit_review']
 def test_actual_draft_price_used_without_changing_offer(self):
  self.assertEqual(self.review()['net_twd'],'612.80')
  with connect(self.s.db_path) as c:c.execute("UPDATE listing_drafts SET price='40'")
  r=self.review();self.assertEqual(r['gross_twd'],'290.00');self.assertEqual(r['net_twd'],'-513.60');self.assertFalse(r['ready']);self.assertIn('未達淨利門檻',r['issues'])
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT sale_price FROM sourcing_offers').fetchone()[0],'80')
 def test_fee_change_rechecks_existing_draft(self):
  self.app.mutate('/api/assumptions',{'fee_pct':'.12','shipping':'1600','packing':'50','reserve':'0','min_margin':'.15'})
  self.assertEqual(self.review()['net_twd'],'-387.20');self.assertFalse(self.review()['ready'])
 def test_missing_fx_and_source_do_not_invent_profit(self):
  with connect(self.s.db_path) as c:c.execute("DELETE FROM fx_rates WHERE currency='JPY'")
  r=self.review();self.assertIsNone(r['net_twd']);self.assertIn('成本缺有效匯率',r['issues'])
  with connect(self.s.db_path) as c:c.execute('UPDATE listing_drafts SET source_offer_id=NULL')
  r=self.review();self.assertIsNone(r['net_twd']);self.assertFalse(r['ready']);self.assertIn('無法估算利潤',r['issues'][0])
 def test_stale_market_and_changed_source_remain_visible(self):
  old=(datetime.now(timezone.utc)-timedelta(hours=49)).isoformat()
  with connect(self.s.db_path) as c:
   c.execute('UPDATE snapshots SET captured_at=?',(old,))
   c.execute('UPDATE listing_drafts SET created_at=?',(old,))
  r=self.review();self.assertFalse(r['ready']);self.assertIn('行情超過兩天',r['issues']);self.assertIn('來源報價已更新，請重新確認草稿',r['issues'])
