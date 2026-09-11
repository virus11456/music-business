import unittest,json
from unittest.mock import patch
from tests import test_source_queue
from db import connect
import direct_matches,comparisons
class DirectMatchTests(unittest.TestCase):
 setUp=test_source_queue.SourceQueueTests.setUp
 tearDown=test_source_queue.SourceQueueTests.tearDown
 def prepare(self):
  with connect(self.s.db_path) as c:
   r=dict(c.execute('SELECT * FROM releases WHERE release_id=900000001').fetchone())
   c.execute('UPDATE platform_candidates SET title=?,artist=?,format=?,catalog_no=?',(r['title'],r['artist'],r['format'],r['catno']))
 def test_cross_match_without_search_record_and_cached_on_price_change(self):
  self.prepare();rows=comparisons.build(self.s);self.assertEqual(len(rows),1);self.assertIn('已抓取資料直接交叉比對',rows[0]['evidence']);self.assertIsNotNone(rows[0]['gross_twd'])
  with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET price='300'")
  with patch('direct_matches.evidence',side_effect=AssertionError('identity cache should be reused')):
   updated=comparisons.build(self.s)
  self.assertNotEqual(rows[0]['gross_twd'],updated[0]['gross_twd'])
 def test_identity_changes_invalidate_and_wrong_artist_or_catalog_rejected(self):
  self.prepare();self.assertEqual(len(comparisons.build(self.s)),1)
  with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET catalog_no='WRONG'")
  self.assertEqual(comparisons.build(self.s),[])
  with connect(self.s.db_path) as c:c.execute("UPDATE platform_candidates SET catalog_no='',artist='Different artist'")
  self.assertEqual(comparisons.build(self.s),[])
 def test_exclusion_is_preserved(self):
  self.prepare()
  with connect(self.s.db_path) as c:c.execute('INSERT INTO excluded_matches VALUES(?,?,?)',('https://tower.jp/item/1',900000001,'2026-09-11'))
  rows=comparisons.build(self.s);self.assertEqual(len(rows),1);self.assertTrue(rows[0]['excluded'])
