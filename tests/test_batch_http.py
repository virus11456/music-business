"""Exercise real HTTP parsing/dispatch in memory; no socket or network claim."""
import io,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from config import Settings
from db import init
import demo
from server import Dashboard,handler

class MemoryConnection:
 def __init__(self,raw):self.input=io.BytesIO(raw);self.output=bytearray()
 def makefile(self,*args,**kwargs):return self.input
 def sendall(self,data):self.output.extend(data)

class BatchHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s);self.app=Dashboard(self.s)
 def tearDown(self):self.tmp.cleanup()
 def post(self,path,data,csrf=True):
  body=json.dumps(data).encode()
  headers=['POST '+path+' HTTP/1.1','Host: 127.0.0.1:8765','Origin: http://127.0.0.1:5173','Content-Type: application/json','Connection: close','Content-Length: '+str(len(body))]
  if csrf:headers.append('X-CSRF-Token: '+self.app.csrf)
  conn=MemoryConnection(('\r\n'.join(headers)+'\r\n\r\n').encode()+body)
  handler(self.app)(conn,('127.0.0.1',12345),SimpleNamespace())
  head,body=bytes(conn.output).split(b'\r\n\r\n',1)
  return int(head.split()[1]),json.loads(body)
 def test_offer_to_batch_through_actual_http_handler(self):
  offer={'release_id':900000001,'vendor':'TEST','source_url':'https://example.com/test','amount':'4500','currency':'JPY','sale_price':'80','sale_currency':'USD','media_cond':'Very Good (VG)','sleeve_cond':'No Cover','version_confirmed':'yes','supply_confirmed':'yes','dispatch_days':'7'}
  self.assertEqual(self.post('/api/offers',offer)[0],200)
  oid=self.app.state()['workflow']['offers'][0]['id']
  status,result=self.post('/api/drafts/batch',{'offer_ids':[oid]})
  self.assertEqual(status,200);self.assertEqual(result['created'],1)
  status,result=self.post('/api/drafts/batch',{'offer_ids':[oid]})
  self.assertEqual(status,200);self.assertEqual(result['skipped'],1)
 def test_validation_returns_specific_json_error(self):
  status,result=self.post('/api/drafts/batch',{'offer_ids':[999]})
  self.assertEqual(status,400);self.assertIn('報價 #999',result['error'])
  self.assertEqual(self.app.state()['workflow']['drafts'],[])
 def test_csrf_is_required(self):
  status,result=self.post('/api/drafts/batch',{'offer_ids':[1]},csrf=False)
  self.assertEqual(status,403);self.assertIn('error',result)
