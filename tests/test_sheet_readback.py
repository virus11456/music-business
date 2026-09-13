import unittest
from unittest.mock import patch
from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace
import sheet_sync

class ReadbackTests(unittest.TestCase):
    def check(self, mismatch):
        c=sqlite3.connect(':memory:')
        c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
        c.execute("INSERT INTO meta VALUES('google_sheet_id','test123')")
        @contextmanager
        def connection(path):yield c
        class Response:
            status_code=200
            def __init__(self,data):self.data=data
            def json(self):return self.data
        class Session:
            def request(self,method,url,**kwargs):
                if url.endswith('/values:batchGet'):
                    return Response({'valueRanges':[{'values':[['id'],[2 if mismatch else 1]]} for _ in range(2)]})
                return Response({'sheets':[]})
        try:
            with patch('sheet_sync.connect',connection),patch('sheet_sync.build_tables',return_value=({'Sources':[['id'],[1]],'Discogs':[['id'],[1]]},set())):
                if mismatch:
                    with self.assertRaises(ValueError):sheet_sync.sync(SimpleNamespace(db_path=None),Session())
                    self.assertIsNone(c.execute("SELECT value FROM meta WHERE key='last_sheet_sync'").fetchone())
                else:
                    self.assertTrue(sheet_sync.sync(SimpleNamespace(db_path=None),Session())['verification']['ok'])
                    self.assertIsNotNone(c.execute("SELECT value FROM meta WHERE key='last_sheet_sync'").fetchone())
        finally:c.close()
    def test_success_after_readback(self):self.check(False)
    def test_mismatch_not_marked_success(self):self.check(True)

    def test_failure_reports_only_safe_fields(self):
        from sync_failure import SyncFailure,report
        failure=SyncFailure('readback_mismatch',['Comparisons','secret-token'])
        self.assertEqual(report(failure)['tables'],['Comparisons'])
        self.assertNotIn('secret',str(report(ValueError('secret'))))

    def test_unknown_write_and_rejected_write_are_distinct(self):
        from sync_failure import SyncFailure
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from db import init,connect
        from config import Settings
        with TemporaryDirectory() as tmp:
            settings=Settings(db_path=Path(tmp)/'test.db');init(settings.db_path)
            with connect(settings.db_path) as c:c.execute("INSERT INTO meta VALUES('google_sheet_id','test123')")
            class Response:
                status_code=200
                def json(self):return {'sheets':[]}
            class Session:
                def __init__(self, rejected):self.rejected=rejected
                def request(self,method,url,**kwargs):
                    if method=='GET':return Response()
                    if not self.rejected:raise TimeoutError('private upstream text')
                    r=Response();r.status_code=403;return r
            for rejected,code in [(False,'write_unknown'),(True,'write_rejected')]:
                with patch('sheet_sync.build_tables',return_value=({'Sources':[['id']],'Discogs':[['id']]},set())):
                    with self.assertRaises(SyncFailure) as raised:sheet_sync.sync(settings,Session(rejected))
                self.assertEqual(raised.exception.code,code)

    def test_unchanged_skips_post_but_checks_again(self):
        c=sqlite3.connect(':memory:');c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)');c.execute("INSERT INTO meta VALUES('google_sheet_id','test123')")
        @contextmanager
        def connection(path):yield c
        class Response:
            status_code=200
            def __init__(self,data):self.data=data
            def json(self):return self.data
        calls=[]
        class Session:
            def request(self,method,url,**kwargs):
                calls.append((method,url))
                if url.endswith('/values:batchGet'):return Response({'valueRanges':[{'values':[['id'],[1]]} for _ in range(2)]})
                return Response({'sheets':[{'properties':{'title':'SIMPLES_'+n,'sheetId':i},'developerMetadata':[{'metadataKey':'simples_owner','metadataValue':'record_business_v1'}]} for i,n in enumerate(['Sources','Discogs'])]})
        try:
            with patch('sheet_sync.connect',connection),patch('sheet_sync.build_tables',return_value=({'Sources':[['id'],[1]],'Discogs':[['id'],[1]]},set())):
                result=sheet_sync.sync(SimpleNamespace(db_path=None),Session())
            self.assertEqual(result['changed_tables'],[])
            self.assertEqual(len(result['unchanged_tables']),2)
            self.assertFalse(any(m=='POST' for m,u in calls))
            self.assertEqual(sum(u.endswith('/values:batchGet') for m,u in calls),2)
        finally:c.close()
