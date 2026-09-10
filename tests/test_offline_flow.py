"""Full synthetic flow with actual HTTP handler, in-memory transport only."""
import tempfile,unittest
from pathlib import Path
from config import Settings
from test_full_workflow import run_flow

class OfflineFlowTests(unittest.TestCase):
 def test_three_formats_to_batch_and_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   result=run_flow(Settings(db_path=Path(tmp)/'isolated.db',token='TEST-NOT-REAL'),in_memory=True)
   self.assertEqual(result['formats'],['Vinyl','CD','Cassette'])
   self.assertEqual(result['export_rows'],3)
