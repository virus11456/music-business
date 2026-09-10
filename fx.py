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
