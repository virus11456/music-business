import json
from db import connect, latest_decision

def clean(value):
    return str(value if value is not None else '—').replace('|','／').replace('\n',' ')

def render(settings):
    with connect(settings.db_path) as c:
        demo = c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
        lines = ['# SIMPLES 唱片選品報告','',
          '**示範資料：虛構版本與價格，不能作為進貨依據。**' if demo and demo[0]=='demo' else '本報告採用資料庫內最新評分；請留意快照與評分時間。','',
          '評分是待驗證的排序規則，不是成交機率。要進貨／跳過／觀察只記錄決策。','',
          '| 版本 ID | 歌手／專輯 | 評分 | 最低掛牌 | 估算淨利 TWD | 決策 |',
          '|---|---|---:|---:|---:|---|']
        rows = c.execute('''SELECT r.*,s.components,s.scored_at,s.opportunity_score FROM releases r
          JOIN scores s ON s.id=(SELECT max(id) FROM scores WHERE release_id=r.release_id)
          ORDER BY s.opportunity_score DESC''').fetchall()
        details = []
        for r in rows:
            result = json.loads(r['components'])
            s = c.execute('SELECT * FROM snapshots WHERE release_id=? ORDER BY captured_at DESC LIMIT 1',(r['release_id'],)).fetchone()
            d = latest_decision(c,r['release_id'])
            decision = {'want':'要進貨','skip':'跳過','watch':'觀察'}.get(d['decision'],'待決策') if d else '待決策'
            lines.append('| '+' | '.join(map(clean,(r['release_id'],f"{r['artist']} / {r['title']}",r['opportunity_score'],
                          f"{s['currency']} {s['lowest_price']}",result['net_twd'],decision)))+' |')
            details += [f"### {clean(r['artist'])} — {clean(r['title'])}",'',
                f"快照：{s['captured_at']}；評分：{r['scored_at']}",
                f"命中：{', '.join(result['rules']) or '無'}；Want/Have：{result['ratio']}",
                f"七日跌幅：{round(result['drop_7d']*100,1) if result['drop_7d'] is not None else '資料不足'}%",'',
                *['- '+w for w in result['warnings']], '']
        if not rows:
            lines += ['','尚未有評分資料。請先加入版本、抓取快照並分析。']
        lines += ['', '## 評分依據','',*details,'## 任務紀錄','']
        for r in c.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 8'):
            lines.append(f"- {r['name']}：{r['status']}（{r['started_at']}）")
        lines += ['', '## 尚待完成','',
          '- 真實 Discogs token 的唯讀端點驗證與第一批 20–30 張人工核對。',
          '- Dashboard 總覽／決策收件匣、手機互動與目標價監控。',
          '- 進貨驗品相、上架佇列、批次上架與庫存管理。','']
        return '\n'.join(lines)
