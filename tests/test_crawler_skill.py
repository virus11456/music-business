import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('crawler_inspector', ROOT/'.agents/skills/record-source-crawlers/scripts/inspect_crawlers.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class CrawlerSkillTests(unittest.TestCase):
    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'missing.db'
            with self.assertRaises(FileNotFoundError): inspector.inspect(p)
            self.assertFalse(p.exists())

    def test_missing_schema_is_not_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'empty.db'
            sqlite3.connect(p).close()
            before = p.read_bytes()
            with self.assertRaises(ValueError): inspector.inspect(p)
            self.assertEqual(before, p.read_bytes())

    def test_readonly_counts_changed_identity_failures_and_stale_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'source ?#.db'
            with sqlite3.connect(p) as c:
                c.executescript('''
CREATE TABLE platform_candidates(id INTEGER,platform TEXT,title TEXT,artist TEXT,format TEXT,catalog_no TEXT,captured_at TEXT);
CREATE TABLE platform_runs(id INTEGER,platform TEXT,count INTEGER,status TEXT,recorded_at TEXT);
CREATE TABLE source_checks(candidate_id INTEGER,fingerprint TEXT,retry_at TEXT,status TEXT);
CREATE TABLE meta(key TEXT,value TEXT);
''')
                source = dict(title='TEST', artist='Test', format='CD', catalog_no='TEST-001')
                for i in range(1,5):
                    c.execute('INSERT INTO platform_candidates VALUES(?,?,?,?,?,?,?)',(i,'ruten',*source.values(),'2026-09-12T00:00:00+00:00' if i==1 else 'invalid'))
                c.executemany('INSERT INTO source_checks VALUES(?,?,?,?)',[
                    (2,inspector.fingerprint(source),'2026-10-01T00:00:00+00:00','matched'),
                    (3,'old-identity','2026-10-01T00:00:00+00:00','unmatched'),
                    (4,inspector.fingerprint(source),'invalid','failed')])
                c.execute("INSERT INTO platform_runs VALUES(1,'ruten',0,'讀取失敗','2026-09-12')")
                c.execute("INSERT INTO meta VALUES('schedule_slot:2026-09-12T10:00:00+08:00','partial')")
                c.execute("INSERT INTO meta VALUES('private_secret','MUST-NOT-APPEAR')")
            before=p.read_bytes()
            result=inspector.inspect(p,datetime(2026,9,12,4,tzinfo=timezone.utc))
            self.assertEqual(result['queue']['due'],3)
            self.assertEqual(result['queue']['cached'],1)
            self.assertEqual(result['queue']['unchecked'],1)
            self.assertEqual(result['queue']['invalid_retry_at'],1)
            self.assertEqual(result['platforms']['ruten']['stale_or_unknown_quotes'],3)
            self.assertEqual(result['platforms']['ruten']['last_collection']['status'],'讀取失敗')
            self.assertIsNone(result['schedule']['enabled'])
            self.assertNotIn('MUST-NOT-APPEAR',str(result))
            self.assertEqual(before,p.read_bytes())
