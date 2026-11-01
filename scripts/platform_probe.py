#!/usr/bin/env python3
"""Live check of each platform's search page and parser with one fixed, well-stocked query.

Read-only: fetches public search pages (and official APIs when their keys are set), parses them, and prints a
JSON report. Nothing is written to any database. Exit code 1 when a parser broke or found nothing; a site that
refuses the connection (HTTP 403 etc.) is reported as blocked without failing the exit code.

  python3 scripts/platform_probe.py            # all platforms
  python3 scripts/platform_probe.py yahoo_jp   # selected platforms
"""
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import api_sources  # noqa: E402
import platforms  # noqa: E402

QUERY = 'Tatsuro Yamashita For You'   # stocked on every platform for years
SCRAPED = ('yahoo_tw', 'yahoo_jp', 'ruten', 'tower')

def probe(platform, settings=None, fetcher=platforms.fetch):
    started = time.monotonic()
    try:
        if platform in api_sources.PLATFORMS:
            if settings is None:
                return {'platform': platform, 'status': 'skipped', 'reason': 'API 金鑰只在伺服器'}
            raw = fetcher(api_sources.request(settings, platform, QUERY, 1))
            rows = api_sources.parse(platform, raw, 1)[0]
        else:
            raw = fetcher(platforms.search_url(platform, QUERY))
            if platform == 'ruten':
                ids = [str(h['Id']) for h in json.loads(raw)['Rows'][:5]]
                time.sleep(3)
                raw = fetcher('https://rtapi.ruten.com.tw/api/prod/v3/index.php/prod?id=' + ','.join(ids)) if ids else '[]'
            rows = platforms.PARSERS[platform](raw)
    except HTTPError as e:
        return {'platform': platform, 'status': 'blocked', 'error': f'HTTP {e.code}', 'seconds': round(time.monotonic() - started, 1)}
    except Exception as e:  # parser or transport: the page changed or could not be read
        return {'platform': platform, 'status': 'broken', 'error': f'{type(e).__name__}: {str(e)[:160]}',
                'seconds': round(time.monotonic() - started, 1)}
    status = 'ok' if rows else 'empty'
    return {'platform': platform, 'status': status, 'items': len(rows), 'sample': rows[0]['title'][:80] if rows else None,
            'seconds': round(time.monotonic() - started, 1)}

def main(argv):
    selected = argv or list(SCRAPED) + list(api_sources.PLATFORMS)
    settings = None
    try:
        from config import Settings, load_env
        load_env()
        candidate = Settings()
        if candidate.rakuten_app_id or candidate.ebay_client_id:
            settings = candidate
    except Exception:
        settings = None  # No server configuration here: API platforms are skipped.
    report = []
    for platform in selected:
        report.append(probe(platform, settings))
        time.sleep(3)
    print(json.dumps({'query': QUERY, 'platforms': report}, ensure_ascii=False, indent=1))
    # Exit 1 only for what code can fix: a parser that breaks, or finds nothing for this well-stocked query.
    # A site refusing the connection (blocked) is reported but needs a person, not a parser change.
    return 1 if any(r['status'] in ('broken', 'empty') for r in report) else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
