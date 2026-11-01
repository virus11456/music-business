from decimal import Decimal
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
  self.data.pop('owned_confirmed');self.save();r=comparisons.build(self.s)[0];self.assertFalse(r['ready']);self.assertIn('待確認可採購庫存與出貨時間',r['issues'])
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

 def test_confirmed_supplier_does_not_require_ownership(self):
  self.data.pop('owned_confirmed');self.data.update(supply_confirmed='yes',dispatch_days='7');self.save()
  self.assertTrue(comparisons.build(self.s)[0]['ready'])
  with connect(self.s.db_path) as c:
   workflow.save_draft(c,{**self.data,'price':'75'},release_id,currency,required)
   row=c.execute('SELECT * FROM listing_drafts').fetchone()
   self.assertEqual(row['owned_confirmed'],0);self.assertEqual(row['supply_confirmed'],1);self.assertEqual(row['dispatch_days'],7)

 def test_usd_reference_and_missing_rate(self):
  self.data.update(sale_price='640',sale_currency='TWD');self.save()
  self.assertEqual(Decimal(comparisons.build(self.s)[0]['sale_usd']),Decimal('20'))
  with connect(self.s.db_path) as c:c.execute("DELETE FROM fx_rates WHERE currency='USD'")
  self.assertIsNone(comparisons.build(self.s)[0]['sale_usd'])
  self.data.update(offer_id='1',sale_price='30',sale_currency='USD');self.save()
  self.assertEqual(comparisons.build(self.s)[0]['sale_usd'],'30')

 def test_manual_cost_timestamp_is_distinct_from_missing_source(self):
  self.save();r=comparisons.build(self.s)[0]
  self.assertIsNone(r['source_at']);self.assertEqual(r['cost_at'],r['offer']['recorded_at'])

class TitleCatalogTests(ComparisonTests):
 def source(self,title):
  return {'id':7,'platform':'yahoo_jp','external_id':'a7','title':title,'artist':'','format':'未確認','catalog_no':'','price':'1000','currency':'JPY',
          'price_kind':'listed','availability':'即決價','source_url':'https://auctions.yahoo.co.jp/jp/auction/a7','captured_at':now()}
 def row(self,title):
  o={'id':None,'release_id':900000001,'title':'Japan pressing','vendor':'yahoo_jp','source_url':'https://auctions.yahoo.co.jp/jp/auction/a7','version_confirmed':0,'owned_confirmed':0,
     'sale_price':None,'sale_currency':None,'amount':None,'currency':'JPY','media_cond':'未確認','sleeve_cond':'未確認','recorded_at':now()}
  with connect(self.s.db_path) as c:return comparisons.calculate(c,self.s,o,self.source(title),False)
 def test_catalogue_number_without_hyphen_in_title_is_read_as_the_release_number(self):
  r=self.row('LP DEMO900000001 帯付')
  self.assertEqual((r['source_catalog_no'],r['source_catalog_from_title']),('DEMO-900000001',True))
  r=self.row('LP DEMO-900000002')
  self.assertEqual(r['source_catalog_no'],'')  # not this release's number: no catalogue claimed
