import copy
import sqlite3
import unittest
from sheet_records import capture, compare, decode, TABLES
from sheet_primary import PrimaryStore, memory_schema

class Repository:
    def __init__(self):
        c=memory_schema()
        c.execute("INSERT INTO meta VALUES('mode','live')")
        c.execute("INSERT INTO releases VALUES(1,'00123',NULL,2000,'JP','CD','00001',NULL,'2026-09-13','')")
        self.data=capture(c);c.close();self.writes=0;self.fail=False
    def read(self,names):return {n:copy.deepcopy(self.data[n]) for n in names}
    def replace(self,old,new):
        if not compare(old,{n:self.data[n] for n in old})['equal']:raise ValueError('conflict')
        self.data.update(copy.deepcopy(new));self.writes+=1
        if self.fail:raise ValueError('unknown result')

class SheetPrimaryTests(unittest.TestCase):
    def test_restart_reads_cloud_without_disk_and_preserves_null_empty_codes(self):
        repo=Repository();store=PrimaryStore(repo)
        with store.connect() as c:
            r=c.execute('SELECT * FROM releases').fetchone()
            self.assertEqual((r['title'],r['artist'],r['notes'],r['catno']),('00123',None,'','00001'))
            c.execute("UPDATE releases SET title='Changed' WHERE release_id=1")
        with PrimaryStore(repo).connect() as c:
            self.assertEqual(c.execute('SELECT title FROM releases').fetchone()[0],'Changed')
            self.assertEqual(c.execute('PRAGMA database_list').fetchone()[2],'')
    def test_unknown_write_is_read_back_no_duplicate_retry(self):
        repo=Repository();store=PrimaryStore(repo);repo.fail=True
        with self.assertRaises(ValueError):
            with store.connect() as c:c.execute("UPDATE releases SET title='Saved remotely' WHERE release_id=1")
        repo.fail=False
        with store.connect() as c:self.assertEqual(c.execute('SELECT title FROM releases').fetchone()[0],'Saved remotely')
        self.assertEqual(repo.writes,1)
    def test_failed_local_transaction_never_writes_sheet(self):
        repo=Repository();store=PrimaryStore(repo)
        with self.assertRaises(RuntimeError):
            with store.connect() as c:
                c.execute("UPDATE releases SET title='not saved'")
                raise RuntimeError()
        self.assertEqual(repo.writes,0)
        with store.connect() as c:self.assertEqual(c.execute('SELECT title FROM releases').fetchone()[0],'00123')
    def test_external_edit_conflict_is_not_overwritten(self):
        repo=Repository();store=PrimaryStore(repo)
        with self.assertRaises(ValueError):
            with store.connect() as c:
                repo.data['releases'][1][1]='other device'
                c.execute("UPDATE releases SET title='this device'")
        self.assertEqual(repo.data['releases'][1][1],'other device')
    def test_missing_table_or_broken_relationship_blocks_loading(self):
        repo=Repository();repo.data.pop('releases')
        with self.assertRaises(KeyError):
            with PrimaryStore(repo).connect():pass
        repo=Repository();repo.data['snapshots'].append([1,999,'2026-09-13','2026-09-13','1','USD',1,1,1,'[]'])
        with self.assertRaises(ValueError):
            with PrimaryStore(repo).connect():pass
    def test_read_and_runtime_counters_do_not_write_business_sheet(self):
        repo=Repository();store=PrimaryStore(repo)
        with store.connect() as c:
            c.execute('INSERT INTO api_budget VALUES(1,1)')
            c.execute("INSERT INTO meta VALUES('direct_matches_v4','{}')")
        self.assertEqual(repo.writes,0)
        self.assertNotIn('direct_matches_v4',str(repo.data['meta']))
    def test_sorted_sheet_is_equal_and_secret_meta_not_exported(self):
        c=memory_schema();c.execute("INSERT INTO meta VALUES('access_token','secret')")
        self.assertNotIn('secret',str(capture(c)));c.close()
        repo=Repository();data=copy.deepcopy(repo.data)
        for v in data.values():v[1:]=reversed(v[1:])
        self.assertTrue(compare(repo.data,data)['equal'])
    def test_null_marker_cannot_silently_erase_data(self):
        with self.assertRaises(ValueError):decode('releases',[['title','__null_columns'],['real title','[0]']],['title'])
    def test_nested_connection_commits_once(self):
        repo=Repository();store=PrimaryStore(repo)
        with store.connect() as c:
            c.execute("UPDATE releases SET title='outer'")
            with store.connect() as inner:inner.execute("UPDATE releases SET notes='inner'")
        self.assertEqual(repo.writes,1)

    def test_purchase_saved_to_sheet_survives_restart_and_rejects_stale_revision(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import purchase_store
        repo=Repository();store=PrimaryStore(repo)
        with store.connect() as c:
            c.execute("INSERT INTO platform_candidates VALUES(1,'tower','1','q','Album','Artist','CD','','100','JPY','listed','stock','https://tower.jp/item/1','2026-09-13')")
        pick={'key':'source-1','release_id':1,'source_url':'https://tower.jp/item/1','title':'Album','seller':''}
        settings=SimpleNamespace(db_path=None)
        with patch('purchase_store.connect',lambda path:store.connect()):
            purchase_store.save(settings,{'revision':0,'picks':[pick]})
            self.assertEqual(purchase_store.state(settings)['picks'],[pick])
            with self.assertRaises(ValueError):purchase_store.save(settings,{'revision':0,'picks':[]})
        with patch('purchase_store.connect',lambda path:PrimaryStore(repo).connect()):
            self.assertEqual(purchase_store.state(settings)['revision'],1)
        with patch('purchase_store.connect',lambda path:store.connect()):
            purchase_store.save(settings,{'revision':1,'picks':[]})
        self.assertEqual(repo.data['purchase_items'][1:],[])
        self.assertNotIn('purchase_priority_',str(repo.data['meta']))
