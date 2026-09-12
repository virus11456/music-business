"""One local price-reached record per watch decision; never sends messages."""
import json
from datetime import datetime,timezone
from config import money
from db import latest_decision,now
from fx import convert,business_day

PREFIX='watch_hit:'
def record(c,release,snapshot,settings,at=None):
    at=at or datetime.now(timezone.utc)
    decision=latest_decision(c,release['release_id'])
    if not decision or decision['decision']!='watch':return False
    captured=datetime.fromisoformat(snapshot['captured_at'])
    if captured>at or (at-captured).total_seconds()>settings.snapshot_max_age_days*86400:return False
    if captured<datetime.fromisoformat(decision['decided_at']):return False
    if not snapshot['num_for_sale'] or not snapshot['lowest_price'] or not snapshot['currency']:return False
    price=money(snapshot['lowest_price']);target=money(decision['target_price'])
    if price<=0 or target<=0:return False
    evidence=[]
    if snapshot['currency']==decision['target_currency']:sale,limit=price,target
    else:
        try:
            sale,a=convert(c,price,snapshot['currency'],business_day(at),settings.fx_max_age_days)
            limit,b=convert(c,target,decision['target_currency'],business_day(at),settings.fx_max_age_days)
            evidence=[a,b]
        except ValueError:return False
    if sale>limit:return False
    data={'decision_id':decision['id'],'release_id':release['release_id'],'artist':release['artist'],'title':release['title'],
          'price':str(price),'currency':snapshot['currency'],'target':str(target),'target_currency':decision['target_currency'],
          'captured_at':snapshot['captured_at'],'recorded_at':now(),'fx':evidence}
    return bool(c.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',(PREFIX+str(decision['id']),json.dumps(data,ensure_ascii=False))).rowcount)

def rows(c):
    return [json.loads(r[0]) for r in c.execute("SELECT value FROM meta WHERE key LIKE 'watch_hit:%' ORDER BY CAST(substr(key,11) AS INTEGER) DESC LIMIT 100")]
