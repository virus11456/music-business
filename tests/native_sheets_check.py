"""Opt-in native Sheets verification; creates and removes six unique QA tabs."""
import sys,os,tempfile,json,uuid,argparse,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_full_workflow import run_flow
from config import load_env,Settings
from db import connect
import sheet_sync
from unittest.mock import patch
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession
load_env()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sheet-id',required=True)
args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_-]+',args.sheet_id):parser.error('Invalid sheet ID')
base='https://sheets.googleapis.com/v4/spreadsheets/'+args.sheet_id
session=AuthorizedSession(Credentials.from_service_account_file(os.environ['GOOGLE_SERVICE_ACCOUNT_FILE'],scopes=['https://www.googleapis.com/auth/spreadsheets']))
prefix='SIMPLES_QA_'+uuid.uuid4().hex[:10]+'_'
def request(method,url,**kw):
 r=session.request(method,url,timeout=40,**kw);r.raise_for_status();return r.json()
def read():return request('GET',base+'/values/'+prefix+'Analysis!A2:L4',params={'valueRenderOption':'UNFORMATTED_VALUE'})['values']
def put(cell,value):return request('PUT',base+'/values/'+prefix+cell,params={'valueInputOption':'RAW'},json={'values':[[value]]})
def verify(settings):
 with connect(settings.db_path) as c:c.execute("INSERT OR REPLACE INTO meta VALUES('google_sheet_id',?)",(base.rsplit('/',1)[1],))
 try:
  with patch('sheet_sync.PREFIX',prefix):sheet_sync.sync(settings,session=session)
  rows=read();assert len(rows)==3,rows
  for row in rows:
   assert row[2]==2560 and row[3]==990 and abs(row[5]-612.8)<.001 and row[9]==1570,row
  put('Inputs!B11','');assert all(r[5]=='待補資料' for r in read())
  put('Inputs!B11',.22);put('Sources!H2',False);assert read()[0][7]=='待核對版本'
  put('Sources!H2',True);put('Sources!D2',20000);assert read()[0][8]=='暫無空間'
  print(json.dumps({'native_sheets':True,'three_formats':True,'missing_fx_blocked':True,'version_check':True,'loss_check':True}))
 finally:
  info=request('GET',base,params={'fields':'sheets(properties)'})
  ids=[s['properties']['sheetId'] for s in info['sheets'] if s['properties']['title'].startswith(prefix)]
  if ids:request('POST',base+':batchUpdate',json={'requests':[{'deleteSheet':{'sheetId':sid}} for sid in ids]})
  print(json.dumps({'temporary_sheets_removed':len(ids)}))
with tempfile.TemporaryDirectory() as tmp:
 print(json.dumps(run_flow(Settings(db_path=Path(tmp)/'qa.db',token='TEST-NOT-REAL'),verify)))
