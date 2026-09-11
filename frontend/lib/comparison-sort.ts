import type {Comparison} from '@/components/comparison-table';
export function sortComparisons(rows:Comparison[],sort:string){
 const key=({want:'want',gross:'gross_twd',margin:'gross_margin',net:'net_twd',spread:'spread_twd'} as const)[sort as 'want']||'want';
 const value=(r:Comparison)=>r[key]==null?-Infinity:Number(r[key]);
 return [...rows].sort((a,b)=>value(b)-value(a)||a.key.localeCompare(b.key));
}

export function referenceUsd(row:Comparison):number|null{
 const raw=row.sale_usd!==undefined?row.sale_usd:
  row.offer?.sale_price?(row.offer.sale_currency==='USD'?row.offer.sale_price:null):
  row.market_currency==='USD'?row.market_price:null;
 if(raw===null||raw===undefined||String(raw).trim()==='')return null;
 const value=Number(raw);return Number.isFinite(value)&&value>0?value:null;
}
export function meetsMinimumUsd(row:Comparison,minimum:string){
 const threshold=Number(minimum);
 if(!Number.isFinite(threshold)||threshold<=0)return true;
 const price=referenceUsd(row);return price!==null&&price>=threshold;
}

export function marketFreshness(row:Comparison,now=Date.now()):'fresh'|'stale'|'unknown'{
 if(!row.has_market||!row.market_at)return 'unknown';
 const age=now-Date.parse(row.market_at);
 if(!Number.isFinite(age)||age<0)return 'unknown';
 return age<=48*60*60*1000?'fresh':'stale';
}
export function marketTimestamp(row:Comparison){
 if(!row.market_at||!Number.isFinite(Date.parse(row.market_at)))return '時間未取得';
 return new Date(row.market_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
}

export function sourceFreshness(row:Comparison,now=Date.now()):'fresh'|'stale'|'unknown'{
 const stamp=row.cost_basis==='confirmed_total'?row.cost_at:row.source_at;
 if(!stamp)return 'unknown';
 const age=now-Date.parse(stamp);
 return !Number.isFinite(age)||age<0?'unknown':age<=48*3600000?'fresh':'stale';
}
export function sourceTimestamp(row:Comparison){
 const stamp=row.cost_basis==='confirmed_total'?row.cost_at:row.source_at;
 return stamp&&Number.isFinite(Date.parse(stamp))?new Date(stamp).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'時間未取得';
}

export function hasDemandAndSource(row:Comparison){
 const positive=(v:unknown)=>v!==null&&v!==undefined&&String(v).trim()!==''&&Number.isFinite(Number(v))&&Number(v)>0;
 let validLink=false;try{validLink=['https:','http:'].includes(new URL(row.source_url).protocol)}catch{}
 return !!row.format&&row.format===row.source_format&&!row.excluded&&row.has_market&&positive(row.want)&&positive(row.market_price)&&positive(row.source_price)&&!!row.market_currency&&!!row.source_currency&&validLink;
}

export function hasFreshComparison(row:Comparison,now=Date.now()){
 return marketFreshness(row,now)==='fresh'&&sourceFreshness({...row,cost_basis:'source_price'},now)==='fresh'&&sourceFreshness(row,now)==='fresh';
}

export function candidateProfit(row:Pick<Comparison,'gross_twd'|'gross_margin'>,sort:'gross'|'margin'='gross'):number{
 const raw=sort==='margin'?row.gross_margin:row.gross_twd;
 return raw!=null&&String(raw).trim()!==''&&Number.isFinite(Number(raw))?Number(raw):-Infinity;
}
