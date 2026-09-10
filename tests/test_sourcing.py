import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from config import Settings
from db import init,connect,now
import demo,workflow,platforms,matching,sourcing,comparisons
class SourcingTests(unittest.TestCase):
 def test_demand_first_excludes_known_format_mismatch(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Settings(db_path=Path(tmp)/'test.db');init(s.db_path);demo.seed(s);workflow.init_workflow(s);platforms.init(s);matching.init(s)
   def fake(settings,query,selected):
    stamp=now()
    with connect(s.db_path) as c:
     for i,fmt in [(1,'LP'),(2,'CD'),(3,'カセット')]:
      c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,'tower',str(i),query,c.execute('SELECT title FROM releases WHERE release_id=900000001').fetchone()[0],'Artist',fmt,'','200','JPY','listed','未確認',f'https://tower.jp/item/{i}',stamp))
     c.execute('INSERT INTO platform_runs(platform,query,count,status,recorded_at) VALUES(?,?,?,?,?)',('tower',query,3,'完成',stamp))
    return {'candidates':3}
   with patch('sourcing.platforms.search',side_effect=fake):r=sourcing.find(s,900000001,['tower'])
   self.assertEqual(r['possible_matches'],1)
   rows=comparisons.build(s);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['format'],'Vinyl');self.assertFalse(rows[0]['ready']);self.assertIsNotNone(rows[0]['gross_twd']);self.assertEqual(rows[0]['cost_basis'],'source_price')
