import tempfile,unittest
from pathlib import Path
from config import Settings
from db import init,connect
import demo,notification_review

class NotificationReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'test.db');init(self.s.db_path);demo.seed(self.s)
  with connect(self.s.db_path) as c:
   snap=c.execute('SELECT id,release_id FROM snapshots LIMIT 1').fetchone()
   c.execute("INSERT INTO outbox(release_id,snapshot_id,rules,message,urgent,status,created_at,updated_at) VALUES(?,?,'test','review only',0,'uncertain','2000','2000')",(snap['release_id'],snap['id']))
   self.id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
 def tearDown(self):self.tmp.cleanup()
 def test_confirm_received_registers_cooldown_once(self):
  notification_review.resolve(self.s,self.id,'sent')
  with self.assertRaises(ValueError):notification_review.resolve(self.s,self.id,'sent')
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM alerts_sent WHERE outbox_id=?',(self.id,)).fetchone()[0],1)
 def test_stop_does_not_record_delivery_or_retry(self):
  notification_review.resolve(self.s,self.id,'cancelled')
  with connect(self.s.db_path) as c:
   self.assertEqual(c.execute('SELECT status FROM outbox WHERE id=?',(self.id,)).fetchone()[0],'cancelled')
   self.assertEqual(c.execute('SELECT count(*) FROM alerts_sent WHERE outbox_id=?',(self.id,)).fetchone()[0],0)
 def test_invalid_inputs_and_non_uncertain_are_unchanged(self):
  for id,outcome in [(True,'sent'),(self.id,'pending'),(999999,'sent')]:
   with self.assertRaises(ValueError):notification_review.resolve(self.s,id,outcome)
  with connect(self.s.db_path) as c:c.execute("UPDATE outbox SET status='sending' WHERE id=?",(self.id,))
  with self.assertRaises(ValueError):notification_review.resolve(self.s,self.id,'sent')
 def test_state_is_read_only_and_counts_all(self):
  before=notification_review.state(self.s)
  self.assertEqual(before,notification_review.state(self.s));self.assertGreaterEqual(before['counts']['uncertain'],1)
  self.assertLessEqual(len(before['rows']),100)
