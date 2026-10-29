"""The state endpoint compresses large bodies and answers 304 for an unchanged validator."""
import gzip,io,json,os,unittest
from types import SimpleNamespace
from unittest.mock import patch
from remote_access import RemoteAccess
from server import handler

STATE={'csrf':'SECRET','records':[{'release_id':1,'artist':'A','title':'B'*3000,'format':'CD','snapshot':None}],'workflow':{'comparisons':[]}}

class FakeRequest:
 def __init__(self,app,headers):
  h=object.__new__(handler(app));h.path='/api/state';h.headers=headers;h.command='GET';h.request_version='HTTP/1.1';h.requestline='GET /api/state HTTP/1.1';h.client_address=('127.0.0.1',0);h.wfile=io.BytesIO();h.close_connection=False;self.h=h
 def run(self):
  self.h.do_GET();raw=self.h.wfile.getvalue();head,_,body=raw.partition(b'\r\n\r\n');lines=head.decode().split('\r\n');status=int(lines[0].split()[1])
  headers={k.lower():v for k,v in (l.split(': ',1) for l in lines[1:])};return status,headers,body

class TransportTests(unittest.TestCase):
 def app(self):
  with patch.dict(os.environ,{'REMOTE_ACCESS_TOKEN':'x'*40,'FRONTEND_ORIGIN':'https://music-business.vercel.app','PUBLIC_API_ORIGIN':'https://api.example.com'}):access=RemoteAccess()
  return SimpleNamespace(access=access,csrf='SECRET',state=lambda:json.loads(json.dumps(STATE)))
 def headers(self,**extra):
  return {'Host':'api.example.com','Origin':'https://music-business.vercel.app','Authorization':'Bearer '+'x'*40,**extra}
 def test_gzip_when_accepted_and_identity_otherwise(self):
  app=self.app()
  status,headers,body=FakeRequest(app,self.headers(**{'Accept-Encoding':'gzip, deflate, br'})).run()
  self.assertEqual(status,200);self.assertEqual(headers['content-encoding'],'gzip');self.assertEqual(headers['content-length'],str(len(body)))
  self.assertEqual(json.loads(gzip.decompress(body)),STATE);self.assertIn('etag',headers);self.assertEqual(headers['cache-control'],'no-store')
  status,headers,body=FakeRequest(app,self.headers()).run()
  self.assertNotIn('content-encoding',headers);self.assertEqual(json.loads(body),STATE)
 def test_matching_validator_returns_304_without_body_and_changes_with_data(self):
  app=self.app()
  _,headers,_=FakeRequest(app,self.headers()).run();etag=headers['etag']
  status,headers,body=FakeRequest(app,self.headers(**{'If-None-Match':etag,'Accept-Encoding':'gzip'})).run()
  self.assertEqual((status,body),(304,b''));self.assertEqual(headers['etag'],etag)
  app.state=lambda:{**json.loads(json.dumps(STATE)),'active':{'name':'job'}}
  status,headers,body=FakeRequest(app,self.headers(**{'If-None-Match':etag})).run()
  self.assertEqual(status,200);self.assertNotEqual(headers['etag'],etag);self.assertEqual(json.loads(body)['active'],{'name':'job'})
 def test_anonymous_catalogue_also_validates_and_never_matches_admin_tag(self):
  app=self.app()
  _,admin,_=FakeRequest(app,self.headers()).run()
  status,headers,body=FakeRequest(app,{'Host':'api.example.com','Origin':'https://music-business.vercel.app'}).run()
  self.assertEqual(status,200);self.assertNotIn('SECRET',body.decode());self.assertNotEqual(headers['etag'],admin['etag'])
  status,_,body=FakeRequest(app,{'Host':'api.example.com','Origin':'https://music-business.vercel.app','If-None-Match':headers['etag']}).run()
  self.assertEqual((status,body),(304,b''))
  status,_,_=FakeRequest(app,{'Host':'api.example.com','Origin':'https://music-business.vercel.app','If-None-Match':admin['etag']}).run()
  self.assertEqual(status,200)
 def test_small_error_bodies_are_not_compressed_and_other_paths_have_no_validator(self):
  app=self.app()
  r=FakeRequest(app,self.headers(**{'Accept-Encoding':'gzip'}));r.h.path='/api/nothing';status,headers,body=r.run()
  self.assertEqual(status,404);self.assertNotIn('content-encoding',headers);self.assertNotIn('etag',headers)

class MatchingPayloadTests(unittest.TestCase):
 def test_version_searches_limited_to_requested_candidates(self):
  import tempfile
  from pathlib import Path
  from config import Settings
  from db import init,connect
  import matching,platforms
  tmp=tempfile.TemporaryDirectory();s=Settings(db_path=Path(tmp.name)/'qa.db');init(s.db_path);platforms.init(s);matching.init(s)
  try:
   with connect(s.db_path) as c:
    for i in (1,2,3):
     c.execute("INSERT INTO platform_candidates(id,platform,external_id,query,title,artist,format,catalog_no,price,currency,price_kind,availability,source_url,captured_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(i,'tower',str(i),'q','t','a','CD','','1','JPY','fixed','x',f'https://t/{i}','2026'))
     c.execute('INSERT INTO version_searches VALUES(?,?,?,?)',(i,'{}','[]','2026'))
   self.assertEqual(set(matching.state(s)),{'1','2','3'})
   self.assertEqual(set(matching.state(s,[3,1,3])),{'1','3'});self.assertEqual(matching.state(s,[]),{})
  finally:tmp.cleanup()
