import tempfile,unittest
from pathlib import Path
from db import init,connect,now
from config import Settings
import demo,workflow,platforms,matching,comparisons
from server import release_id,required
from cli import currency
class ComparisonTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);workflow.init_workflow(self.s);platforms.init(self.s);matching.init(self.s)
  self.data={'release_id':'900000001','vendor':'Test','source_url':'https://example.com/item','amount':'4500','currency':'JPY','media_cond':'Near Mint (NM or M-)','sleeve_cond':'Near Mint (NM or M-)','version_confirmed':'yes','owned_confirmed':'yes','sale_price':'75','sale_currency':'USD'}
 def tearDown(self):self.tmp.cleanup()
 def save(self):
  with connect(self.s.db_path) as c:workflow.save_offer(c,self.data,release_id,currency,required)
 def test_gross_net_and_ready(self):
  self.save();r=comparisons.build(self.s)[0]
  self.assertEqual(r['sale_twd'],'2400.00');self.assertEqual(r['cost_twd'],'990.00');self.assertEqual(r['gross_twd'],'1410.00');self.assertEqual(r['fees_twd'],'938.00');self.assertEqual(r['net_twd'],'472.00');self.assertTrue(r['ready'])
 def test_unowned_cannot_be_ready(self):
  self.data.pop('owned_confirmed');self.save();r=comparisons.build(self.s)[0];self.assertFalse(r['ready']);self.assertIn('尚未確認持有商品',r['issues'])
 def test_missing_fx_no_fake_profit(self):
  self.save()
  with connect(self.s.db_path) as c:c.execute("DELETE FROM fx_rates WHERE currency='JPY'")
  r=comparisons.build(self.s)[0];self.assertIsNone(r['gross_twd']);self.assertFalse(r['ready'])
 def test_update_offer_does_not_duplicate(self):
  self.save();self.data.update(offer_id='1',amount='9000');self.save();rows=comparisons.build(self.s);self.assertEqual(len(rows),1);self.assertFalse(rows[0]['ready']);self.assertIn('未達淨利門檻',rows[0]['issues'])
 def test_stale_offer_cannot_be_ready(self):
  self.save()
  with connect(self.s.db_path) as c:c.execute("UPDATE sourcing_offers SET recorded_at='2020-01-01T00:00:00+00:00'")
  self.assertFalse(comparisons.build(self.s)[0]['ready'])
 def test_missing_sale_confirmation(self):
  self.data.pop('sale_price');self.save();r=comparisons.build(self.s)[0];self.assertEqual(r['net_twd'],'472.00');self.assertFalse(r['ready']);self.assertIn('待確認預定售價',r['issues'])
