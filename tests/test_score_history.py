import tempfile,unittest
from pathlib import Path
from config import Settings
from db import init,connect
import analyze,demo

class ScoreHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Settings(db_path=Path(self.tmp.name)/'qa.db');init(self.s.db_path);demo.seed(self.s)
    def tearDown(self):self.tmp.cleanup()
    def counts(self):
        with connect(self.s.db_path) as c:return dict(c.execute('SELECT release_id,count(*) FROM scores GROUP BY release_id').fetchall())
    def test_each_release_keeps_only_its_newest_scores(self):
        for _ in range(analyze.SCORE_HISTORY+5):result=analyze.run(self.s)
        counts=self.counts()
        self.assertTrue(counts);self.assertEqual(set(counts.values()),{analyze.SCORE_HISTORY})
        self.assertEqual(result['scores_pruned'],len(counts))
        with connect(self.s.db_path) as c:
            for rid in counts:
                kept=[r[0] for r in c.execute('SELECT id FROM scores WHERE release_id=? ORDER BY id',(rid,))]
                newest=c.execute('SELECT max(id) FROM scores WHERE release_id=?',(rid,)).fetchone()[0]
                self.assertEqual(kept[-1],newest);self.assertEqual(len(kept),analyze.SCORE_HISTORY)
    def test_short_histories_are_untouched(self):
        for _ in range(3):result=analyze.run(self.s)
        self.assertEqual(set(self.counts().values()),{3});self.assertEqual(result['scores_pruned'],0)
    def test_latest_score_seen_by_the_dashboard_is_unchanged_by_pruning(self):
        from server import Dashboard
        for _ in range(analyze.SCORE_HISTORY):analyze.run(self.s)
        before={r['release_id']:r['analysis'] for r in Dashboard(self.s).state()['records']}
        analyze.run(self.s)
        after={r['release_id']:r['analysis'] for r in Dashboard(self.s).state()['records']}
        self.assertEqual(before,after)
