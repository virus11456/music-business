import tempfile,unittest,hashlib,json
from pathlib import Path
from config import Settings
from db import init,connect
from server import Dashboard
import demo,workflow

class ExportHistoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);self.app=Dashboard(self.s)
  self.app.mutate('/api/drafts',{'release_id':900000001,'price':'80','currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','owned_confirmed':'yes'})
 def tearDown(self):self.tmp.cleanup()
 def test_generated_content_and_snapshot_survive_edit_and_restart(self):
  content=workflow.quicklister_csv(self.s,[1],'USD')
  with connect(self.s.db_path) as c:
   row=c.execute('SELECT * FROM listing_exports').fetchone()
   self.assertEqual(row['content_sha256'],hashlib.sha256(content.encode()).hexdigest())
   self.assertEqual(json.loads(row['items'])[0]['price'],'80')
   c.execute("UPDATE listing_drafts SET price='90'")
  history=Dashboard(Settings(db_path=self.s.db_path)).state()['workflow']['exports']
  self.assertEqual(history[0]['items'][0]['price'],'80')
  self.assertEqual(history[0]['currency'],'USD')
 def test_invalid_batch_records_nothing(self):
  for ids,cc in [([1,999],'USD'),([1],'JPY'),([1,1],'USD')]:
   with self.assertRaises(ValueError):workflow.quicklister_csv(self.s,ids,cc)
  self.assertEqual(workflow.export_history(self.s),[])
 def test_each_generation_recorded_and_recent_view_bounded(self):
  for _ in range(21):workflow.quicklister_csv(self.s,[1],'USD')
  history=workflow.export_history(self.s)
  self.assertEqual(len(history),20);self.assertEqual(history[0]['id'],21);self.assertEqual(history[-1]['id'],2)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM listing_exports').fetchone()[0],21)
