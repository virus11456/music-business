import tempfile,unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from config import Settings
from db import init,connect
from scheduler import Scheduler,TZ
import platforms,source_queue

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.settings=Settings(db_path=Path(self.temp.name)/'test.db');init(self.settings.db_path)
        platforms.init(self.settings);source_queue.init(self.settings)
        class App:
            def __init__(self,s):self.settings=s;self.busy=False;self.calls=[]
            def start(self,name,op):
                if self.busy:raise ValueError('busy')
                self.calls.append(op())
        self.app=App(self.settings);self.scheduler=Scheduler(self.app)
        with connect(self.settings.db_path) as c:c.execute("INSERT INTO releases(release_id,title,added_at) VALUES(1,'test','2026-09-10')")
    def tearDown(self):self.temp.cleanup()
    def test_three_slots_and_persistent_dedup(self):
        with patch('scheduler.source_queue.run',return_value={'failed':0}) as run:
            for hour in (10,16,22):
                instant=datetime(2026,9,10,hour,0,tzinfo=TZ)
                self.assertTrue(self.scheduler.tick(instant))
                self.assertFalse(Scheduler(self.app).tick(instant))
            self.assertEqual(run.call_count,3)
    def test_busy_retries_and_no_stale_catchup(self):
        self.app.busy=True;instant=datetime(2026,9,10,10,0,tzinfo=TZ)
        self.assertFalse(self.scheduler.tick(instant))
        self.app.busy=False
        with patch('scheduler.source_queue.run',return_value={'failed':1}):self.assertTrue(self.scheduler.tick(instant))
        self.assertEqual(self.app.calls[0]['failed'],1)
        self.assertFalse(self.scheduler.tick(datetime(2026,9,10,16,15,tzinfo=TZ)))
    def test_next_day_and_timezone(self):
        state=self.scheduler.state(datetime(2026,9,10,23,0,tzinfo=TZ))
        self.assertEqual(state['next_run'],'2026-09-11T03:00:00+08:00')
        self.assertEqual(state['times'],['03:00','10:00','16:00','22:00'])
    def test_backlog_pauses_collection_but_keeps_matching(self):
        with connect(self.settings.db_path) as c:
            c.execute('INSERT INTO source_topics VALUES(?,?,?)',('Beatles','["tower"]','2026-09-10'))
        with patch('scheduler.source_queue.pending_count',return_value=21),patch('scheduler.source_queue.run',return_value={'failed':0}) as run:
            self.scheduler.tick(datetime(2026,9,10,10,0,tzinfo=TZ))
            self.assertEqual(run.call_args.args,(self.settings,None,None,60))
            self.assertTrue(self.app.calls[-1]['collection_paused'])
        with patch('scheduler.source_queue.pending_count',return_value=20),patch('scheduler.source_queue.run',return_value={'failed':0}) as run:
            self.scheduler.tick(datetime(2026,9,10,16,0,tzinfo=TZ))
            self.assertEqual(run.call_args.args,(self.settings,'Beatles',['tower'],60))
    def test_night_slot_runs_scan_and_demand_search_not_the_reverse_queue(self):
        night={'flow':'demand_night','failed':0,'errors':[]}
        with patch('scheduler.night',return_value=night) as run_night,patch('scheduler.source_queue.run') as reverse:
            self.assertTrue(self.scheduler.tick(datetime(2026,9,10,3,5,tzinfo=TZ)))
        run_night.assert_called_once_with(self.settings);reverse.assert_not_called()
        self.assertEqual(self.app.calls[-1]['batches'],[night])
        self.assertEqual(self.scheduler.state(datetime(2026,9,10,3,30,tzinfo=TZ))['last_run'],{'at':'2026-09-10T03:00:00+08:00','status':'complete'})
        self.assertFalse(self.scheduler.tick(datetime(2026,9,10,3,10,tzinfo=TZ)))
    def test_demo_does_not_run(self):
        with connect(self.settings.db_path) as c:c.execute("INSERT INTO meta VALUES('mode','demo')")
        self.assertFalse(self.scheduler.tick(datetime(2026,9,10,10,0,tzinfo=TZ)))
    def test_failure_is_recorded_and_not_falsely_running(self):
        instant=datetime(2026,9,10,10,0,tzinfo=TZ)
        with patch('scheduler.source_queue.run',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):self.scheduler.tick(instant)
        self.assertEqual(self.scheduler.state(instant)['last_run']['status'],'failed')
        self.assertFalse(self.scheduler.tick(instant))
    def test_last_completed_slot_survives_restart(self):
        instant=datetime(2026,9,10,10,0,tzinfo=TZ)
        with patch('scheduler.source_queue.run',return_value={'failed':0}):self.scheduler.tick(instant)
        self.assertEqual(Scheduler(self.app).state(instant)['last_run'],{'at':instant.isoformat(),'status':'complete'})
