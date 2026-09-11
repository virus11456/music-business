import json,tempfile,unittest
from pathlib import Path
from config import Settings
from db import init,connect
import platforms,source_refresh
class RefreshTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'test.db');init(self.s.db_path);platforms.init(self.s)
  with connect(self.s.db_path) as c:
   for i in (1,2):c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(i,'ruten',str(i),'test','Album','Artist','CD','CAT','200','TWD','listed','未確認','https://www.ruten.com.tw/item/show?'+str(i),'2020-01-01T00:00:00+00:00'))
 def tearDown(self):self.tmp.cleanup()
 def payload(self,i=1,title='Album'):
  return json.dumps([{'ProdId':str(i),'ProdName':title,'Currency':'TWD','PriceRange':[350,350],'SaleType':'buy','StockStatus':1}])
 def test_refresh_only_returned_items_and_preserve_identity(self):
  r=source_refresh.run(self.s,lambda u:self.payload());self.assertEqual((r['updated'],r['missing']),(1,1))
  with connect(self.s.db_path) as c:
   a,b=c.execute('SELECT * FROM platform_candidates ORDER BY id').fetchall()
   self.assertEqual(a['price'],'350');self.assertEqual(a['catalog_no'],'CAT');self.assertEqual(a['format'],'CD');self.assertEqual(b['price'],'200');self.assertTrue(b['captured_at'].startswith('2020'))
  self.assertEqual(source_refresh.run(self.s,lambda u:self.fail('should respect retry delay'))['attempted'],0)
 def test_failure_preserves_price_and_clock(self):
  r=source_refresh.run(self.s,lambda u:'bad');self.assertEqual(r['failed'],2)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute("SELECT count(*) FROM platform_candidates WHERE captured_at LIKE '2020%' AND price='200'").fetchone()[0],2)
 def test_identity_change_does_not_validate_old_match(self):
  r=source_refresh.run(self.s,lambda u:self.payload(title='Different album'));self.assertEqual(r['failed'],1)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT title FROM platform_candidates WHERE id=1').fetchone()[0],'Album')
 def test_unrequested_id_fails_without_inserting(self):
  r=source_refresh.run(self.s,lambda u:self.payload(i=999));self.assertEqual(r['failed'],2)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM platform_candidates').fetchone()[0],2)
 def test_missing_items_do_not_starve_other_quotes(self):
  source_refresh.run(self.s,lambda u:'[]',limit=1)
  with connect(self.s.db_path) as c:c.execute("UPDATE source_refresh_attempts SET attempted_at='2021-01-01T00:00:00+00:00'")
  r=source_refresh.run(self.s,lambda u:self.payload(i=2),limit=1);self.assertEqual(r['updated'],1)
