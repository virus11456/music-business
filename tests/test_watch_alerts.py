import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from db import init,connect
from config import Settings
import demo,watch_alerts,analyze
class WatchAlertsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'test.db');init(self.s.db_path);demo.seed(self.s);self.at=datetime.now(timezone.utc)
  with connect(self.s.db_path) as c:
   self.release=dict(c.execute('SELECT * FROM releases LIMIT 1').fetchone());self.snap=dict(c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(self.release['release_id'],)).fetchone())
   c.execute("INSERT INTO decisions(release_id,decision,target_price,target_currency,decided_at) VALUES(?,'watch','30','USD',?)",(self.release['release_id'],(self.at-timedelta(hours=1)).isoformat()))
  self.snap.update(lowest_price='30',currency='USD',num_for_sale=1,captured_at=self.at.isoformat())
 def tearDown(self):self.tmp.cleanup()
 def record(self):
  with connect(self.s.db_path) as c:return watch_alerts.record(c,self.release,self.snap,self.s,self.at)
 def test_equal_and_repeated_snapshots_only_one_hit(self):
  self.assertTrue(self.record());self.snap['lowest_price']='25';self.assertFalse(self.record())
  with connect(self.s.db_path) as c:self.assertEqual(len(watch_alerts.rows(c)),1)
 def test_invalid_price_supply_and_time_do_not_trigger(self):
  original=dict(self.snap)
  for patch in [{'lowest_price':'31'},{'lowest_price':'0'},{'num_for_sale':0},{'captured_at':(self.at-timedelta(days=3)).isoformat()},{'captured_at':(self.at+timedelta(seconds=1)).isoformat()},{'captured_at':(self.at-timedelta(hours=2)).isoformat()}]:
   self.snap={**original,**patch};self.assertFalse(self.record())
 def test_cross_currency_requires_fresh_fx(self):
  self.snap.update(currency='TWD',lowest_price='900')
  with connect(self.s.db_path) as c:c.execute('DELETE FROM fx_rates')
  self.assertFalse(self.record())
  from fx import business_day
  with connect(self.s.db_path) as c:c.execute("INSERT INTO fx_rates VALUES('USD',?,'30','test')",(business_day(self.at),))
  self.assertTrue(self.record())
 def test_new_watch_can_trigger_but_changed_decision_cannot(self):
  self.assertTrue(self.record())
  with connect(self.s.db_path) as c:c.execute("INSERT INTO decisions(release_id,decision,decided_at) VALUES(?,'skip',?)",(self.release['release_id'],self.at.isoformat()))
  self.assertFalse(self.record())
  with connect(self.s.db_path) as c:c.execute("INSERT INTO decisions(release_id,decision,target_price,target_currency,decided_at) VALUES(?,'watch','30','USD',?)",(self.release['release_id'],self.at.isoformat()))
  self.assertTrue(self.record())
 def test_analysis_records_target_even_below_score_threshold_without_outbox(self):
  self.s.min_score=101
  with connect(self.s.db_path) as c:
   c.execute('UPDATE snapshots SET lowest_price=?,currency=?,num_for_sale=?,captured_at=? WHERE id=?',('30','USD',1,self.at.isoformat(),self.snap['id']))
   before=c.execute('SELECT count(*) FROM outbox').fetchone()[0]
  self.assertEqual(analyze.run(self.s)['watch_hits'],1)
  self.assertEqual(analyze.run(self.s)['watch_hits'],0)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM outbox').fetchone()[0],before)
