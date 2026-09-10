from datetime import date,datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from config import money

def business_day(instant=None):
    return (instant or datetime.now(ZoneInfo('Asia/Taipei'))).astimezone(ZoneInfo('Asia/Taipei')).date().isoformat()

def convert(c, amount, currency, as_of, max_age=7):
    if currency == 'TWD':
        return money(amount), {'currency':'TWD','rate':'1','date':as_of,'source':'identity'}
    row = c.execute('SELECT * FROM fx_rates WHERE currency=? AND rate_date<=? ORDER BY rate_date DESC LIMIT 1',
                    (currency,as_of)).fetchone()
    if not row or (date.fromisoformat(as_of)-date.fromisoformat(row['rate_date'])).days > max_age:
        raise ValueError('缺少有效匯率：'+str(currency))
    return money(amount)*Decimal(row['twd_per_unit']), dict(row)

def refresh_reference(settings,fetcher=None):
    """Daily reference FX for estimates; preserve same-day manually entered rates."""
    import json
    from urllib.request import urlopen
    from db import connect
    day=business_day()
    import time
    with connect(settings.db_path) as c:
        next_refresh=c.execute("SELECT value FROM meta WHERE key='reference_fx_refresh_after'").fetchone()
        if next_refresh and float(next_refresh[0])>time.time():
            try:
                for cc in ('USD','JPY','EUR','GBP'):convert(c,1,cc,day)
                return {'cached':True}
            except ValueError:pass
        if c.execute("SELECT count(*) FROM fx_rates WHERE rate_date=? AND currency IN ('USD','JPY','EUR','GBP')",(day,)).fetchone()[0]==4:
            return {'cached':True}
    url='https://open.er-api.com/v6/latest/USD'
    if fetcher:data=fetcher(url)
    else:
        with urlopen(url,timeout=25) as response:data=json.load(response)
    if data.get('result')!='success' or data.get('base_code')!='USD':raise ValueError('匯率來源格式不符')
    rate_day=business_day(datetime.fromtimestamp(data['time_last_update_unix'],ZoneInfo('UTC')))
    if not 0<=(date.fromisoformat(day)-date.fromisoformat(rate_day)).days<=7:raise ValueError('匯率日期無效')
    rates={cc:money(data['rates'][cc]) for cc in ('USD','JPY','EUR','GBP','TWD')}
    if any(v<=0 for v in rates.values()):raise ValueError('匯率無效')
    with connect(settings.db_path) as c:
        for cc in ('USD','JPY','EUR','GBP'):
            c.execute('INSERT OR IGNORE INTO fx_rates VALUES(?,?,?,?)',(cc,rate_day,str(rates['TWD']/rates[cc]),'ExchangeRate-API 參考匯率 https://www.exchangerate-api.com'))
        next_refresh=max(time.time()+3600,min(float(data.get('time_next_update_unix',0)),time.time()+86400))
        c.execute("INSERT OR REPLACE INTO meta VALUES('reference_fx_refresh_after',?)",(str(next_refresh),))
    return {'date':rate_day,'currencies':4,'cached':False}
