import unittest,json
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from db import connect
from tests.test_source_queue import SourceQueueTests
import refresh_priority,identity_data
from source_match import evidence
class PriorityTests(unittest.TestCase):
 setUp=SourceQueueTests.setUp
 tearDown=SourceQueueTests.tearDown
 def test_priority_reserve_cooldown_and_low_frequency(self):
  instant=datetime.now(timezone.utc)
  with connect(self.s.db_path) as c:
   c.execute('CREATE TABLE source_refresh_attempts(candidate_id INTEGER PRIMARY KEY,attempted_at TEXT,status TEXT)')
   c.execute('DELETE FROM platform_candidates')
   for i in range(1,6):
    age=30 if i<4 else 8
    c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,'tower',str(i),'test','Album','Artist','CD','','100','JPY','listed','在庫あり',f'https://tower.jp/item/{i}',(instant-timedelta(hours=age)).isoformat()))
   priorities={'https://tower.jp/item/3':(0,Decimal(500),100),'https://tower.jp/item/4':(1,Decimal(0),0)}
   rows,report=refresh_priority.select(c,'tower',2,priorities,instant)
   self.assertEqual([r['id'] for r in rows],[1,4]);self.assertEqual(report,{'rotation':1,'priority':1})
   c.execute('INSERT INTO source_refresh_attempts VALUES(?,?,?)',(4,instant.isoformat(),'failed'))
   rows,_=refresh_priority.select(c,'tower',4,priorities,instant)
   self.assertEqual([r['id'] for r in rows],[1,3,2]);self.assertNotIn(5,[r['id'] for r in rows])
 def test_purchase_priority_validates_known_sources_and_removes(self):
  url='https://tower.jp/item/1'
  refresh_priority.set_purchases(self.s,[url],True)
  self.assertEqual(refresh_priority.scores(self.s)[url][0],1)
  with self.assertRaises(ValueError):refresh_priority.set_purchases(self.s,[url,'https://invalid.example'],True)
  refresh_priority.set_purchases(self.s,[url],False)
  self.assertFalse(refresh_priority.scores(self.s).get(url,(0,))[0])
class BarcodeTests(unittest.TestCase):
 def test_checksum_equivalence_and_non_barcodes(self):
  self.assertEqual(identity_data.barcodes('036000291452'),identity_data.barcodes('0036000291452'))
  self.assertEqual(identity_data.barcodes(['1234567890123','0000000000000','2026','978-1-SECRET']),[])
 def test_barcode_conflict_overrides_same_title_catalog_label(self):
  source={'title':'Album LP JAN: 4006381333931','format':'LP','catalog_no':'ABC-123'}
  target={'title':'Album','format':'Vinyl','catno':'ABC-123','labels':'Apple','barcodes':identity_data.barcodes('036000291452')}
  self.assertFalse(evidence(source,target))
  target['barcodes']=identity_data.barcodes('4006381333931')
  self.assertTrue(any('條碼' in r for r in evidence(source,target)))
  source['format']='CD';self.assertFalse(evidence(source,target))

class IdentityPersistenceTests(unittest.TestCase):
 setUp=SourceQueueTests.setUp
 tearDown=SourceQueueTests.tearDown
 def test_enrichment_is_tied_to_identity_and_only_new_metadata_invalidates_check(self):
  import source_queue
  with connect(self.s.db_path) as c:
   row=dict(c.execute('SELECT * FROM platform_candidates WHERE id=1').fetchone());before=source_queue.fingerprint(row)
   self.assertEqual(before,source_queue.fingerprint(identity_data.enrich(c,row)))
   identity_data.save_source(c,row,{'barcodes':['4006381333931'],'labels':'Test Label'})
   enriched=identity_data.enrich(c,row)
   self.assertNotEqual(before,source_queue.fingerprint(enriched));self.assertEqual(enriched['barcodes'],['04006381333931'])
   self.assertNotIn('barcodes',identity_data.enrich(c,{**row,'title':'Different release'}))
