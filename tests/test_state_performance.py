"""Sheet-primary reads must not pay for table comparison; refreshes must not block requests."""
import copy,os,threading,time,unittest
from unittest.mock import patch
import sheet_primary
from sheet_records import capture,compare
from sheet_primary import PrimaryStore,memory_schema

class Repository:
    def __init__(self):
        c=memory_schema()
        c.execute("INSERT INTO meta VALUES('mode','live')")
        c.execute("INSERT INTO releases VALUES(1,'first',NULL,2000,'JP','CD','00001',NULL,'2026-09-13','')")
        self.data=capture(c);c.close();self.reads=0;self.writes=0;self.gate=None;self.fail_reads=False
    def read(self,names):
        self.reads+=1
        if self.fail_reads:raise ValueError('sheet unavailable')
        if self.gate:self.gate.wait(5)
        return {n:copy.deepcopy(self.data[n]) for n in names}
    def replace(self,old,new):
        if not compare(old,{n:self.data[n] for n in old})['equal']:raise ValueError('conflict')
        self.data.update(copy.deepcopy(new));self.writes+=1

def title(store):
    with store.connect() as c:return c.execute('SELECT title FROM releases WHERE release_id=1').fetchone()[0]

class CheapReadTests(unittest.TestCase):
    def test_read_only_connections_never_compare_tables(self):
        repo=Repository();store=PrimaryStore(repo);calls=[]
        real=sheet_primary.capture
        with patch('sheet_primary.capture',side_effect=lambda c:(calls.append(1),real(c))[1]):
            for _ in range(5):title(store)
            self.assertEqual(calls,[])
            with store.connect() as c:c.execute("UPDATE releases SET title='changed' WHERE release_id=1")
            self.assertEqual(len(calls),2);self.assertEqual(repo.writes,1)
            self.assertEqual(repo.data['releases'][1][1],'changed')
            with store.connect() as c:c.execute("UPDATE releases SET title='changed' WHERE release_id=999")
            self.assertEqual(len(calls),2);self.assertEqual(repo.writes,1)
    def test_local_only_tables_change_version_but_not_sheet(self):
        repo=Repository();store=PrimaryStore(repo);before=store.version()
        with store.connect() as c:c.execute('INSERT INTO api_budget VALUES(1,1)')
        self.assertNotEqual(store.version(),before);self.assertEqual(repo.writes,0)
        self.assertEqual(store.version(),store.version())
    def test_failed_transaction_still_restores_and_forces_reread(self):
        repo=Repository();store=PrimaryStore(repo);title(store)
        repo.data['releases'][1][1]='remote'
        with self.assertRaises(RuntimeError):
            with store.connect() as c:
                c.execute("UPDATE releases SET title='local'");raise RuntimeError()
        self.assertEqual(repo.reads,1)
        self.assertEqual(title(store),'remote');self.assertEqual(repo.reads,2)

class BackgroundRefreshTests(unittest.TestCase):
    def wait_idle(self,store):
        if store.refresh_thread:store.refresh_thread.join(5)
    def test_expired_view_is_served_while_refresh_runs_then_swapped(self):
        repo=Repository();store=PrimaryStore(repo,ttl=0);self.assertEqual(title(store),'first')
        repo.data['releases'][1][1]='edited in sheet';repo.gate=threading.Event()
        started=time.perf_counter();self.assertEqual(title(store),'first');self.assertLess(time.perf_counter()-started,1)
        self.assertEqual(store.status()['refreshing'],True)
        repo.gate.set();self.wait_idle(store)
        self.assertEqual(title(store),'edited in sheet');self.assertEqual(store.generation,2)
    def test_write_during_refresh_keeps_local_view_and_retries(self):
        repo=Repository();store=PrimaryStore(repo,ttl=0);title(store)
        repo.gate=threading.Event();title(store)  # background read is now waiting on the gate
        with store.connect() as c:c.execute("UPDATE releases SET title='written locally' WHERE release_id=1")
        repo.gate.set();self.wait_idle(store)
        self.assertEqual(store.generation,1);self.assertEqual(title(store),'written locally')
        self.wait_idle(store);self.assertEqual(title(store),'written locally');self.assertEqual(store.generation,2)
    def test_failed_refresh_keeps_serving_and_retries_after_backoff(self):
        repo=Repository();store=PrimaryStore(repo,ttl=0,retry=0);title(store)
        repo.fail_reads=True;self.assertEqual(title(store),'first');self.wait_idle(store)
        self.assertEqual(store.status()['refresh_error'],'ValueError');self.assertEqual(title(store),'first');self.wait_idle(store)
        repo.fail_reads=False;repo.data['releases'][1][1]='recovered';title(store);self.wait_idle(store)
        self.assertEqual(title(store),'recovered');self.assertIsNone(store.status()['refresh_error'])
    def test_startup_without_view_loads_synchronously(self):
        repo=Repository();store=PrimaryStore(repo,ttl=0)
        self.assertEqual(title(store),'first');self.assertEqual(repo.reads,1)

class DerivedStateCacheTests(unittest.TestCase):
    def test_state_reuses_derived_views_until_data_changes(self):
        import demo
        from config import Settings
        from server import Dashboard
        repo=Repository();store=PrimaryStore(repo)
        with patch.dict(os.environ,{'DATA_BACKEND':'google_sheets','GOOGLE_SPREADSHEET_ID':'x'*30}),patch.object(sheet_primary,'_store',store):
            app=Dashboard(Settings())
            # The first derivation after a data change may itself fill match caches, which moves the version once more.
            app.state();first=app.state();second=app.state()
            self.assertIs(first['workflow'],second['workflow']);self.assertIs(first['records'],second['records'])
            self.assertEqual(first['storage']['backend'],'google_sheets');self.assertIn('loaded_seconds_ago',first['storage'])
            with sheet_primary.instance().connect() as c:c.execute("UPDATE releases SET title='renamed' WHERE release_id=1")
            third=app.state()
            self.assertIsNot(second['records'],third['records']);self.assertEqual(third['records'][0]['title'],'renamed')
            app.state();self.assertIs(app.state()['workflow'],app.state()['workflow'])
    def test_sqlite_mode_never_caches(self):
        import tempfile
        from pathlib import Path
        from config import Settings
        from db import init
        from server import Dashboard
        import demo
        tmp=tempfile.TemporaryDirectory();s=Settings(db_path=Path(tmp.name)/'qa.db');init(s.db_path);demo.seed(s);app=Dashboard(s)
        try:self.assertIsNot(app.state()['workflow'],app.state()['workflow']);self.assertNotIn('loaded_seconds_ago',app.state()['storage'])
        finally:tmp.cleanup()
