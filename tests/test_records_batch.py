"""Records are read with one query per table and no per-release history; same values as the per-release queries."""
import json,tempfile,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from config import Settings
from db import init,connect,now,snapshot,decide
import demo,analyze

def reference(c,rid):
    snap=c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(rid,)).fetchone()
    score=c.execute('SELECT * FROM scores WHERE release_id=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()
    cost=c.execute('SELECT * FROM costs WHERE release_id=? ORDER BY recorded_at DESC,id DESC LIMIT 1',(rid,)).fetchone()
    decision=c.execute('SELECT * FROM decisions WHERE release_id=? ORDER BY id DESC LIMIT 1',(rid,)).fetchone()
    return {'snapshot':dict(snap) if snap else None,'analysis':json.loads(score['components']) if score else None,
            'scored_at':score['scored_at'] if score else None,'cost':dict(cost) if cost else None,'decision':dict(decision) if decision else None}

class RecordsBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'t.db',token='t');init(self.s.db_path);demo.seed(self.s)
        with connect(self.s.db_path) as c:
            rid=900000001
            for day in ('2026-10-01T03:00:00+00:00','2026-10-02T03:00:00+00:00'):snapshot(c,rid,day,'20','USD',2,10,30)
            c.execute("INSERT INTO costs(release_id,source,cost_amount,cost_currency,grading,recorded_at) VALUES(?,?,?,?,?,?)",(rid,'a','100','TWD','',now()))
            c.execute("INSERT INTO costs(release_id,source,cost_amount,cost_currency,grading,recorded_at) VALUES(?,?,?,?,?,?)",(rid,'b','120','TWD','',now()))
            decide(c,rid,'watch','10','USD');decide(c,rid,'want')
        analyze.run(self.s);analyze.run(self.s)
        from server import Dashboard
        self.app=Dashboard(self.s)
    def tearDown(self):self.tmp.cleanup()
    def test_batch_equals_per_release_queries_and_drops_history(self):
        records=self.app.state()['records']
        self.assertTrue(records)
        with connect(self.s.db_path) as c:
            for r in records:
                self.assertNotIn('history',r)
                self.assertEqual({k:r[k] for k in ('snapshot','analysis','scored_at','cost','decision')},reference(c,r['release_id']),r['release_id'])
        r=next(r for r in records if r['release_id']==900000001)
        self.assertEqual((r['cost']['source'],r['decision']['decision']),('b','want'))
    def test_history_is_served_on_demand_oldest_first(self):
        history=self.app.history(900000001)
        self.assertLessEqual(len(history),30);self.assertTrue(history)
        self.assertEqual([h['captured_at'] for h in history],sorted(h['captured_at'] for h in history))
        self.assertEqual(set(history[0]),{'captured_at','lowest_price','currency'})

if __name__=='__main__':unittest.main()
