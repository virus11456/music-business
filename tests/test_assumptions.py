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
