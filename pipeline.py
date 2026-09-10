"""One demand-first cycle; no purchase or listing side effects."""
import argparse
import json
import analyze,ingest,sourcing,sheet_sync
from config import load_env,Settings
from discogs_client import DiscogsClient

def run(settings,release_ids,selected,query=None):
    if not release_ids or len(release_ids)>20:raise ValueError('每次請選擇 1 至 20 個版本')
    result={'releases':[],'sheet_sync':None,'errors':[]}
    for rid in dict.fromkeys(release_ids):
        row={'release_id':rid}
        try:ingest.fetch_one(DiscogsClient(settings),settings,rid);row['market']='完成'
        except Exception as exc:row['market']='失敗';result['errors'].append({'release_id':rid,'step':'market','error':type(exc).__name__})
        try:row['sourcing']=sourcing.find(settings,rid,selected,query)
        except Exception as exc:result['errors'].append({'release_id':rid,'step':'sourcing','error':type(exc).__name__})
        result['releases'].append(row)
    analyze.run(settings)
    try:result['sheet_sync']=sheet_sync.sync(settings)
    except Exception as exc:result['errors'].append({'step':'sheets','error':type(exc).__name__})
    result['failed']=len(result['errors'])+sum(r.get('sourcing',{}).get('failed_platforms',0) for r in result['releases'])
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='更新需求行情、找貨、比價並同步 Google Sheets；不刊登')
    parser.add_argument('--release-id',type=int,action='append',required=True)
    parser.add_argument('--platform',action='append',choices=['yahoo_tw','yahoo_jp','ruten','tower'])
    args=parser.parse_args();load_env();s=Settings()
    from server import Dashboard
    Dashboard(s)
    result=run(s,args.release_id,args.platform or ['yahoo_tw','yahoo_jp','ruten','tower'])
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(1 if result['errors'] or any(r.get('sourcing',{}).get('failed_platforms') for r in result['releases']) else 0)
