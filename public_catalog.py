"""Explicit public catalogue projection; never serialize the admin state wholesale."""
from copy import deepcopy

RECORD_FIELDS = 'release_id artist title format country year catno'.split()
SNAPSHOT_FIELDS = 'want have lowest_price currency num_for_sale captured_at'.split()
COMPARISON_FIELDS = """key format source_format candidate_id source_title release_id release_title
vendor source_url source_price source_currency price_kind availability has_market market_price
market_currency market_at source_at cost_at cost_basis want have sale_basis sale_usd sale_twd
source_twd cost_twd spread_twd gross_twd gross_margin barcodes source_barcodes labels catalog_no
source_catalog_no source_catalog_from_title evidence version_confirmed excluded""".split()

def pick(row, fields):
    return {key:deepcopy(row[key]) for key in fields if key in row}

def public_catalog(state):
    records=[]
    for record in state['records']:
        row=pick(record, RECORD_FIELDS)
        row['snapshot']=pick(record['snapshot'], SNAPSHOT_FIELDS) if record.get('snapshot') else None
        records.append(row)
    comparisons=[]
    for comparison in state['workflow']['comparisons']:
        # Manual offers can carry private draft prices and procurement decisions.
        if comparison.get('offer') is not None:
            continue
        row=pick(comparison, COMPARISON_FIELDS)
        row.update(offer=None,ready=False,issues=[],status='版本候選，待核對',
                   listing_status='unknown',net_twd=None,net_margin=None,fees_twd=None)
        comparisons.append(row)
    return {'permissions':{'can_write':False}, 'records':records,
            'workflow':{'comparisons':comparisons}, 'csrf':''}
