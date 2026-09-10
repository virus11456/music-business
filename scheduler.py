"""In-process Taipei scheduler, sharing the dashboard's background-job lock."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import threading
from db import connect
import pipeline

TZ=ZoneInfo('Asia/Taipei')
HOURS=(10,16,22)
GRACE=timedelta(minutes=15)

class Scheduler:
    def __init__(self,dashboard):
        self.app=dashboard
        self.stop_event=threading.Event()
        self.thread=None

    def state(self,instant=None):
        local=(instant or datetime.now(TZ)).astimezone(TZ)
        upcoming=[local.replace(hour=h,minute=0,second=0,microsecond=0)+timedelta(days=d) for d in (0,1) for h in HOURS]
        return {'enabled':bool(self.thread and self.thread.is_alive()),'timezone':'Asia/Taipei','times':['10:00','16:00','22:00'],'next_run':min(t for t in upcoming if t>local).isoformat()}

    def tick(self,instant=None):
        local=(instant or datetime.now(TZ)).astimezone(TZ)
        due=[local.replace(hour=h,minute=0,second=0,microsecond=0) for h in HOURS]
        due=[t for t in due if timedelta(0)<=local-t<GRACE]
        if not due:return False
        slot='schedule_slot:'+max(due).isoformat()
        with connect(self.app.settings.db_path) as c:
            mode=c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if mode and mode[0]=='demo':return False
            if c.execute('SELECT 1 FROM meta WHERE key=?',(slot,)).fetchone():return False
        def operation():
            with connect(self.app.settings.db_path) as c:
                if not c.execute('INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)',(slot,'started')).rowcount:return {}
                ids=[r[0] for r in c.execute('SELECT release_id FROM releases ORDER BY release_id')]
            report={'scheduled_slot':slot,'versions':len(ids),'failed':0,'batches':[]}
            for offset in range(0,len(ids),20):
                result=pipeline.run(self.app.settings,ids[offset:offset+20],['yahoo_tw','yahoo_jp','ruten','tower'])
                report['batches'].append(result);report['failed']+=result['failed']
            with connect(self.app.settings.db_path) as c:
                c.execute('UPDATE meta SET value=? WHERE key=?',('partial' if report['failed'] else 'complete',slot))
            return report
        try:self.app.start('定時更新：'+max(due).strftime('%m/%d %H:%M'),operation)
        except ValueError:return False  # Busy: next poll retries within the grace window.
        return True

    def start(self):
        def loop():
            while not self.stop_event.is_set():
                try:self.tick()
                except Exception:
                    # Keep future slots alive; do not log credentials or remote payloads.
                    import logging
                    logging.getLogger(__name__).error('Scheduled update check failed')
                self.stop_event.wait(20)
        self.thread=threading.Thread(target=loop,name='record-scheduler',daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
