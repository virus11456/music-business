import io,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.error import HTTPError,URLError
from config import Settings
from db import init,connect
import demo,workflow,discogs_publish,inventory_sync
from discogs_client import DiscogsClient,ListingRejected,ListingUncertain,APIError
from server import Dashboard,release_id,required
from cli import currency

DRAFT={'release_id':'900000001','price':'80','currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','owned_confirmed':'yes','note':'Small mark'}

class Reply:
 def __init__(self,body,status=201):self.body=body;self.status=status;self.headers={'X-Discogs-Ratelimit-Remaining':'50'}
 def read(self,n=-1):return self.body
 def __enter__(self):return self
 def __exit__(self,*a):return False

def http_error(code,body=b''):
 return HTTPError('https://api.discogs.com/marketplace/listings',code,'err',{},io.BytesIO(body))

class PublishTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db',token='TEST');init(self.s.db_path);demo.seed(self.s);workflow.init_workflow(self.s)
  with connect(self.s.db_path) as c:
   workflow.save_draft(c,DRAFT,release_id,currency,required)
   workflow.save_draft(c,{**DRAFT,'release_id':'900000002','price':'45'},release_id,currency,required)
  self.env=patch.dict(os.environ,{'DISCOGS_LISTING_WRITE':'1'});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def record(self,draft_id):
  with connect(self.s.db_path) as c:return discogs_publish.submission(c,draft_id)
 def published(self):
  with connect(self.s.db_path) as c:return c.execute('SELECT release_id,listing_id FROM published_listings ORDER BY release_id').fetchall()

 def test_disabled_flag_sends_nothing_and_records_nothing(self):
  with patch.dict(os.environ,{'DISCOGS_LISTING_WRITE':''}):
   client=Mock();client.post.side_effect=AssertionError('must not call')
   with self.assertRaisesRegex(workflow.BatchDraftError,'DISCOGS_LISTING_WRITE'):discogs_publish.run(self.s,[1],'USD','Draft',client)
   self.assertFalse(discogs_publish.state(self.s)['enabled'])
  self.assertIsNone(self.record(1))

 def test_batch_is_validated_before_any_request(self):
  client=Mock();client.post.side_effect=AssertionError('must not call')
  for ids,cc,status in [([1,999],'USD','Draft'),([1],'JPY','Draft'),([1,1],'USD','Draft'),([1],'USD','Live'),([],'USD','Draft'),(['1'],'USD','Draft')]:
   with self.assertRaises(workflow.BatchDraftError):discogs_publish.run(self.s,ids,cc,status,client)
  with connect(self.s.db_path) as c:c.execute("UPDATE listing_drafts SET created_at='2000-01-01T00:00:00+00:00' WHERE id=2")
  with self.assertRaisesRegex(workflow.BatchDraftError,'48 小時'):discogs_publish.run(self.s,[1,2],'USD','Draft',client)
  self.assertIsNone(self.record(1));self.assertEqual(self.published(),[])

 def test_success_records_listing_and_blocks_duplicate_export(self):
  client=Mock();client.post.return_value={'listing_id':555,'resource_url':'x'}
  result=discogs_publish.run(self.s,[1],'USD','Draft',client)
  self.assertEqual((result['listed'],result['failed']),(1,0))
  path,payload=client.post.call_args.args
  self.assertEqual(path,'/marketplace/listings')
  self.assertEqual({k:payload[k] for k in ('release_id','condition','sleeve_condition','price','status','external_id','allow_offers')},
   {'release_id':900000001,'condition':'Very Good (VG)','sleeve_condition':'No Cover','price':80.0,'status':'Draft','external_id':'simples-1-release-900000001','allow_offers':False})
  self.assertIn('Media: Very Good (VG). Sleeve: No Cover. Small mark',payload['comments'])
  record=self.record(1);self.assertEqual((record['status'],record['listing_id'],record['attempts']),('listed',555,1))
  self.assertEqual([tuple(r) for r in self.published()],[(900000001,'555')])
  drafts={d['id']:d for d in workflow.get_workflow(self.s)['drafts']}
  self.assertEqual(drafts[1]['listing_status'],'listed');self.assertEqual(drafts[1]['submission']['status'],'listed')
  self.assertTrue(any('已登錄上架' in i for i in drafts[1]['export_issues']))
  with self.assertRaises(workflow.BatchDraftError):discogs_publish.run(self.s,[1],'USD','Draft',client)
  self.assertEqual(client.post.call_count,1)

 def test_rejection_keeps_draft_editable_and_resendable(self):
  client=Mock();client.post.side_effect=[ListingRejected(422,'Release not found'),{'listing_id':9}]
  result=discogs_publish.run(self.s,[1],'USD','Draft',client)
  self.assertEqual((result['rejected'],result['failed'],result['listed']),(1,1,0))
  record=self.record(1);self.assertEqual(record['status'],'failed');self.assertIn('Release not found',record['reason'])
  self.assertEqual(self.published(),[])
  with connect(self.s.db_path) as c:self.assertEqual(workflow.draft_export_issues(c,c.execute('SELECT * FROM listing_drafts WHERE id=1').fetchone()),[])
  result=discogs_publish.run(self.s,[1],'USD','For Sale',client)
  record=self.record(1);self.assertEqual((record['status'],record['attempts'],record['history'][0]['status'],record['requested_status']),('listed',2,'failed','For Sale'))

 def test_uncertain_outcome_stops_batch_and_is_never_resent(self):
  client=Mock();client.post.side_effect=ListingUncertain('Discogs 連線中斷或逾時，刊登結果不明')
  result=discogs_publish.run(self.s,[1,2],'USD','Draft',client)
  self.assertEqual((result['uncertain'],result['not_attempted'],result['failed']),(1,1,2));self.assertEqual(client.post.call_count,1)
  self.assertEqual(self.record(1)['status'],'uncertain');self.assertIsNone(self.record(2))
  with connect(self.s.db_path) as c:
   issues=workflow.draft_export_issues(c,c.execute('SELECT * FROM listing_drafts WHERE id=1').fetchone())
  self.assertTrue(any('結果不明' in i for i in issues))
  with self.assertRaisesRegex(ValueError,'結果不明'):workflow.quicklister_csv(self.s,[1],'USD')
  with self.assertRaisesRegex(workflow.BatchDraftError,'結果不明'):discogs_publish.run(self.s,[1],'USD','Draft',client)
  self.assertEqual(client.post.call_count,1)
  for bad in [(1,'listed',''),(1,'listed','abc'),(2,'not_listed',None),('1','listed','5'),(1,'retry',None)]:
   with self.assertRaises(ValueError):discogs_publish.resolve(self.s,*bad)
  self.assertEqual(self.record(1)['status'],'uncertain')
  discogs_publish.resolve(self.s,1,'listed','777')
  self.assertEqual((self.record(1)['status'],self.record(1)['listing_id']),('listed',777));self.assertEqual([tuple(r) for r in self.published()],[(900000001,'777')])
  with self.assertRaises(ValueError):discogs_publish.resolve(self.s,1,'not_listed')

 def test_not_listed_resolution_allows_a_new_attempt(self):
  client=Mock();client.post.side_effect=[ListingUncertain('x'),{'listing_id':3}]
  discogs_publish.run(self.s,[1],'USD','Draft',client)
  discogs_publish.resolve(self.s,1,'not_listed')
  self.assertEqual(self.record(1)['status'],'failed');self.assertEqual(self.published(),[])
  discogs_publish.run(self.s,[1],'USD','Draft',client)
  self.assertEqual(self.record(1)['status'],'listed')

 def test_unexpected_exception_after_send_is_uncertain(self):
  client=Mock();client.post.side_effect=RuntimeError('token secret')
  discogs_publish.run(self.s,[1],'USD','Draft',client)
  record=self.record(1);self.assertEqual(record['status'],'uncertain');self.assertNotIn('secret',record['reason'])

 def test_inventory_readback_confirms_open_attempt(self):
  client=Mock();client.post.side_effect=ListingUncertain('x')
  discogs_publish.run(self.s,[1],'USD','Draft',client)
  item={'id':321,'release':{'id':900000001},'status':'Draft','external_id':'simples-1-release-900000001'}
  other={'id':322,'release':{'id':900000002},'status':'For Sale','external_id':'simples-1-release-900000001'}
  reader=Mock(get=Mock(side_effect=[{'username':'U'},{'pagination':{'page':1,'pages':1,'items':2},'listings':[other,item]}]))
  result=inventory_sync.run(self.s,reader)
  self.assertEqual(result['reconciled'],1)
  record=self.record(1);self.assertEqual((record['status'],record['listing_id']),('listed',321))
  self.assertEqual([tuple(r) for r in self.published()],[(900000001,'321')])
  snapshot=inventory_sync.state(self.s)['snapshot'];self.assertEqual(snapshot['linked'],1);self.assertEqual(snapshot['reconciled'],1)

 def test_state_counts_and_recent_rows(self):
  client=Mock();client.post.side_effect=[{'listing_id':1},ListingRejected(400,'bad')]
  discogs_publish.run(self.s,[1,2],'USD','Draft',client)
  state=discogs_publish.state(self.s)
  self.assertTrue(state['enabled']);self.assertEqual(state['counts'],{'submitting':0,'listed':1,'failed':1,'uncertain':0})
  self.assertEqual([r['draft_id'] for r in state['rows']],[2,1])

 def test_damaged_record_blocks_export_and_resend_without_crashing(self):
  with connect(self.s.db_path) as c:c.execute("INSERT INTO meta VALUES(?,?)",(discogs_publish.key(1),'not json'))
  drafts={d['id']:d for d in workflow.get_workflow(self.s)['drafts']}
  self.assertEqual(drafts[1]['submission']['status'],'damaged');self.assertTrue(any('結果不明' in i for i in drafts[1]['export_issues']))
  client=Mock();client.post.side_effect=AssertionError('must not call')
  with self.assertRaises(workflow.BatchDraftError):discogs_publish.run(self.s,[1],'USD','Draft',client)
  self.assertEqual(discogs_publish.state(self.s)['rows'][0]['status'],'damaged')
 def test_stale_submitting_is_resolvable(self):
  with connect(self.s.db_path) as c:
   c.execute("INSERT INTO meta VALUES(?,?)",(discogs_publish.key(1),json.dumps({'draft_id':1,'release_id':900000001,'source_url':'','external_id':'simples-1-release-900000001','status':'submitting','started_at':'2000-01-01T00:00:00+00:00','history':[]})))
  self.assertTrue(discogs_publish.stale_open(self.record(1)))
  discogs_publish.resolve(self.s,1,'listed','12')
  self.assertEqual(self.record(1)['status'],'listed')

class ClientPostTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db',token='TEST');init(self.s.db_path)
 def tearDown(self):self.tmp.cleanup()
 def client(self,transport):
  tick=iter(range(1,100000))
  return DiscogsClient(self.s,transport=transport,clock=lambda:next(tick)*100.0,sleep=Mock())
 def test_only_the_listing_endpoint_is_writable(self):
  with self.assertRaises(APIError):self.client(Mock()).post('/marketplace/orders',{})
  with self.assertRaises(APIError):self.client(Mock()).post('/marketplace/listings',[])
 def test_created_reply_returns_data_once(self):
  transport=Mock(return_value=Reply(b'{"listing_id": 42}'))
  data=self.client(transport).post('/marketplace/listings',{'release_id':1})
  self.assertEqual(data['listing_id'],42);self.assertEqual(transport.call_count,1)
  request=transport.call_args.args[0]
  self.assertEqual(request.get_method(),'POST');self.assertEqual(json.loads(request.data)['release_id'],1)
  self.assertEqual(request.get_header('Authorization'),'Discogs token=TEST')
 def test_definite_rejections_and_unknown_outcomes_are_classified_without_retry(self):
  cases=[(http_error(422,b'{"message":"Release \\u0007not found"}'),ListingRejected,'Release not found'),(http_error(429),ListingRejected,'429'),
         (http_error(500),ListingUncertain,'500'),(URLError('down'),ListingUncertain,'連線'),(TimeoutError(),ListingUncertain,'連線')]
  for error,kind,text in cases:
   transport=Mock(side_effect=error)
   with self.assertRaisesRegex(kind,text):self.client(transport).post('/marketplace/listings',{})
   self.assertEqual(transport.call_count,1)
  for body in [b'not json',b'[]',b'x'*100001]:
   with self.assertRaises(ListingUncertain):self.client(Mock(return_value=Reply(body))).post('/marketplace/listings',{})
  with self.assertRaises(ListingUncertain):self.client(Mock(return_value=Reply(b'{}',status=204))).post('/marketplace/listings',{})

class EndpointTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db',token='TEST');init(self.s.db_path);demo.seed(self.s)
  with connect(self.s.db_path) as c:c.execute("UPDATE meta SET value='live' WHERE key='mode'")
  self.app=Dashboard(self.s)
  self.app.mutate('/api/drafts',DRAFT)
  self.env=patch.dict(os.environ,{'DISCOGS_LISTING_WRITE':'1'});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def wait(self):
  for _ in range(200):
   if self.app.active is None:return
   time.sleep(.01)
  self.fail('job did not finish')
 def test_publish_endpoint_validates_then_runs_job(self):
  with patch('discogs_publish.run',return_value={'listed':1,'failed':0}) as run:
   for data in [{'draft_ids':[1],'currency':'USD','status':'Live'},{'draft_ids':[1],'currency':'JPY'},{'draft_ids':'1','currency':'USD'}]:
    with self.assertRaises(ValueError):self.app.mutate('/api/listings/publish',data)
   run.assert_not_called()
   result=self.app.mutate('/api/listings/publish',{'draft_ids':[1],'currency':'USD'});self.wait()
   self.assertTrue(result['accepted']);run.assert_called_once_with(self.s,[1],'USD','Draft')
  state=self.app.state()
  self.assertTrue(state['configured']['discogs_listing_write']);self.assertIn('listing_submissions',state['workflow'])
  with patch.dict(os.environ,{'DISCOGS_LISTING_WRITE':''}):
   self.assertFalse(self.app.state()['configured']['discogs_listing_write'])
   with self.assertRaises(ValueError):self.app.mutate('/api/listings/publish',{'draft_ids':[1],'currency':'USD'})
 def test_resolve_endpoint_and_public_catalog_exclusion(self):
  with patch('discogs_publish.resolve',return_value={'saved':True}) as resolve:
   self.app.mutate('/api/listings/submissions/resolve',{'draft_id':1,'outcome':'not_listed'});resolve.assert_called_once_with(self.s,1,'not_listed',None)
  from public_catalog import public_catalog
  self.assertNotIn('listing_submissions',json.dumps(public_catalog(self.app.state())))

class SheetContractTests(unittest.TestCase):
 def test_submission_records_round_trip_through_sheet_primary(self):
  from sheet_records import allowed_meta,capture,decode
  from sheet_primary import memory_schema
  self.assertTrue(allowed_meta('listing_submission:7'));self.assertFalse(allowed_meta('listing_submissions'))
  c=memory_schema();c.execute("INSERT INTO meta VALUES('listing_submission:7','{\"status\":\"uncertain\"}')")
  data=capture(c)['meta'];rows=decode('meta',data,['key','value'])
  self.assertEqual(rows,[['listing_submission:7','{"status":"uncertain"}']])
