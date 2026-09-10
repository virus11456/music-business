"""Read-only endpoint probe. Never tests seller permissions by creating a listing."""
import json
from discogs_client import DiscogsClient, parse_release, parse_stats

def shape(value):
    if isinstance(value,dict):
        return {k:shape(v) for k,v in value.items()}
    if isinstance(value,list):
        return [shape(value[0])] if value else []
    return type(value).__name__

def run(settings, rid):
    client = DiscogsClient(settings)
    release = client.get(f'/releases/{rid}')
    stats = client.get(f'/marketplace/stats/{rid}',{'curr_abbr':settings.currency})
    parsed_r = parse_release(release,rid)
    parsed_s = parse_stats(stats)
    return {'release_fields':shape(release),'stats_fields':shape(stats),
            'validated':{'release_id':parsed_r['release_id'],'stats':parsed_s},
            'note':'僅驗證本次唯讀回應；不代表上架權限或全部版本資料可用'}
