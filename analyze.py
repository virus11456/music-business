"""Transparent heuristics: listing prices and demand counts are not sales forecasts."""
import json
from datetime import datetime, timedelta, timezone
from config import money
from db import connect, now, latest_decision
from fx import convert,business_day

# Only the newest score per release is ever read; keep a short history instead of one row per run forever.
SCORE_HISTORY = 30

def clamp(x):
    return max(0., min(1., x))

def evaluate(c, s, settings, at=None):
    at = at or datetime.now(timezone.utc)
    captured = datetime.fromisoformat(s['captured_at'])
    warnings = ['售價採最低掛牌價；未校正品相，並非成交保證']
    stale = (at-captured).total_seconds() > settings.snapshot_max_age_days*86400 or captured > at
    if stale:
        warnings.append('快照過期或時間異常：停止觸發提醒')
    ratio = None if s['want'] is None or s['have'] is None else s['want']/max(s['have'],1)
    supply = s['num_for_sale']
    liquid = supply is not None and supply >= 1 and ratio is not None and ratio > 1.5
    cost = c.execute('SELECT * FROM costs WHERE release_id=? AND recorded_at<=? ORDER BY recorded_at DESC,id DESC LIMIT 1',
                     (s['release_id'],at.isoformat())).fetchone()
    net = margin = None
    fx_used = []
    if not cost:
        warnings.append('缺少進貨成本：利潤分項暫用中性值，不代表可獲利')
    elif s['lowest_price'] is not None and s['currency']:
        try:
            sale, a = convert(c,s['lowest_price'],s['currency'],business_day(at),settings.fx_max_age_days)
            purchase, b = convert(c,cost['cost_amount'],cost['cost_currency'],business_day(at),settings.fx_max_age_days)
            fx_used = [a,b]
            if sale > 0:
                net = sale-purchase-sale*settings.fee_pct-settings.shipping-settings.packing-settings.reserve
                margin = float(net/sale)
        except ValueError as exc:
            warnings.append(str(exc)+'：不計算淨利')
    drop = None
    cutoff = captured - timedelta(days=7)
    previous = c.execute('''SELECT * FROM snapshots WHERE release_id=? AND currency=? AND captured_at<=?
      AND captured_at>=? AND lowest_price IS NOT NULL ORDER BY captured_at DESC LIMIT 1''',
      (s['release_id'],s['currency'],cutoff.isoformat(),(cutoff-timedelta(days=2)).isoformat())).fetchone()
    if previous and money(previous['lowest_price']) > 0 and s['lowest_price'] is not None:
        drop = float(1-money(s['lowest_price'])/money(previous['lowest_price']))
    else:
        warnings.append('缺少同幣別 7 日基準：價格動能暫用中性值')
    parts = dict(zip(('demand','margin','scarcity','momentum'),(
        clamp((ratio or 0)/5), .5 if margin is None else clamp(margin/.4),
        0 if not supply else 1/(1+(supply-1)/3), .5 if drop is None else clamp(drop/.4))))
    score = round(sum(v*w for v,w in zip(parts.values(),settings.weights))*100,2)
    rules = []
    if not stale and supply is not None and supply >= 1 and s['lowest_price'] is not None and money(s['lowest_price']) > 0:
        if net is not None and net > 0 and margin >= settings.min_margin:
            rules.append('UNDERVALUED')
        if ratio is not None and ratio >= settings.hot_ratio and supply <= settings.max_supply:
            rules.append('HOT_DEMAND')
        if drop is not None and drop >= settings.price_drop:
            rules.append('PRICE_DROP')
    return {'score':score,'parts':parts,'weights':settings.weights,'ratio':ratio,'liquidity':liquid,
            'net_twd':str(net.quantize(money('.01'))) if net is not None else None,
            'margin':margin,'drop_7d':drop,'rules':rules,'warnings':warnings,'fx':fx_used,
            'assumptions':{'fee_pct':str(settings.fee_pct),'shipping':str(settings.shipping),
                           'packing':str(settings.packing),'reserve':str(settings.reserve)},'stale':stale}

def message(release, s, result):
    return (f"SIMPLES 選品提醒｜{result['score']} 分\n{release['artist']} — {release['title']}\n"
            f"{release['country']} / {release['format']}\n最低掛牌 {s['currency']} {s['lowest_price']}"
            f"｜在售 {s['num_for_sale']}\nWant/Have：{result['ratio']}\n"
            f"估算淨利 TWD：{result['net_twd'] or '待補成本或匯率'}\n"
            f"規則：{', '.join(result['rules'])}\n"
            f"https://www.discogs.com/release/{s['release_id']}\n"
            + '\n'.join(result['warnings']))[:3800]

def run(settings):
    count = queued = watch_hits = 0
    with connect(settings.db_path) as c:
        for r in c.execute('SELECT * FROM releases').fetchall():
            s = c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(r['release_id'],)).fetchone()
            if not s:
                continue
            import watch_alerts
            watch_hits += int(watch_alerts.record(c,r,s,settings))
            result = evaluate(c,s,settings)
            c.execute('INSERT INTO scores(release_id,snapshot_id,scored_at,opportunity_score,components) VALUES(?,?,?,?,?)',
                      (r['release_id'],s['id'],now(),result['score'],json.dumps(result,ensure_ascii=False)))
            count += 1
            if not result['rules'] or result['score'] < settings.min_score:
                continue
            decision = latest_decision(c,r['release_id'])
            if decision:
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(decision['decided_at'])).days
                if decision['decision'] in ('want','watch') or age < settings.skip_days:
                    continue
            last = c.execute('SELECT * FROM alerts_sent WHERE release_id=? ORDER BY id DESC LIMIT 1',(r['release_id'],)).fetchone()
            if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last['sent_at'])).days < settings.cooldown_days:
                significant = (last['currency']==s['currency'] and last['price'] and money(last['price'])>0
                               and money(s['lowest_price']) <= money(last['price'])*money('.85'))
                if not significant:
                    continue
            c.execute("UPDATE outbox SET status='cancelled',updated_at=? WHERE release_id=? AND status='pending'",(now(),r['release_id']))
            rules = json.dumps(sorted(result['rules']))
            existing = c.execute('SELECT status FROM outbox WHERE release_id=? AND snapshot_id=? AND rules=?',
                                 (r['release_id'],s['id'],rules)).fetchone()
            if existing and existing['status'] in ('sent','uncertain','sending'):
                continue
            values = (message(r,s,result),int(result['score']>=settings.urgent_score or 'PRICE_DROP' in result['rules']),
                      result['score'],s['lowest_price'],s['currency'],now(),now(),r['release_id'],s['id'],rules)
            c.execute('''INSERT INTO outbox(message,urgent,score,price,currency,created_at,updated_at,release_id,snapshot_id,rules)
              VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(release_id,snapshot_id,rules) DO UPDATE SET
              message=excluded.message,urgent=excluded.urgent,score=excluded.score,price=excluded.price,
              currency=excluded.currency,status='pending',updated_at=excluded.updated_at''',values)
            queued += 1
        pruned = c.execute('''DELETE FROM scores WHERE id IN (SELECT id FROM (SELECT id,
            ROW_NUMBER() OVER (PARTITION BY release_id ORDER BY id DESC) AS position FROM scores) WHERE position>?)''',
            (SCORE_HISTORY,)).rowcount
    return {'scored':count,'queued':queued,'watch_hits':watch_hits,'scores_pruned':pruned}
