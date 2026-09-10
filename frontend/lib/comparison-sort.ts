import type {Comparison} from '@/components/comparison-table';
export function sortComparisons(rows:Comparison[],sort:string){
 const key=({want:'want',gross:'gross_twd',margin:'gross_margin',net:'net_twd',spread:'spread_twd'} as const)[sort as 'want']||'want';
 const value=(r:Comparison)=>r[key]==null?-Infinity:Number(r[key]);
 return [...rows].sort((a,b)=>value(b)-value(a)||a.key.localeCompare(b.key));
}
