from datetime import datetime, timedelta, timezone
from db import connect, snapshot, now
from ingest import save_release

def seed(settings):
    with connect(settings.db_path) as c:
        if c.execute('SELECT count(*) FROM releases').fetchone()[0]:
            raise ValueError('示範資料只能寫入空白資料庫，避免混入真實行情')
        c.execute("INSERT OR REPLACE INTO meta VALUES('mode','demo')")
        today = datetime.now(timezone.utc)
        for currency,rate in [('USD','32'),('JPY','.22')]:
            c.execute('INSERT INTO fx_rates VALUES(?,?,?,?)',(currency,today.date().isoformat(),rate,'DEMO：虛構匯率'))
        examples = [
            (900000001,'Demo Artist A','Japan pressing / 有成本',100,75,2,100,480,'JPY','4500'),
            (900000002,'Demo Artist B','Japan pressing / 待詢價',90,85,3,100,360,None,None),
            (900000003,'Demo Artist C','Japan pressing / 利潤不足',35,35,20,400,250,'JPY','4000'),
            (900000004,'Demo Artist D','Japan pressing / 無在售',None,None,0,100,900,None,None)]
        for rid,artist,title,old,price,supply,have,want,cc,amount in examples:
            save_release(c,dict(release_id=rid,title=title,artist=artist,year=1980,country='Japan',format='Vinyl',catno='DEMO-'+str(rid)),'demo')
            snapshot(c,rid,(today-timedelta(days=7)).isoformat(),old,'USD' if old else None,supply,have,want)
            snapshot(c,rid,today.isoformat(),price,'USD' if price else None,supply,have,want)
            if amount:
                c.execute('INSERT INTO costs(release_id,source,cost_amount,cost_currency,recorded_at) VALUES(?,?,?,?,?)',
                          (rid,'示範貨源；含進貨端運費',amount,cc,now()))
