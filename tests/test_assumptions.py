import unittest,tempfile
from decimal import Decimal
from pathlib import Path
from config import Settings
from db import init,connect
import demo
from server import Dashboard

class AssumptionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'qa.db';self.s=Settings(db_path=self.path);init(self.path);demo.seed(self.s);self.app=Dashboard(self.s)
  self.values={'fee_pct':'.10','shipping':'100','packing':'20','reserve':'30','min_margin':'.25'}
  self.app.mutate('/api/offers',{'release_id':900000001,'vendor':'TEST','source_url':'https://example.com/test','amount':'4500','currency':'JPY','sale_price':'80','sale_currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7'})
 def tearDown(self):self.tmp.cleanup()
 def test_saved_settings_change_profit_and_survive_restart(self):
  self.app.mutate('/api/assumptions',self.values)
  row=self.app.state()['workflow']['comparisons'][0]
  self.assertEqual(row['net_twd'],'1164.00');self.assertTrue(row['ready'])
  restarted=Dashboard(Settings(db_path=self.path))
  self.assertEqual(restarted.state()['assumptions']['shipping'],'100')
  self.assertEqual(restarted.state()['workflow']['comparisons'][0]['net_twd'],'1164.00')
 def test_higher_threshold_blocks_batch(self):
  self.app.mutate('/api/assumptions',{**self.values,'min_margin':'.9'})
  self.assertFalse(self.app.state()['workflow']['comparisons'][0]['ready'])
  with self.assertRaises(ValueError):self.app.mutate('/api/drafts/batch',{'offer_ids':[1]})
 def test_invalid_settings_leave_existing_values_unchanged(self):
  before=self.app.state()['assumptions']
  for key,value in [('fee_pct','1'),('shipping','-1'),('reserve','NaN'),('min_margin','1.01'),('packing','Infinity')]:
   with self.subTest(key=key),self.assertRaises(ValueError):self.app.mutate('/api/assumptions',{**self.values,key:value})
  self.assertEqual(self.app.state()['assumptions'],before)
  with connect(self.path) as c:self.assertIsNone(c.execute("SELECT 1 FROM meta WHERE key='business_assumptions'").fetchone())

class PaymentFeeTests(AssumptionTests):
 def test_paypal_percentage_and_fixed_fee_reduce_net(self):
  from decimal import Decimal
  self.app.mutate('/api/assumptions',self.values)
  before=self.app.state()['workflow']['comparisons'][0]
  self.app.mutate('/api/assumptions',{**self.values,'payment_pct':'.069','payment_fixed':'10'})
  after=self.app.state()['workflow']['comparisons'][0]
  sale=Decimal(after['sale_twd'])
  self.assertEqual(Decimal(before['net_twd'])-Decimal(after['net_twd']),(sale*Decimal('.069')+10).quantize(Decimal('.01')))
  self.assertEqual(Decimal(after['fees_twd']),(sale*Decimal('.169')+10+150).quantize(Decimal('.01')))
  saved=Dashboard(Settings(db_path=self.path)).state()['assumptions']
  self.assertEqual((saved['payment_pct'],saved['payment_fixed']),('0.069','10'))
 def test_settings_saved_before_the_split_keep_their_combined_rate(self):
  import json
  with connect(self.path) as c:c.execute("INSERT OR REPLACE INTO meta VALUES('business_assumptions',?)",(json.dumps(self.values),))
  s=Settings(db_path=self.path)
  self.assertEqual((s.fee_pct,s.payment_pct,s.payment_fixed),(Decimal('.10'),0,0))
 def test_combined_rate_must_stay_below_one_and_payment_not_negative(self):
  for extra in ({'fee_pct':'.5','payment_pct':'.5'},{'payment_pct':'-0.01'},{'payment_fixed':'-1'}):
   with self.subTest(extra=extra),self.assertRaises(ValueError):self.app.mutate('/api/assumptions',{**self.values,**extra})

