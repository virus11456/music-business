#!/usr/bin/env python3
from fx import business_day
import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
import analyze
import demo
import ingest
import notify
import probe
import report
from config import Settings, load_env, money
from db import connect, init, now, decide, job
from discogs_client import DiscogsClient, APIError

def positive(value):
    number = int(value)
    if number<=0:
        raise argparse.ArgumentTypeError('必須大於零')
    return number

def parser():
    p = argparse.ArgumentParser(description='SIMPLES 唱片生意：第一階段後端')
    p.add_argument('--db',type=Path,help='資料庫路徑；demo 請使用獨立路徑')
    sub = p.add_subparsers(dest='command',required=True)
    for name in ('init-db','demo','ingest','analyze','health','report','pipeline'):
        sub.add_parser(name)
    for name in ('add-release','probe'):
        sub.add_parser(name).add_argument('release_id',type=positive)
    cost = sub.add_parser('add-cost')
    cost.add_argument('release_id',type=positive)
    cost.add_argument('amount')
    cost.add_argument('currency')
    cost.add_argument('--source',required=True)
    cost.add_argument('--grading',default='')
    fx = sub.add_parser('set-fx')
    fx.add_argument('currency')
    fx.add_argument('twd_per_unit')
    fx.add_argument('--date',default=business_day())
    fx.add_argument('--source',required=True)
    d = sub.add_parser('decide')
    d.add_argument('release_id',type=positive)
    d.add_argument('choice',choices=['want','skip','watch'])
    d.add_argument('--target')
    d.add_argument('--currency')
    target = sub.add_parser('add-target')
    target.add_argument('name')
    target.add_argument('--artist',required=True,help='第一版以英文歌手明確限定候選，避免把日本國別當成英文語言')
    target.add_argument('--country',default='Japan')
    target.add_argument('--format',default='Vinyl')
    target.add_argument('--ratio',type=float,default=1.5)
    scan = sub.add_parser('scan')
    scan.add_argument('--pages',type=positive,default=2)
    digest = sub.add_parser('digest')
    digest.add_argument('--send',action='store_true',help='明確啟用真實 Telegram 發送；預設只預覽')
    digest.add_argument('--urgent-only',action='store_true')
    backup = sub.add_parser('backup')
    backup.add_argument('destination',type=Path)
    return p

def currency(value):
    value=value.upper()
    if len(value)!=3 or not value.isascii() or not value.isalpha():
        raise ValueError('幣別請使用三碼，例如 TWD / USD / JPY')
    return value

def main(argv=None):
    args = parser().parse_args(argv)
    try:
        load_env()
        settings = Settings()
        if args.db:
            settings.db_path = args.db.resolve()
        if args.command=='demo' and not args.db:
            raise ValueError('demo 必須明確指定 --db data/demo.sqlite3')
        init(settings.db_path)
        cmd = args.command
        if cmd in ('probe','add-release','ingest','scan','pipeline'):
            with connect(settings.db_path) as c:
                mode = c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
                if mode and mode[0]=='demo':
                    raise ValueError('示範資料庫不可混入真實資料；請切換 live.sqlite3')
        with job(settings.db_path,cmd) as detail:
            if cmd=='init-db':
                result = {'initialized':str(settings.db_path)}
            elif cmd=='demo':
                demo.seed(settings)
                result=analyze.run(settings)
            elif cmd=='probe':
                result=probe.run(settings,args.release_id)
            elif cmd=='add-release':
                ingest.fetch_one(DiscogsClient(settings),settings,args.release_id)
                result={'added':args.release_id}
            elif cmd=='ingest':
                result=ingest.run(settings)
            elif cmd=='scan':
                result=ingest.scan(settings,args.pages)
            elif cmd=='analyze':
                result=analyze.run(settings)
            elif cmd=='pipeline':
                result=ingest.run(settings)
                result.update(analyze.run(settings))
            elif cmd=='digest':
                result={'deliveries':notify.deliver(settings,args.urgent_only,args.send)}
                result['failed']=sum(x['status'] not in ('sent','preview') for x in result['deliveries'])
            elif cmd=='report':
                print(report.render(settings))
                return 0
            elif cmd=='health':
                with connect(settings.db_path) as c:
                    result={'jobs':[dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 12')],
                            'api':[dict(r) for r in c.execute('SELECT * FROM api_health')],
                            'outbox':[dict(r) for r in c.execute('SELECT status,count(*) AS count FROM outbox GROUP BY status')]}
            elif cmd=='backup':
                dest=args.destination.resolve()
                if dest.exists():
                    raise ValueError('備份目的檔已存在，請使用新檔名')
                dest.parent.mkdir(parents=True,exist_ok=True)
                with connect(settings.db_path) as c, sqlite3.connect(dest) as target:
                    c.backup(target)
                result={'backup':str(dest)}
            else:
                with connect(settings.db_path) as c:
                    if cmd=='add-cost':
                        c.execute('INSERT INTO costs(release_id,source,cost_amount,cost_currency,grading,recorded_at) VALUES(?,?,?,?,?,?)',
                          (args.release_id,args.source,str(money(args.amount)),currency(args.currency),args.grading,now()))
                    elif cmd=='set-fx':
                        date.fromisoformat(args.date)
                        if money(args.twd_per_unit)<=0:
                            raise ValueError('匯率必須大於零')
                        c.execute('INSERT OR REPLACE INTO fx_rates VALUES(?,?,?,?)',
                                  (currency(args.currency),args.date,str(money(args.twd_per_unit)),args.source))
                    elif cmd=='decide':
                        decide(c,args.release_id,args.choice,args.target,currency(args.currency) if args.currency else None)
                    elif cmd=='add-target':
                        if not 0<=args.ratio<=1000000:
                            raise ValueError('需求門檻必須是有效非負值')
                        params={'artist':args.artist,'country':args.country,'format':args.format}
                        c.execute('INSERT INTO scan_targets(name,query_params,min_want_have) VALUES(?,?,?)',
                                  (args.name,json.dumps(params),args.ratio))
                result={'saved':cmd}
                if cmd in ('add-cost','set-fx'):
                    result.update(analyze.run(settings))
            if isinstance(result,dict):
                detail.update(result if cmd not in ('probe','health','digest') else {'completed':True,'failed':result.get('failed',0)})
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 1 if isinstance(result,dict) and result.get('failed') else 0
    except (ValueError,APIError,sqlite3.Error,OSError) as exc:
        # Do not emit HTTP request URLs, headers, or raw third-party payloads.
        print('操作未完成：'+(str(exc) if isinstance(exc,(ValueError,APIError)) else type(exc).__name__),file=sys.stderr)
        return 1

if __name__=='__main__':
    sys.exit(main())
