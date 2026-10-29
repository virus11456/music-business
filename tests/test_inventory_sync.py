import tempfile,unittest,json
from pathlib import Path
from unittest.mock import Mock
from config import Settings
from db import init,connect
import workflow,inventory_sync,demo
class InventoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);workflow.init_workflow(self.s)
 def tearDown(self):self.tmp.cleanup()
 def client(self,items,page=1,pages=1,total=None,user='TEST'):
  return Mock(get=Mock(side_effect=[{'username':user},{'pagination':{'page':page,'pages':pages,'items':len(items) if total is None else total},'listings':items}]))
 def item(self,id):return {'id':id,'release':{'id':1},'status':'For Sale','external_id':''}
 def test_partial_pages_do_not_replace_complete_snapshot(self):
  inventory_sync.run(self.s,self.client([self.item(1)]))
  inventory_sync.run(self.s,self.client([self.item(2)],pages=2,total=2))
  self.assertEqual(inventory_sync.state(self.s)['snapshot']['rows'][0]['listing_id'],1)
  result=inventory_sync.run(self.s,self.client([self.item(3)],page=2,pages=2,total=2))
  self.assertTrue(result['complete']);self.assertEqual(inventory_sync.state(self.s)['snapshot']['total'],2)
 def test_failed_page_and_account_change_preserve_previous_state(self):
  inventory_sync.run(self.s,self.client([self.item(1)],pages=2,total=2))
  before=inventory_sync.state(self.s)
  for client in [self.client([self.item(1)],page=2,pages=2,total=2),self.client([],user='OTHER'),self.client([],page=2,pages=3,total=3)]:
   with self.assertRaises(ValueError):inventory_sync.run(self.s,client)
   self.assertEqual(inventory_sync.state(self.s),before)
 def test_album_id_alone_never_registers_a_listing(self):
  inventory_sync.run(self.s,self.client([self.item(1)]))
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM published_listings').fetchone()[0],0)
 def test_empty_inventory_does_not_erase_publishing_history(self):
  with connect(self.s.db_path) as c:c.execute("INSERT INTO published_listings VALUES('https://example.com',1,'9','2000')")
  inventory_sync.run(self.s,self.client([],pages=0))
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM published_listings').fetchone()[0],1)
 def test_only_exported_unchanged_draft_can_register(self):
  demo.seed(self.s)
  from server import release_id,required
  from cli import currency
  data={'release_id':'900000001','price':'80','currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','owned_confirmed':'yes','source_url':'https://example.com/source'}
  with connect(self.s.db_path) as c:workflow.save_draft(c,data,release_id,currency,required)
  item={'id':123,'release':{'id':900000001},'status':'For Sale','external_id':'simples-1-release-900000001'}
  inventory_sync.run(self.s,self.client([item]))
  self.assertEqual(inventory_sync.state(self.s)['snapshot']['linked'],0)
  workflow.quicklister_csv(self.s,[1],'USD')
  with connect(self.s.db_path) as c:c.execute("UPDATE listing_drafts SET created_at='2999-01-01T00:00:00+00:00'")
  inventory_sync.run(self.s,self.client([item]))
  self.assertEqual(inventory_sync.state(self.s)['snapshot']['linked'],0)
  with connect(self.s.db_path) as c:c.execute("UPDATE listing_drafts SET created_at='2000-01-01T00:00:00+00:00'")
  inventory_sync.run(self.s,self.client([item]))
  self.assertEqual(inventory_sync.state(self.s)['snapshot']['linked'],1)
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT listing_id FROM published_listings').fetchone()[0],'123')
 def test_switching_account_clears_snapshot_but_keeps_publishing_history(self):
  inventory_sync.run(self.s,self.client([self.item(1)],user='OLD'))
  with connect(self.s.db_path) as c:c.execute("INSERT INTO published_listings VALUES('https://example.com',1,'9','2000')")
  with self.assertRaisesRegex(ValueError,'NEW'):inventory_sync.run(self.s,self.client([self.item(2)],user='NEW'))
  self.assertEqual(inventory_sync.state(self.s)['account'],'OLD')
  from server import Dashboard
  result=Dashboard(self.s).mutate('/api/inventory/reset',{'scope':'account'})
  self.assertIn('OLD',result['message']);self.assertIsNone(inventory_sync.state(self.s)['snapshot'])
  inventory_sync.run(self.s,self.client([self.item(2)],user='NEW'))
  self.assertEqual(inventory_sync.state(self.s)['account'],'NEW')
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT count(*) FROM published_listings').fetchone()[0],1)
