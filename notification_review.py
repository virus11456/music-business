"""Review delivery outcomes without sending or retrying messages."""
from db import connect, now

def state(settings):
    with connect(settings.db_path) as c:
        counts = dict(c.execute('SELECT status,count(*) FROM outbox GROUP BY status').fetchall())
        rows = [dict(r) for r in c.execute('SELECT id,release_id,status,message,updated_at FROM outbox ORDER BY updated_at DESC,id DESC LIMIT 100')]
        import watch_alerts
        hits=watch_alerts.rows(c)
    return {'counts':counts,'rows':rows,'limit':100,'watch_hits':hits}

def resolve(settings, item_id, outcome):
    if type(item_id) is not int or item_id < 1 or outcome not in ('sent','cancelled'):
        raise ValueError('通知核對資料無效')
    with connect(settings.db_path) as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM outbox WHERE id=?',(item_id,)).fetchone()
        if not row or row['status'] != 'uncertain':
            raise ValueError('只能處理結果不明的通知，請重新整理')
        stamp = now()
        if outcome == 'sent':
            c.execute('INSERT OR IGNORE INTO alerts_sent(release_id,rules,sent_at,score,price,currency,outbox_id) VALUES(?,?,?,?,?,?,?)',
                      (row['release_id'],row['rules'],stamp,row['score'],row['price'],row['currency'],item_id))
        c.execute('UPDATE outbox SET status=?,error=?,updated_at=? WHERE id=?',
                  (outcome,'人工核對：已收到' if outcome=='sent' else '人工核對：停止處理，不重送',stamp,item_id))
    return {'saved':True,'message':'核對結果已儲存；沒有送出或重送通知'}
