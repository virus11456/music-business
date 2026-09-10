"""Explicit opt-in delivery. Unknown transport outcome is never retried blindly."""
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from db import connect, now, latest_decision
from analyze import evaluate, message

def telegram(settings, text, transport=urlopen):
    request = Request('https://api.telegram.org/bot'+settings.telegram_token+'/sendMessage',
        data=json.dumps({'chat_id':settings.telegram_chat,'text':text}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    try:
        with transport(request,timeout=30) as response:
            data = json.load(response)
            if data.get('ok') is True:
                return 'sent',None
            return 'pending','Telegram 未接受訊息'
    except HTTPError as exc:
        code = exc.code
        exc.close()
        return ('pending' if 400<=code<500 else 'uncertain'),f'Telegram HTTP {code}'
    except (URLError,TimeoutError,OSError,ValueError):
        return 'uncertain','送出結果不明，請人工核對 Telegram 後再處理'

def deliver(settings, urgent_only=False, send=False, sender=telegram):
    if send and (not settings.telegram_token or not settings.telegram_chat):
        raise ValueError('尚未設定 Telegram bot 與接收對象')
    if send:
        with connect(settings.db_path) as c:
            demo = c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if demo and demo[0]=='demo':
                raise ValueError('示範資料庫禁止送出真實通知')
    with connect(settings.db_path) as c:
        # A process crash after sending may have delivered the message already.
        cutoff = (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
        c.execute("UPDATE outbox SET status='uncertain',error='執行中斷，需人工核對',updated_at=? WHERE status='sending' AND updated_at<?",(now(),cutoff))
        rows = c.execute("SELECT * FROM outbox WHERE status='pending' AND (?=0 OR urgent=1) ORDER BY score DESC",(int(urgent_only),)).fetchall()
    results = []
    for row in rows:
        with connect(settings.db_path) as c:
            c.execute('BEGIN IMMEDIATE')
            decision = latest_decision(c,row['release_id'])
            s = c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(row['release_id'],)).fetchone()
            assessment = evaluate(c,s,settings) if s else None
            skip = decision and (decision['decision'] in ('want','watch') or
                   (datetime.now(timezone.utc)-datetime.fromisoformat(decision['decided_at'])).days<settings.skip_days)
            if skip or not assessment or assessment['stale'] or not assessment['rules'] or assessment['score']<settings.min_score:
                c.execute("UPDATE outbox SET status='cancelled',updated_at=? WHERE id=? AND status='pending'",(now(),row['id']))
                continue
            # Only send the frozen analysis if it still describes this snapshot and inputs.
            release = c.execute('SELECT * FROM releases WHERE release_id=?',(row['release_id'],)).fetchone()
            if s['id']!=row['snapshot_id'] or message(release,s,assessment)!=row['message']:
                c.execute("UPDATE outbox SET status='cancelled',updated_at=? WHERE id=? AND status='pending'",(now(),row['id']))
                continue
            if not send:
                results.append({'id':row['id'],'status':'preview','message':row['message']})
                continue
            claimed = c.execute("UPDATE outbox SET status='sending',updated_at=? WHERE id=? AND status='pending'",(now(),row['id'])).rowcount
        if not claimed:
            continue
        status,error = sender(settings,row['message'])
        with connect(settings.db_path) as c:
            c.execute('UPDATE outbox SET status=?,error=?,updated_at=? WHERE id=?',(status,error,now(),row['id']))
            if status=='sent':
                c.execute('INSERT INTO alerts_sent(release_id,rules,sent_at,score,price,currency,outbox_id) VALUES(?,?,?,?,?,?,?)',
                    (row['release_id'],row['rules'],now(),row['score'],row['price'],row['currency'],row['id']))
        results.append({'id':row['id'],'status':status,'error':error})
        if status != 'sent':
            break
    return results
