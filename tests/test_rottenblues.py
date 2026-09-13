import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import rottenblues as rb
import platforms,source_details,source_refresh
from config import Settings
from db import init,connect

# Minimal public catalog shape observed 2026-09-13; no customer data.
def product():
 return {'id':10598255362229,'handle':'日版黑膠-名譽傳說','title':'【日版黑膠】名譽傳說《OK集》','product_type':'黑膠','body_html':'<p>預購中，12月2日發行</p>','tags':['Vinyl','預購 Pre-order'],'variants':[{'id':53256229159093,'title':'Default Title','price':'1290.00','available':True,'sku':None,'barcode':None}]}

class RottenTests(unittest.TestCase):
 def test_catalog_preorder_price_and_link(self):
  rows,more=rb.parse_catalog(json.dumps({'products':[product()]}));r=rows[0]
  self.assertEqual((r['price'],r['currency'],r['availability'],r['format']),('1290.00','TWD','預購','Vinyl'))
  self.assertFalse(more);self.assertTrue(r['source_url'].endswith('?variant=53256229159093'));self.assertEqual(r['labels'],'')
 def test_distinct_variants_not_lowest_price(self):
  p=product();p['variants']+=[{**p['variants'][0],'id':53256229159094,'title':'限量盤','price':'1590.00','available':False}]
  rows,_=rb.parse_catalog(json.dumps({'products':[p]}));self.assertEqual(len(rows),2);self.assertEqual(rows[1]['availability'],'售罄');self.assertEqual(rows[1]['price'],'1590.00');self.assertIn('限量盤',rows[1]['title'])
 def test_empty_filtered_page_keeps_cursor(self):
  rows,more=rb.parse_catalog(json.dumps({'products':[product()]*40}),'CD');self.assertEqual(rows,[]);self.assertTrue(more)
  self.assertEqual(rb.parse_catalog('{"products":[]}'),([],False))
 def test_unknown_media_and_conflicts_excluded(self):
  p=product();p['title']='【CD】Album';self.assertEqual(rb.product_rows(p),[])
  p['product_type']='其他';p['title']='唱片架';self.assertEqual(rb.product_rows(p),[])
 def test_bad_structure_price_id_and_currency(self):
  for raw in ['{}','{"products":null}','<html>denied</html>']:
   with self.assertRaises(ValueError):rb.parse_catalog(raw)
  for key,value in [('price','NaN'),('id','../evil'),('price_currency','USD')]:
   p=product();p['variants'][0][key]=value
   with self.assertRaises(ValueError):rb.product_rows(p)
 def test_js_detail_cents_and_wrong_variant(self):
  p=product();row=rb.product_rows(p)[0];p.update(type='J-Pop',description=p['body_html']);p['variants'][0]['price']=129000
  result=source_details.parse('rottenblues',row['external_id'],json.dumps(p),row['source_url']);self.assertEqual(result['price'],'1290');self.assertEqual(result['availability'],'預購')
  p['variants'][0]['id']=9
  with self.assertRaises(ValueError):rb.parse_detail(row['external_id'],row['source_url'],json.dumps(p))
 def test_url_rejects_external_hosts_and_path(self):
  for url in ['https://evil.com/products/a?variant=1','https://www.rottenblues.com/products/%2F..%2Fx?variant=1','https://www.rottenblues.com/products/a?variant=2']:
   with self.assertRaises(ValueError):rb.detail_url('1',url)
 def test_upsert_identity_and_refresh_use_saved_variant(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Settings(db_path=Path(tmp)/'test.db');init(s.db_path);platforms.init(s)
   p=product();p['variants'][0]['barcode']='4901234567894'
   with patch('platforms.time.sleep'):
    for _ in range(2):
     r=platforms.search(s,rb.ALL_QUERY,['rottenblues'],lambda _:json.dumps({'products':[p]}),full_page=True);self.assertEqual(r['failed_platforms'],0)
   with connect(s.db_path) as c:
    self.assertEqual(c.execute('SELECT count(*) FROM platform_candidates').fetchone()[0],1)
    self.assertEqual(c.execute("SELECT count(*) FROM meta WHERE key LIKE 'source_identity_%'").fetchone()[0],1)
    c.execute("UPDATE platform_candidates SET captured_at='2020-01-01T00:00:00+00:00'")
   p.update(type='J-Pop',description=p['body_html']);p['variants'][0]['price']=135000
   result=source_refresh.run(s,lambda u:json.dumps(p),sleeper=lambda _:None)
   self.assertEqual(result['updated'],1)
   with connect(s.db_path) as c:self.assertEqual(c.execute('SELECT price FROM platform_candidates').fetchone()[0],'1350')
