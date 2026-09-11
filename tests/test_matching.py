import tempfile,unittest,json
from pathlib import Path
from config import Settings
from db import init,connect
import platforms,matching
class MatchingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'test.db');init(self.s.db_path);platforms.init(self.s);matching.init(self.s)
  with connect(self.s.db_path) as c:
   c.execute("INSERT INTO platform_candidates VALUES(1,'tower','123','Beatles','Test','The Beatles','SHM-CD','ABC-123','100','JPY','listed','未確認','https://tower.jp/item/123','2026-09-10')")
 def tearDown(self):self.tmp.cleanup()
 def test_catalog_search_and_only_release_results(self):
  seen={}
  class Client:
   def get(self,path,params):
    seen.update(params)
    return {'results':[{'id':4,'type':'master'},{'id':True,'type':'release'},{'id':5,'type':'release','title':'Test','catno':'ABC 123','format':['CD']}]}
  matching.search(self.s,1,client=Client())
  self.assertEqual(seen['catno'],'ABC-123');self.assertEqual(seen['format'],'CD')
  results=matching.state(self.s)['1']['results'];self.assertEqual(len(results),1);self.assertIn('仍需核對',results[0]['evidence'][0])
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM releases').fetchone()[0],0)
 def test_override_and_empty_result(self):
  seen={}
  class Client:
   def get(self,path,params):seen.update(params);return {'results':[]}
  matching.search(self.s,1,'Rubber Soul',Client());self.assertEqual(seen['q'],'Rubber Soul');self.assertNotIn('catno',seen)
  self.assertEqual(matching.state(self.s)['1']['results'],[])
 def test_unknown_candidate_rejected(self):
  with self.assertRaises(ValueError):matching.search(self.s,999)
 def test_media_unknown_not_guessed(self):
  self.assertIsNone(matching.media('未確認'));self.assertEqual(matching.media('LP'),'Vinyl')

 def test_title_format_limits_api_search_without_guessing_mixed_sets(self):
  seen={}
  class Client:
   def get(self,path,params):seen.clear();seen.update(params);return {'results':[]}
  for title,expected in [('Rubber Soul 黑膠 LP','Vinyl'),('Rubber Soul 卡帶','Cassette'),('Rubber Soul SHM-CD','CD'),('Rubber Soul CD + LP',None)]:
   with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET title=?,format='未確認' WHERE id=1",(title,))
   matching.search(self.s,1,client=Client())
   self.assertEqual(seen.get('format'),expected)
