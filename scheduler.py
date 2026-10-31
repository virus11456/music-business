"""In-process Taipei scheduler, sharing the dashboard's background-job lock."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import threading
from db import connect
import pipeline
import source_queue
import json
import time

TZ=ZoneInfo('Asia/Taipei')
HOURS=(10,16,22)
# 03:00 is the quiet slot for the Discogs demand scan and the scarcity-list platform search.
NIGHT=3
SLOTS=(NIGHT,)+HOURS
# Reverse matches per day slot; the queue drains three times faster than the earlier 20.
REVERSE_LIMIT=60
GRACE=timedelta(minutes=15)

def night(settings):
    """Discover scarce releases on Discogs, then search platforms for the scarcity list. No purchases or listings."""
    import ingest, demand_queue, analyze, sheet_sync
    result={'flow':'demand_night','failed':0,'errors':[]}
    timings={};mark=time.perf_counter()
    def lap(name):
        nonlocal mark
        t=time.perf_counter();timings[name]=round(t-mark,1);mark=t
    result['scan']=ingest.scan(settings,pages=40,budget=settings.scan_budget,max_new=settings.scan_max_new)
    result['failed']+=result['scan']['failed'];lap('scan')
    result['demand']=demand_queue.run(settings)
    result['failed']+=result['demand']['failed'];lap('demand')
    result['scores_pruned']=(analyze.run(settings) or {}).get('scores_pruned',0);lap('analyze')
    try:result['sheet_sync']=sheet_sync.sync(settings)
    except Exception as exc:
        result['errors'].append(__import__('sync_failure').report(exc));result['failed']+=1
    lap('sheet_sync')
    result['timings']=timings
    return result

class Scheduler:
    def __init__(self,dashboard):
        self.app=dashboard
        self.stop_event=threading.Event()
        self.thread=None

    def state(self,instant=None):
        local=(instant or datetime.now(TZ)).astimezone(TZ)
        upcoming=[local.replace(hour=h,minute=0,second=0,microsecond=0)+timedelta(days=d) for d in (0,1) for h in SLOTS]
        with connect(self.app.settings.db_path) as c:
            last=c.execute("SELECT key,value FROM meta WHERE key LIKE 'schedule_slot:%' ORDER BY key DESC LIMIT 1").fetchone()
        return {'last_run':{'at':last['key'].removeprefix('schedule_slot:'),'status':last['value']} if last else None,'enabled':bool(self.thread and self.thread.is_alive()),'timezone':'Asia/Taipei','times':[f'{h:02d}:00' for h in SLOTS],'next_run':min(t for t in upcoming if t>local).isoformat()}

    def tick(self,instant=None):
        local=(instant or datetime.now(TZ)).astimezone(TZ)
        due=[local.replace(hour=h,minute=0,second=0,microsecond=0) for h in SLOTS]
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
            try:
                if max(due).hour==NIGHT:
                    result=night(self.app.settings)
                    report['batches'].append(result);report['failed']+=result['failed']
                    with connect(self.app.settings.db_path) as c:
                        c.execute('UPDATE meta SET value=? WHERE key=?',('partial' if report['failed'] else 'complete',slot))
                    return report
                source_queue.init(self.app.settings)
                with connect(self.app.settings.db_path) as c:
                    topic=c.execute('SELECT * FROM source_topics ORDER BY collected_at LIMIT 1').fetchone()
                pending=source_queue.pending_count(self.app.settings)
                collect=topic is not None and pending<=20
                report['collection_paused']=bool(topic) and not collect
                report['pending_before']=pending
                result=source_queue.run(self.app.settings,topic['query'] if collect else None,json.loads(topic['platforms']) if collect else None,REVERSE_LIMIT)
                report['batches'].append(result);report['failed']+=result['failed']
            except Exception:
                with connect(self.app.settings.db_path) as c:c.execute('UPDATE meta SET value=? WHERE key=?',('failed',slot))
                raise
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