class OrderFeeTests(AssumptionTests):
 def settings(self,**values):
  s=Settings(db_path=self.path)
  base={'fee_pct':'.09','payment_pct':'.044','payment_fixed':'.30','conversion_pct':'0','tax_pct':'0','buyer_shipping':'0','shipping':'0','packing':'0','reserve':'0'}
  for k,v in {**base,**values}.items():setattr(s,k,Decimal(v))
  return s
 def test_real_discogs_paypal_statements_are_reproduced(self):
  import config
  # Three PayPal statements for Discogs orders (USD): item, buyer shipping, buyer tax, seller net.
  for item,ship,tax,net in (('325','28','28.24','304.16'),('19','28','10.81','39.93'),('15','13','5.60','23.70')):
   with self.subTest(item=item):
    s=self.settings(buyer_shipping=ship,tax_pct=str(Decimal(tax)/(Decimal(item)+Decimal(ship))))
    self.assertEqual((Decimal(item)-config.fees(s,Decimal(item))).quantize(Decimal('.01')),Decimal(net))
 def test_conversion_applies_after_discogs_and_paypal(self):
  import config
  s=self.settings(conversion_pct='.025')
  # 100 sale: Discogs 9, PayPal 4.70, conversion 2.5% of 86.30.
  self.assertEqual(config.fees(s,Decimal(100)).quantize(Decimal('.0001')),(Decimal('13.70')+Decimal('86.30')*Decimal('.025')).quantize(Decimal('.0001')))
 def test_buyer_shipping_offsets_postage_and_is_saved(self):
  self.app.mutate('/api/assumptions',self.values)
  before=Decimal(self.app.state()['workflow']['comparisons'][0]['net_twd'])
  self.app.mutate('/api/assumptions',{**self.values,'buyer_shipping':'100'})
  after=Decimal(self.app.state()['workflow']['comparisons'][0]['net_twd'])
  # Discogs takes 10% of the shipping charged too, so the buyer's NT$100 adds NT$90.
  self.assertEqual(after-before,Decimal('90.00'))
  self.assertEqual(Dashboard(Settings(db_path=self.path)).state()['assumptions']['buyer_shipping'],'100')
 def test_order_fields_are_validated(self):
  for extra in ({'tax_pct':'1.01'},{'conversion_pct':'.9'},{'buyer_shipping':'-1'}):
   with self.subTest(extra=extra),self.assertRaises(ValueError):self.app.mutate('/api/assumptions',{**self.values,**extra})

class FormatShippingTests(AssumptionTests):
 def test_cd_and_cassette_use_their_own_shipping_and_fall_back_when_blank(self):
  import config
  self.app.mutate('/api/assumptions',{**self.values,'buyer_shipping':'900','shipping':'600','buyer_shipping_cd':'420','shipping_cd':'250','buyer_shipping_cassette':'','shipping_cassette':''})
  s=Settings(db_path=self.path)
  self.assertEqual(config.shipping_for(s,'Vinyl'),(Decimal('900'),Decimal('600')))
  self.assertEqual(config.shipping_for(s,'CD'),(Decimal('420'),Decimal('250')))
  self.assertEqual(config.shipping_for(s,'Cassette'),(Decimal('900'),Decimal('600')))  # blank: same as vinyl
  self.assertEqual(config.shipping_for(s,None),(Decimal('900'),Decimal('600')))
  # Same sale: the CD keeps less buyer shipping but pays less postage.
  self.assertNotEqual(config.fees(s,Decimal(1000),'CD'),config.fees(s,Decimal(1000),'Vinyl'))
  saved=Dashboard(Settings(db_path=self.path)).state()['assumptions']
  self.assertEqual((saved['buyer_shipping_cd'],saved['shipping_cd'],saved['shipping_cassette']),('420','250',''))
 def test_negative_format_shipping_is_rejected(self):
  with self.assertRaises(ValueError):self.app.mutate('/api/assumptions',{**self.values,'shipping_cd':'-1'})

class ImportCostTests(AssumptionTests):
 def test_platform_import_cost_is_added_only_to_listed_price_estimates(self):
  import comparisons,config
  from db import now
  self.app.mutate('/api/assumptions',{**self.values,'import_cost_jp':'700','import_cost_overseas':'800','import_cost_tw':'0'})
  s=Settings(db_path=self.path)
  self.assertEqual((config.import_cost(s,'yahoo_jp'),config.import_cost(s,'rakuten'),config.import_cost(s,'ebay'),config.import_cost(s,'ruten'),config.import_cost(s,'other')),(Decimal('700'),Decimal('700'),Decimal('800'),Decimal('0'),0))
  source={'id':7,'platform':'yahoo_jp','external_id':'a7','title':'Record LP','artist':'','format':'LP','catalog_no':'','price':'1000','currency':'JPY',
          'price_kind':'listed','availability':'即決價','source_url':'https://auctions.yahoo.co.jp/jp/auction/a7','captured_at':now()}
  o={'id':None,'release_id':900000001,'title':'Japan pressing','vendor':'yahoo_jp','source_url':source['source_url'],'version_confirmed':0,'owned_confirmed':0,
     'sale_price':None,'sale_currency':None,'amount':None,'currency':'JPY','media_cond':'未確認','sleeve_cond':'未確認','recorded_at':now()}
  with connect(self.path) as c:row=comparisons.calculate(c,s,o,source,False)
  self.assertEqual(row['import_twd'],'700.00')
  self.assertEqual(Decimal(row['gross_twd']),Decimal(row['sale_twd'])-Decimal(row['source_twd'])-700)
  self.assertIn('依來源標價＋設定的進貨附加成本估算',row['issues'])
  # A confirmed total cost already includes everything: no extra.
  self.assertIsNone(self.app.state()['workflow']['comparisons'][0].get('import_twd'))
  self.assertEqual(Dashboard(Settings(db_path=self.path)).state()['assumptions']['import_cost_jp'],'700')
