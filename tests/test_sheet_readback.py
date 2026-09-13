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
