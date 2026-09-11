"""A writer may commit while the comparison reader walks saved search results."""
import json,unittest
from unittest.mock import patch
from tests import test_source_queue
from db import connect,now
import comparisons
class ComparisonConcurrencyTests(unittest.TestCase):
 setUp=test_source_queue.SourceQueueTests.setUp
 tearDown=test_source_queue.SourceQueueTests.tearDown
 def test_background_commit_during_search_iteration_keeps_prices_readable(self):
  with connect(self.s.db_path) as c:
   target=dict(c.execute('SELECT * FROM releases WHERE release_id=900000001').fetchone())
   c.execute('UPDATE platform_candidates SET title=?,format=?',(target['title'],target['format']))
   for sid in (2,3):
    c.execute('INSERT INTO platform_candidates SELECT ?,platform,?,query,title,artist,format,catalog_no,price,currency,price_kind,availability,?,captured_at FROM platform_candidates WHERE id=1',(sid,str(sid),f'https://tower.jp/item/{sid}'))
   for sid in (1,2,3):
    c.execute('INSERT INTO version_searches VALUES(?,?,?,?)',(sid,'{}',json.dumps([{'release_id':900000001,'title':target['title'],'labels':'' if sid==1 else 'Test Label'}]),now()))
  original=comparisons.match_evidence
  committed=[]
  def evidence(source,release):
   if not committed:
    with connect(self.s.db_path) as writer:writer.execute("INSERT INTO meta VALUES('concurrent_writer','done')")
    committed.append(True)
   return original(source,release)
  with patch('comparisons.match_evidence',side_effect=evidence):rows=comparisons.build(self.s)
  self.assertEqual(len(rows),3)
  self.assertTrue(all(row['gross_twd'] is not None for row in rows))
  with connect(self.s.db_path) as c:
   self.assertEqual(c.execute("SELECT value FROM meta WHERE key='concurrent_writer'").fetchone()[0],'done')
   self.assertEqual(c.execute("SELECT value FROM meta WHERE key='release_labels_900000001'").fetchone()[0],'Test Label')
