import os,unittest
from unittest.mock import patch
from remote_access import RemoteAccess

class RemoteTests(unittest.TestCase):
 def setUp(self):
  self.env={'REMOTE_ACCESS_TOKEN':'x'*40,'FRONTEND_ORIGIN':'https://music-business.vercel.app','PUBLIC_API_ORIGIN':'https://api.example.com'}
 def test_auth_and_origin(self):
  with patch.dict(os.environ,self.env):access=RemoteAccess()
  h={'Host':'api.example.com','Origin':self.env['FRONTEND_ORIGIN']}
  self.assertEqual(access.allowed(h),401)
  h['Authorization']='Bearer '+'x'*40;self.assertEqual(access.allowed(h),200)
  h['Origin']='https://evil.example';self.assertEqual(access.allowed(h),403)
 def test_localhost_not_auth_bypass(self):
  with patch.dict(os.environ,self.env):access=RemoteAccess()
  self.assertEqual(access.allowed({'Host':'localhost:8765'}),401)
 def test_invalid_secret_is_rejected(self):
  with patch.dict(os.environ,{**self.env,'REMOTE_ACCESS_TOKEN':'short'}):
   with self.assertRaises(ValueError):RemoteAccess()
 def test_https_required(self):
  with patch.dict(os.environ,{**self.env,'PUBLIC_API_ORIGIN':'http://api.example.com'}):
   with self.assertRaises(ValueError):RemoteAccess()
