import type {Comparison} from '@/components/comparison-table';
import {hasDemandAndSource,hasPositiveMargin,hasFreshComparison,sourceFreshness} from './comparison-sort';
import {matchLevel,matchConflicts} from './match-evidence';
import {sourceAvailability} from './source-availability';
export type PurchasePick={key:string;release_id:number;source_url:string;title:string;seller:string};
const platformNames:Record<string,string>={yahoo_tw:'Yahoo 台灣拍賣',yahoo_jp:'Yahoo 日本拍賣',ruten:'露天市集',tower:'Tower',rottenblues:'Rotten Blues 爛調唱片',rakuten:'樂天市場',ebay:'eBay'};
export const purchaseStorageKey='simples.purchase-list.v1';
export function parsePicks(raw:string|null):PurchasePick[]{
 try{const data=JSON.parse(raw||'[]');if(!Array.isArray(data))return [];
 return [...new Map(data.filter(p=>p&&typeof p.key==='string'&&Number.isSafeInteger(p.release_id)&&p.release_id>0&&typeof p.source_url==='string'&&/^https?:\/\//i.test(p.source_url)&&typeof p.title==='string'&&typeof p.seller==='string').slice(0,200).map(p=>[p.key,{key:p.key,release_id:p.release_id,source_url:p.source_url,title:p.title.slice(0,500),seller:p.seller.slice(0,100)}])).values()];
 }catch{return []}
}
export function purchaseSupply(row:Comparison,now=Date.now()):'platform'|'confirmed'|'unknown'{
 const supply=sourceAvailability(row);
 if(supply==='stock')return 'platform';
 const offer=row.offer;
 if(supply!=='unknown'||!offer||Number(offer.release_id)!==row.release_id||offer.source_url!==row.source_url)return 'unknown';
 const confirmed=offer.supply_confirmed===1||offer.supply_confirmed==='1';
 const sourceAt=Date.parse(row.source_at||''),confirmedAt=Date.parse(row.cost_at||'');
 if(confirmed&&sourceFreshness({...row,cost_basis:'confirmed_total'},now)==='fresh'&&Number.isFinite(sourceAt)&&sourceAt<=confirmedAt)return 'confirmed';
 return 'unknown';
}
export function purchaseSupplyLabel(row:Comparison,now=Date.now()){
 return {platform:'來源標示現貨',confirmed:'已人工確認供貨（48 小時內）',unknown:'供貨待重新確認'}[purchaseSupply(row,now)];
}
export function purchaseIssues(row:Comparison|undefined,now=Date.now()):string[]{
 if(!row)return ['目前資料未找到此配對，保留選取待更新'];
 const issues=matchConflicts(row);
 if(!hasDemandAndSource(row))issues.push('需求、價格、格式或連結不完整／配對已排除');
 if(!hasPositiveMargin(row))issues.push('目前不是正毛利');
 if(!hasFreshComparison(row,now))issues.push('貨源、行情或成本超過 48 小時／時間未知');
 if(purchaseSupply(row,now)==='unknown')issues.push('尚未確認現貨，或供貨確認已過期／來源有新資料');
 if(row.offer?.owned_confirmed===1||row.offer?.owned_confirmed==='1')issues.push('已持有商品，不列入待採購合計');
 if(matchLevel(row)!=='confirmed')issues.push('實際壓片版本待核對');
 return [...new Set(issues)];
}
export function purchaseRows(picks:PurchasePick[],rows:Comparison[],now=Date.now()){
 const identity=(release:number,url:string)=>JSON.stringify([release,url]);
 const index=new Map<string,Comparison[]>();
 for(const row of rows){const id=identity(row.release_id,row.source_url);index.set(id,[...(index.get(id)||[]),row])}
 return picks.map(pick=>{const matches=index.get(identity(pick.release_id,pick.source_url))||[];const row=matches.length===1?matches[0]:undefined;
 const issues=matches.length>1?['同一商品與版本存在多筆報價，請先核對後再計算']:purchaseIssues(row,now);
 if(picks.some(other=>other.key!==pick.key&&other.source_url===pick.source_url))issues.push('同一貨源選到多個版本，請保留正確的一筆');
 return {pick,row,issues};});
}
export type PurchaseItem=ReturnType<typeof purchaseRows>[number];
export function purchaseGroups(items:PurchaseItem[]){
 const groups=new Map<string,{name:string;items:PurchaseItem[]}>();
 for(const item of items){const rawVendor=item.row?.vendor||'平台待確認';const vendor=platformNames[rawVendor]||rawVendor;const seller=item.pick.seller.trim();
 const key=JSON.stringify([vendor,seller||item.pick.source_url]);
 if(!groups.has(key))groups.set(key,{name:seller?`${vendor} · ${seller}（自行指定）`:`${vendor} · 賣家待確認`,items:[]});
 groups.get(key)!.items.push(item);}
 return [...groups.values()];
}
export function purchaseTotals(items:PurchaseItem[]){
 const valid=items.filter(i=>!i.issues.length&&i.row&&[i.row.cost_basis==='confirmed_total'?i.row.cost_twd:i.row.source_twd,i.row.gross_twd].every(v=>v!=null&&String(v).trim()!==''&&Number.isFinite(Number(v))));
 return {count:valid.length,cost:valid.reduce((sum,i)=>sum+Number(i.row!.cost_basis==='confirmed_total'?i.row!.cost_twd:i.row!.source_twd),0),gross:valid.reduce((sum,i)=>sum+Number(i.row!.gross_twd),0)};
}
export function purchaseCsv(items:PurchaseItem[]){
 const cell=(v:unknown)=>{let text=String(v??'');if(/^[\s]*[=+\-@]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"'};
 const header=['平台','賣家（自行指定）','商品','Discogs 版本','格式','件數','進貨幣別','進貨標價','估算成本 TWD','預估毛利 TWD','毛利率','供貨依據','檢查結果','貨源更新','行情更新','商品連結'];
 return '\uFEFF'+[header,...items.map(({pick,row,issues})=>[row?.vendor,pick.seller,pick.title,pick.release_id,row?.format,1,row?.source_currency,row?.source_price,row?(row.cost_basis==='confirmed_total'?row.cost_twd:row.source_twd):'',row?.gross_twd,row?.gross_margin==null?'':(row.gross_margin*100).toFixed(1)+'%',row?purchaseSupplyLabel(row):'供貨待確認',issues.join('；')||'檢查通過，購買前仍須確認',row?.source_at,row?.market_at,pick.source_url])].map(r=>r.map(cell).join(',')).join('\r\n');
}
