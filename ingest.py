import json
from db import connect, snapshot, now
from discogs_client import DiscogsClient, parse_release, parse_release_market, parse_stats, APIError

def save_release(c, r, theme=None):
    if 'barcodes' in r:c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(f"release_barcodes_{r['release_id']}",json.dumps(r['barcodes'])))
    if 'labels' in r:c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(f"release_labels_{r['release_id']}",r['labels']))
    c.execute('''INSERT INTO releases(release_id,title,artist,year,country,format,catno,source_theme,added_at)
      VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(release_id) DO UPDATE SET title=excluded.title,
      artist=excluded.artist,year=excluded.year,country=excluded.country,format=excluded.format,catno=excluded.catno''',
      (r['release_id'],r['title'],r['artist'],r['year'],r['country'],r['format'],r['catno'],theme,now()))

def fetch_one(client, settings, rid, theme=None):
    data = client.get(f'/releases/{rid}')
    r = parse_release(data,rid)
    # One request per release instead of two: Discogs allows 60 a minute and market refresh is a scheduled-job bottleneck.
    market = parse_release_market(data,settings.currency)
    price,currency,supply = market or parse_stats(client.get(f'/marketplace/stats/{rid}',{'curr_abbr':settings.currency}))
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

def scan(settings, pages=2, client=None, budget=None, min_want=None, max_new=None):
    """Discover tracked releases from enabled scan targets.

    A search result's own community counts, when present, rule a release out before the per-release call;
    the release response decides admission and also supplies its USD snapshot. `budget` caps Discogs calls and
    `max_new` caps releases added per run, so tracking (and every comparison rebuild) grows in steps."""
    client = client or DiscogsClient(settings)
    min_want = settings.scan_min_want if min_want is None else min_want
    with connect(settings.db_path) as c:
        targets = c.execute('SELECT * FROM scan_targets WHERE enabled=1').fetchall()
    found = failed = requests = prefiltered = 0
    def call(path, params=None):
        nonlocal requests
        requests += 1
        return client.get(path, params)
    # Each enabled target gets an equal share, so the first target cannot use up the whole night.
    share = lambda total: None if total is None else -(-total // max(1,len(targets)))
    target_budget, target_new = share(budget), share(max_new)
    used = {'requests':0,'found':0}
    spent = lambda: ((budget is not None and requests >= budget) or (max_new is not None and found >= max_new)
                     or (target_budget is not None and requests-used['requests'] >= target_budget)
                     or (target_new is not None and found-used['found'] >= target_new))
    def wanted(want, have, ratio):
        return want >= min_want and want/max(have,1) >= ratio
    for target in targets:
        used.update(requests=requests,found=found)
        if spent():
            break
        try:
            page = target['next_page']
            for _ in range(pages):
                if spent():
                    break
                params = json.loads(target['query_params'])
                params.update(type='release',page=page,per_page=50)
                result = call('/database/search',params)
                if not isinstance(result.get('results'),list) or not isinstance(result.get('pagination'),dict):
                    raise APIError('search 回傳格式不符')
                total_pages = result['pagination'].get('pages')
                if not isinstance(total_pages,int) or total_pages < 0:
                    raise APIError('pagination.pages 格式不符')
                finished = True
                for item in result['results']:
                    rid = item.get('id')
                    if item.get('type') != 'release' or not isinstance(rid,int) or rid<=0:
                        continue
                    with connect(settings.db_path) as c:
                        known = c.execute('SELECT 1 FROM releases WHERE release_id=?',(rid,)).fetchone()
                    if known:
                        continue
                    hint = item.get('community') if isinstance(item.get('community'),dict) else {}
                    want, have = hint.get('want'), hint.get('have')
                    if all(isinstance(v,int) and not isinstance(v,bool) and v>=0 for v in (want,have)) and not wanted(want,have,target['min_want_have']):
                        prefiltered += 1
                        continue
                    if spent():
                        finished = False  # Same page again next time; already saved releases are skipped.
                        break
                    try:
                        data = call(f'/releases/{rid}')
                        r = parse_release(data,rid)
                        if r['have'] is None or r['want'] is None or not wanted(r['want'],r['have'],target['min_want_have']):
                            continue
                        market = parse_release_market(data,settings.currency)
                        with connect(settings.db_path) as c:
                            save_release(c,r,target['name'])
                            if market:
                                snapshot(c,rid,now(),*market,r['have'],r['want'])
                        found += 1
                    except (APIError,ValueError,TypeError,KeyError):
                        failed += 1
                if not finished:
                    break
                page = 1 if page>=total_pages else page+1
                with connect(settings.db_path) as c:
                    c.execute('UPDATE scan_targets SET next_page=?,last_run_at=? WHERE id=?',(page,now(),target['id']))
                if page == 1:
                    break
        except (APIError,ValueError,TypeError,KeyError):
            failed += 1
    exhausted = (budget is not None and requests >= budget) or (max_new is not None and found >= max_new)
    return {'discovered':found,'failed':failed,'requests':requests,'prefiltered':prefiltered,'budget_exhausted':exhausted}
