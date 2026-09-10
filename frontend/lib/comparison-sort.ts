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
