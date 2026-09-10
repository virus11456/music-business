import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from config import Settings
from db import init,connect
from fx import refresh_reference,business_day

class ReferenceFXTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'fx.db');init(self.s.db_path)
  self.payload={'result':'success','base_code':'USD','time_last_update_unix':int(datetime.now(timezone.utc).timestamp()),'rates':{'USD':1,'JPY':150,'EUR':.9,'GBP':.8,'TWD':30}}
 def tearDown(self):self.tmp.cleanup()
 def test_cross_rate_and_manual_override_preserved(self):
  with connect(self.s.db_path) as c:c.execute('INSERT INTO fx_rates VALUES(?,?,?,?)',('USD',business_day(),'31','manual'))
  refresh_reference(self.s,lambda _:self.payload)
  with connect(self.s.db_path) as c:
   self.assertEqual(c.execute("SELECT twd_per_unit FROM fx_rates WHERE currency='JPY'").fetchone()[0],'0.2')
   self.assertEqual(c.execute("SELECT twd_per_unit FROM fx_rates WHERE currency='USD'").fetchone()[0],'31')
  self.assertTrue(refresh_reference(self.s,lambda _:self.fail('same-day FX must be cached'))['cached'])
 def test_future_or_invalid_payload_is_not_stored(self):
  self.payload['time_last_update_unix']=int((datetime.now(timezone.utc)+timedelta(days=2)).timestamp())
  with self.assertRaises(ValueError):refresh_reference(self.s,lambda _:self.payload)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM fx_rates').fetchone()[0],0)
