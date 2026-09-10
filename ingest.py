import json
from db import connect, snapshot, now
from discogs_client import DiscogsClient, parse_release, parse_stats, APIError

def save_release(c, r, theme=None):
    c.execute('''INSERT INTO releases(release_id,title,artist,year,country,format,catno,source_theme,added_at)
      VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(release_id) DO UPDATE SET title=excluded.title,
      artist=excluded.artist,year=excluded.year,country=excluded.country,format=excluded.format,catno=excluded.catno''',
      (r['release_id'],r['title'],r['artist'],r['year'],r['country'],r['format'],r['catno'],theme,now()))

def fetch_one(client, settings, rid, theme=None):
    r = parse_release(client.get(f'/releases/{rid}'),rid)
    price,currency,supply = parse_stats(client.get(f'/marketplace/stats/{rid}',{'curr_abbr':settings.currency}))
    with connect(settings.db_path) as c:
        save_release(c,r,theme)
        snapshot(c,rid,now(),price,currency,supply,r['have'],r['want'])

def run(settings, client=None):
    client = client or DiscogsClient(settings)
    with connect(settings.db_path) as c:
        ids = [r[0] for r in c.execute('SELECT release_id FROM releases')]
    failures = []
    for rid in ids:
        try:
            fetch_one(client,settings,rid)
        except (APIError,ValueError,TypeError,KeyError) as exc:
            failures.append({'release_id':rid,'error':type(exc).__name__})
    return {'success':len(ids)-len(failures),'failed':len(failures),'failures':failures}

def scan(settings, pages=2, client=None):
    client = client or DiscogsClient(settings)
    with connect(settings.db_path) as c:
        targets = c.execute('SELECT * FROM scan_targets WHERE enabled=1').fetchall()
    found = failed = 0
    for target in targets:
        try:
            page = target['next_page']
            for _ in range(pages):
                params = json.loads(target['query_params'])
                params.update(type='release',page=page,per_page=50)
                result = client.get('/database/search',params)
                if not isinstance(result.get('results'),list) or not isinstance(result.get('pagination'),dict):
                    raise APIError('search 回傳格式不符')
                total_pages = result['pagination'].get('pages')
                if not isinstance(total_pages,int) or total_pages < 0:
                    raise APIError('pagination.pages 格式不符')
                for item in result['results']:
                    rid = item.get('id')
                    if item.get('type') != 'release' or not isinstance(rid,int) or rid<=0:
                        continue
                    with connect(settings.db_path) as c:
                        known = c.execute('SELECT 1 FROM releases WHERE release_id=?',(rid,)).fetchone()
                    if known:
                        continue
                    try:
                        r = parse_release(client.get(f'/releases/{rid}'),rid)
                        if r['have'] is None or r['want'] is None or r['want']/max(r['have'],1)<target['min_want_have']:
                            continue
                        with connect(settings.db_path) as c:
                            save_release(c,r,target['name'])
                        found += 1
                    except (APIError,ValueError,TypeError,KeyError):
                        failed += 1
                page = 1 if page>=total_pages else page+1
                with connect(settings.db_path) as c:
                    c.execute('UPDATE scan_targets SET next_page=?,last_run_at=? WHERE id=?',(page,now(),target['id']))
                if page == 1:
                    break
        except (APIError,ValueError,TypeError,KeyError):
            failed += 1
    return {'discovered':found,'failed':failed}
