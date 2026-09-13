"""Purchase intentions in the active primary store. No purchases or listings."""
import json
from db import connect, now
from refresh_priority import key as priority_key
SCHEMA='''CREATE TABLE IF NOT EXISTS purchase_items (
 key TEXT PRIMARY KEY,release_id INTEGER NOT NULL,source_url TEXT UNIQUE NOT NULL,
 title TEXT NOT NULL,seller TEXT NOT NULL DEFAULT '');'''


def state(settings):
    with connect(settings.db_path) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='purchase_items'").fetchone():return None
        revision=c.execute("SELECT value FROM meta WHERE key='purchase_revision'").fetchone()
        return {'revision':int(revision[0]) if revision else 0,
                'picks':[dict(r) for r in c.execute('SELECT * FROM purchase_items ORDER BY key')]}


def save(settings,data):
    picks,revision=data.get('picks'),data.get('revision')
    if type(revision) is not int or revision<0 or not isinstance(picks,list) or len(picks)>200:
        raise ValueError('清單版本無效或超過 200 件')
    clean=[];urls=set();keys=set()
    for p in picks:
        if not isinstance(p,dict) or type(p.get('release_id')) is not int or not 0<p['release_id']<2**53:
            raise ValueError('版本無效')
        for name,limit in [('key',1500),('source_url',1500),('title',500),('seller',100)]:
            if not isinstance(p.get(name),str) or len(p[name])>limit:raise ValueError('欄位無效')
        if not p['key'] or p['source_url'] in urls or p['key'] in keys:raise ValueError('同一貨源只能選一個版本')
        keys.add(p['key']);urls.add(p['source_url']);clean.append(p)
    with connect(settings.db_path) as c:
        current=c.execute("SELECT value FROM meta WHERE key='purchase_revision'").fetchone()
        if revision!=(int(current[0]) if current else 0):raise ValueError('另一裝置已修改清單，請重新整理後重試')
        previous={r['source_url']:dict(r) for r in c.execute('SELECT * FROM purchase_items')}
        for p in clean:
            if not c.execute('SELECT 1 FROM releases WHERE release_id=?',(p['release_id'],)).fetchone() and p['source_url'] not in previous:
                raise ValueError('版本尚未有已存行情')
            if not c.execute('SELECT 1 FROM platform_candidates WHERE source_url=?',(p['source_url'],)).fetchone() and p['source_url'] not in previous:
                raise ValueError('找不到已存貨源')
        c.execute('DELETE FROM purchase_items')
        c.executemany('INSERT INTO purchase_items VALUES(?,?,?,?,?)',[(p['key'],p['release_id'],p['source_url'],p['title'],p['seller']) for p in clean])
        c.execute("INSERT OR REPLACE INTO meta VALUES('purchase_revision',?)",(str(revision+1),))
        for url in set(previous)-urls:c.execute('DELETE FROM meta WHERE key=?',(priority_key(url),))
        for url in urls:c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(priority_key(url),json.dumps({'source_url':url,'saved_at':now()})))
    return {'message':'採購清單已寫入 Google Sheet，所有裝置共用'}
