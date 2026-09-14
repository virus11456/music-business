import json,tempfile,unittest
from pathlib import Path
from password_login import PasswordLogin,password_hash
class PasswordTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'auth.json';self.now=100
  self.path.write_text(json.dumps({'username':'admin','salt':'ab'*16,'hash':password_hash('valid-password-123','ab'*16)}))
  self.auth=PasswordLogin(self.path,clock=lambda:self.now)
 def test_login_expiration_and_logout(self):
  code,data=self.auth.login('admin','valid-password-123');self.assertEqual(code,200);token=data['session_token'];self.assertTrue(self.auth.valid(token));self.assertFalse(self.auth.valid('other'))
  self.now+=8*3600;self.assertFalse(self.auth.valid(token))
  _,d=self.auth.login('admin','valid-password-123');self.auth.revoke(d['session_token']);self.assertFalse(self.auth.valid(d['session_token']))
 def test_errors_do_not_reveal_account(self):
  self.assertEqual(self.auth.login('wrong','valid-password-123'),self.auth.login('admin','wrong'))
 def test_rate_limit_and_recovery(self):
  for _ in range(10):self.assertEqual(self.auth.login('admin','wrong')[0],401)
  self.assertEqual(self.auth.login('admin','valid-password-123')[0],429);self.now+=60;self.assertEqual(self.auth.login('admin','valid-password-123')[0],200)
 def test_missing_malformed_configuration(self):
  for content in ['{}','bad','{"username":null}']:
   self.path.write_text(content);self.assertEqual(self.auth.login('admin','anything')[0],503)
 def test_bad_input(self):
  for u,p in [(None,'x'),('admin',None),('admin','x'*1025)]:self.assertEqual(self.auth.login(u,p)[0],401)

class ResetTests(PasswordTests):
 def test_reset_is_single_use_and_revokes_sessions(self):
  _,session=self.auth.login('admin','valid-password-123');token=self.auth.issue_reset()
  self.assertNotIn(token,self.auth.reset_path.read_text())
  self.assertEqual(self.auth.reset(token,'frank','new-password-value-123')[0],200)
  self.assertFalse(self.auth.valid(session['session_token']))
  self.assertEqual(self.auth.reset(token,'other','new-password-value-123')[0],400)
  self.assertEqual(self.auth.login('frank','new-password-value-123')[0],200)
  self.assertEqual(self.auth.login('admin','valid-password-123')[0],401)
 def test_invalid_expired_and_short_password_preserve_account(self):
  token=self.auth.issue_reset();original=self.path.read_text()
  self.assertEqual(self.auth.reset('z'*43,'admin','new-password-value-123')[0],400)
  self.assertEqual(self.auth.reset(token,'admin','short')[0],400)
  record=json.loads(self.auth.reset_path.read_text());record['expires']=0;self.auth.reset_path.write_text(json.dumps(record))
  self.assertEqual(self.auth.reset(token,'admin','new-password-value-123')[0],400)
  self.assertEqual(self.path.read_text(),original)
 def test_concurrent_consumption_only_one_wins(self):
  from concurrent.futures import ThreadPoolExecutor
  token=self.auth.issue_reset();other=PasswordLogin(self.path)
  with ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(lambda a:a.reset(token,'frank','new-password-value-123')[0],[self.auth,other]))
  self.assertEqual(sorted(results),[200,400])

class LoginRouteTests(unittest.TestCase):
 def request(self,origin='https://music-business.vercel.app',payload=None,content_type='application/json',path='/api/login'):
  import io,os
  from unittest.mock import patch
  from types import SimpleNamespace
  from remote_access import RemoteAccess
  from server import handler
  with patch.dict(os.environ,{'REMOTE_ACCESS_TOKEN':'x'*40,'FRONTEND_ORIGIN':'https://music-business.vercel.app','PUBLIC_API_ORIGIN':'https://api.example.com'}):access=RemoteAccess()
  calls=[];access.passwords.login=lambda u,p:(calls.append((u,p)) or (401,{'error':'帳號或密碼不正確'}))
  cls=handler(SimpleNamespace(access=access,csrf='csrf'))
  h=object.__new__(cls);h.path=path;body=json.dumps(payload if payload is not None else {'username':'admin','password':'wrong'}).encode()
  h.headers={'Host':'api.example.com','Origin':origin,'Content-Type':content_type,'Content-Length':str(len(body))};h.rfile=io.BytesIO(body);results=[];h.respond=lambda code,data:results.append((code,data));h.do_POST();return results,calls
 def test_cross_origin_login_is_blocked_before_password(self):
  for origin in ['', 'https://evil.example']:
   result,calls=self.request(origin);self.assertEqual(result[0][0],403);self.assertEqual(calls,[])
 def test_login_checks_password_without_existing_session(self):
  result,calls=self.request();self.assertEqual(result[0][0],401);self.assertEqual(len(calls),1)
 def test_malformed_payload_rejected(self):
  result,calls=self.request(payload=[]);self.assertEqual(result[0][0],400);self.assertEqual(calls,[])
 def test_non_json_rejected(self):
  result,calls=self.request(content_type='text/plain');self.assertEqual(result[0][0],415);self.assertEqual(calls,[])

 def test_reset_link_cannot_be_requested_without_login(self):
  result,calls=self.request(path='/api/account/reset-link');self.assertEqual(result[0][0],401);self.assertEqual(calls,[])
 def test_reset_needs_token_and_rejects_other_origin(self):
  result,calls=self.request(path='/api/account/reset');self.assertEqual(result[0][0],400)
  result,calls=self.request(path='/api/account/reset',origin='https://evil.example');self.assertEqual(result[0][0],403)
