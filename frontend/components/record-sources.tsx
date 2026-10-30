import {useState} from 'react';
import MediaBadge from '@/components/media-badge';
import {matchLabel} from '@/lib/match-evidence';
import {sourceAvailability,supplyLabels} from '@/lib/source-availability';
import {candidateProfit,marketFreshness,marketTimestamp,sourceFreshness,sourceTimestamp} from '@/lib/comparison-sort';
import type {Comparison} from '@/components/comparison-table';
const names:Record<string,string>={yahoo_tw:'Yahoo 台灣拍賣',yahoo_jp:'Yahoo 日本拍賣',ruten:'露天市集',tower:'Tower',rottenblues:'Rotten Blues 爛調唱片'};
let numberFormat:Intl.NumberFormat|undefined;
const money=(value:string|null|undefined)=>value==null?'—':(numberFormat??=new Intl.NumberFormat('zh-TW',{maximumFractionDigits:2})).format(Number(value));
type Actions={purchaseLocked?:boolean;onPurchase?:(row:Comparison)=>void;purchaseKeys?:string[];locked?:boolean;onAction?:(row:Comparison)=>void};
function Source({row:r,locked,onAction,onPurchase,purchaseKeys,purchaseLocked}:{row:Comparison}&Actions){
 let href:string|undefined;try{const url=new URL(r.source_url);if(['https:','http:'].includes(url.protocol))href=url.href}catch{/* Invalid links stay plain text. */}
 const margin=r.gross_margin, known=margin!=null&&Number.isFinite(margin), loss=known&&margin<0;
 const netKnown=r.net_twd!=null&&Number.isFinite(Number(r.net_twd)),netLoss=netKnown&&Number(r.net_twd)<0;
 const quote={...r,cost_basis:'source_price'};
 const freshness=(value:string)=>value==='fresh'?'48 小時內':value==='stale'?'超過 48 小時':'時間待確認';
 const width=known?Math.min(100,Math.abs(margin)*100)/2:0;
 return <div className="record-source">
  <div className="source-identity">
   <div><b>{names[r.vendor]||r.vendor}</b> <MediaBadge format={r.source_format}/> <span className={'badge '+(sourceAvailability(r)==='stock'?'green':'amber')}>{supplyLabels[sourceAvailability(r)]}</span> <span className={'badge '+(r.listing_status==='listed'?'green':'')}>{r.listing_status==='listed'?'已上架':r.listing_status==='unlisted'?'未上架':'刊登狀態待確認'}</span></div>
   <p>{href?<a href={href} target="_blank" rel="noopener noreferrer">{r.source_title} ↗</a>:r.source_title}</p>
   <small>{matchLabel(r)} · {r.availability}</small>
   <small>Label：{r.labels||'尚未取得'} · Discogs 編號：{r.catalog_no||'尚未取得'} · 貨源編號：{r.source_catalog_no||'尚未取得'}{r.source_catalog_from_title?'（由標題辨識，待核對）':''}</small>
  </div>
  <div className="source-financials">
   <div><small>進貨標價</small><b>{r.source_price===null?'價格未取得':`${r.source_currency} ${money(r.source_price)}`}</b><small>{r.price_kind==='current_bid'?'拍賣參考出價':r.price_kind==='range'?'規格價格待確認':'未含運費'}</small><small className={sourceFreshness(quote)==='fresh'?'':'quote-warning'}>貨源 {sourceTimestamp(quote)} · {freshness(sourceFreshness(quote))}</small></div>
   <div><small>Discogs 參考售價</small><b>{r.market_currency} {money(r.market_price)}</b><small>約 NT$ {money(r.sale_twd)} · 非成交價</small><small className={marketFreshness(r)==='fresh'?'':'quote-warning'}>行情 {marketTimestamp(r)} · {freshness(marketFreshness(r))}</small></div>
   <div className={loss?'profit negative':'profit positive'}><small>價差／毛利</small><b>{r.gross_twd==null?'尚無估算':`NT$ ${money(r.gross_twd)}`}</b><small>{r.cost_basis==='confirmed_total'?'售價 − 已確認總成本':'售價 − 貨源標價（同幣別）'}</small></div>
   <div className={loss?'profit negative':'profit positive'}><small>毛利率</small><b>{known?`${(margin*100).toFixed(1)}%`:'—'}</b><div className="profit-bar" role="img" aria-label={known?`預估毛利率 ${(margin*100).toFixed(1)}%，${loss?'虧損':'正毛利'}`:'毛利率尚未取得'}><i style={{left:`${loss?50-width:50}%`,width:`${width}%`}}/></div></div>
  </div>
  <div className="source-card-footer"><div className="source-cost-summary"><small className={netLoss?'net-summary loss':'net-summary'}>{netKnown?`扣已設定費用後：NT$ ${money(r.net_twd)}${netLoss?' · 估算虧損':''}`:'扣費後金額待取得'}</small><small className="source-cost-note">{r.cost_basis==='confirmed_total'?`採已確認總成本（${sourceTimestamp(r)} · ${freshness(sourceFreshness(r))}）`:'尚未扣除進貨運費'}；毛利尚未扣除平台費等營運費用</small></div>{onPurchase&&<button type="button" className="btn secondary" disabled={locked||purchaseLocked||purchaseKeys?.includes(r.key)} onClick={()=>onPurchase(r)}>{purchaseKeys?.includes(r.key)?'已加入採購清單':'加入採購清單'}</button>}{onAction&&<button type="button" className="btn secondary" disabled={locked||!r.has_market} onClick={()=>onAction(r)}>{r.ready?'建立草稿':'核對貨源'}</button>}</div>
 </div>;
}
/** One card per source, best estimate first; the order the cards are shown in. */
export function sourceRows(rows:Comparison[],sortBy:'gross'|'margin'='gross'){
 return [...new Map(rows.filter(r=>!r.excluded).map(r=>[r.source_url,r])).values()].sort((a,b)=>candidateProfit(b,sortBy)-candidateProfit(a,sortBy));
}
export default function RecordSources({rows,locked,onAction,onPurchase,purchaseKeys,purchaseLocked,sortBy='gross'}:{rows:Comparison[];sortBy?:'gross'|'margin'}&Actions){
 // Collapsed cards are built only after the list is opened; some releases have hundreds of sources.
 const [open,setOpen]=useState(false);
 const unique=sourceRows(rows,sortBy);
 return <section className="record-sources" aria-label="對應進貨賣場"><h3>對應進貨賣場 · {unique.length} 件{unique.length>1?(sortBy==='margin'?' · 預估毛利率由高到低':' · 預估毛利由高到低'):''}</h3>{unique.length?<><Source row={unique[0]} locked={locked} onAction={onAction} onPurchase={onPurchase} purchaseKeys={purchaseKeys} purchaseLocked={purchaseLocked}/>{unique.length>1&&<details open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>展開其餘 {unique.length-1} 個賣場</summary>{open&&unique.slice(1).map(r=><Source key={r.source_url} row={r} locked={locked} onAction={onAction} onPurchase={onPurchase} purchaseKeys={purchaseKeys} purchaseLocked={purchaseLocked}/>)}</details>}</>:<p>尚未找到對應貨源，資料會保留等待後續比對。</p>}</section>;
}
