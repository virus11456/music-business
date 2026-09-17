import json,os,unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from public_catalog import public_catalog
from remote_access import RemoteAccess
from server import handler

class PublicCatalogTests(unittest.TestCase):
 def fixture(self):
  return {'csrf':'SECRET','records':[{'release_id':1,'artist':'A','title':'B','format':'CD','cost':{'source':'PRIVATE'},'decision':{'decision':'want'},'snapshot':{'want':3,'lowest_price':'30','internal':'PRIVATE'}}], 'workflow':{'comparisons':[{'key':'candidate-1-1','release_id':1,'offer':None,'gross_twd':'20','gross_margin':.2,'source_url':'https://example.com/1','internal':'PRIVATE'},{'key':'offer-1','offer':{'note':'PRIVATE'}}],'purchase_list':{'picks':['PRIVATE']},'drafts':['PRIVATE']},'jobs':['PRIVATE'],'new_private_field':'PRIVATE'}
 def test_projection_excludes_nested_private_data_and_manual_offers(self):
  state=self.fixture();before=deepcopy(state);public=public_catalog(state)
  self.assertEqual(state,before)
  self.assertNotIn('PRIVATE',json.dumps(public));self.assertNotIn('SECRET',json.dumps(public))
  self.assertEqual(public['permissions'],{'can_write':False})
  self.assertEqual(len(public['workflow']['comparisons']),1)
  self.assertEqual(public['workflow']['comparisons'][0]['gross_twd'],'20')
 def request(self,path='/api/state',method='GET',auth='',origin='https://music-business.vercel.app',host='api.example.com'):
  with patch.dict(os.environ,{'REMOTE_ACCESS_TOKEN':'x'*40,'FRONTEND_ORIGIN':'https://music-business.vercel.app','PUBLIC_API_ORIGIN':'https://api.example.com'}):access=RemoteAccess()
  app=SimpleNamespace(access=access,csrf='SECRET',state=self.fixture)
  h=object.__new__(handler(app));h.path=path;h.headers={'Host':host,'Origin':origin,'Authorization':auth};result=[];h.respond=lambda code,data:result.append((code,data));getattr(h,'do_'+method)();return result[0]
 def test_anonymous_can_read_only_catalogue(self):
  code,data=self.request();self.assertEqual(code,200);self.assertFalse(data['permissions']['can_write'])
 def test_private_exports_and_writes_stay_blocked(self):
  for path in ['/api/drafts/export','/api/drafts/quicklister?id=1','/api/state?private=1']:
   self.assertEqual(self.request(path)[0],401)
  for path in ['/api/releases','/api/purchase-list','/api/drafts','/api/refresh']:
   self.assertEqual(self.request(path,method='POST')[0],401)
 def test_invalid_credentials_do_not_downgrade_to_public(self):
  self.assertEqual(self.request(auth='Bearer wrong')[0],401)
 def test_origin_and_host_still_checked(self):
  self.assertEqual(self.request(origin='https://evil.example')[0],403)
  self.assertEqual(self.request(host='evil.example')[0],403)
 def test_authenticated_admin_retains_original_state(self):
  code,data=self.request(auth='Bearer '+'x'*40);self.assertEqual(code,200);self.assertEqual(data['csrf'],'SECRET');self.assertIn('purchase_list',data['workflow'])
