import io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from db import init,connect
from config import Settings
import ai_listing,demo,workflow
from server import release_id,required,Dashboard
from cli import currency

class AINoteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);workflow.init_workflow(self.s)
  with connect(self.s.db_path) as c:workflow.save_draft(c,dict(release_id='900000001',price='80',currency='USD',media_cond='Very Good (VG)',sleeve_cond='No Cover',version_confirmed='yes',owned_confirmed='yes',note='Small mark'),release_id,currency,required)
  self.env=patch.dict(os.environ,{'OPENAI_API_KEY':'TEST-KEY','OPENAI_LISTING_MODEL':'TEST-MODEL'});self.env.start()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def response(self,text='Small mark.'):
  return io.BytesIO(json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}]}).encode())
 def test_only_facts_sent_and_suggestion_never_saved(self):
  def transport(req,timeout):
   body=json.loads(req.data);facts=json.loads(body['input'])
   self.assertEqual(set(facts),{'artist','title','format','media_cond','sleeve_cond','note'})
   self.assertFalse(body['store']);self.assertEqual(timeout,20)
   return self.response()
  result=ai_listing.suggest(self.s,1,transport)
  self.assertFalse(result['saved']);self.assertEqual(result['suggestion'],'Small mark.')
  with connect(self.s.db_path) as c:self.assertEqual(c.execute('SELECT note FROM listing_drafts').fetchone()[0],'Small mark')
 def test_missing_settings_and_stale_draft_do_not_call_provider(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
   with self.assertRaisesRegex(ValueError,'尚未設定'):ai_listing.suggest(self.s,1,lambda *a: self.fail('network'))
  with connect(self.s.db_path) as c:c.execute("UPDATE listing_drafts SET created_at='2000-01-01T00:00:00+00:00'")
  with self.assertRaisesRegex(ValueError,'48 小時'):ai_listing.suggest(self.s,1,lambda *a:self.fail('network'))
 def test_incomplete_oversized_and_failed_outputs_are_rejected_without_retry(self):
  for raw in [b'{}',b'not json',b'x'*100001,json.dumps({'status':'incomplete'}).encode()]:
   with self.assertRaises(ValueError):ai_listing.suggest(self.s,1,lambda *a,**k:io.BytesIO(raw))
  with self.assertRaisesRegex(ValueError,'220'):ai_listing.suggest(self.s,1,lambda *a,**k:self.response('x'*221))
  with patch('ai_listing.urlopen') as unused:
   calls=[]
   def fail(*a,**k):calls.append(1);raise TimeoutError('secret payload')
   with self.assertRaisesRegex(ValueError,'未儲存') as error:ai_listing.suggest(self.s,1,fail)
   self.assertNotIn('secret',str(error.exception));self.assertEqual(len(calls),1)
 def test_endpoint_and_capability_are_connected(self):
  app=Dashboard(self.s)
  with patch('ai_listing.suggest',return_value={'suggestion':'TEST','saved':False}) as generate:
   self.assertFalse(app.mutate('/api/drafts/suggest-note',{'draft_id':'1'})['saved']);generate.assert_called_once_with(self.s,1)
  self.assertTrue(app.state()['configured']['ai_listing'])
