import type {Comparison} from '@/components/comparison-table';
const names:Record<string,string>={yahoo_tw:'Yahoo 台灣拍賣',yahoo_jp:'Yahoo 日本拍賣',ruten:'露天市集',tower:'Tower'};
const formats:Record<string,string>={Vinyl:'黑膠',CD:'CD',Cassette:'卡帶'};
const money=(value:string|null|undefined)=>value==null?'—':Number(value).toLocaleString('zh-TW',{maximumFractionDigits:2});
const profit=(row:Comparison)=>row.gross_twd!=null&&Number.isFinite(Number(row.gross_twd))?Number(row.gross_twd):-Infinity;
function Source({row:r}:{row:Comparison}){
 let href:string|undefined;try{const url=new URL(r.source_url);if(['https:','http:'].includes(url.protocol))href=url.href}catch{/* Invalid links stay plain text. */}
 const margin=r.gross_margin, known=margin!=null&&Number.isFinite(margin), loss=known&&margin<0;
 const width=known?Math.min(100,Math.abs(margin)*100)/2:0;
 return <div className="record-source">
  <div className="source-identity">
   <div><b>{names[r.vendor]||r.vendor}</b> <span className="badge media-badge">{formats[r.source_format||'']||'類型待確認'}</span></div>
   <p>{href?<a href={href} target="_blank" rel="noopener noreferrer">{r.source_title} ↗</a>:r.source_title}</p>
   <small>{r.version_confirmed?'已核對版本':'可能配對，版本待核對'} · {r.availability}</small>
   <small>Label：{r.labels||'尚未取得'} · Discogs 編號：{r.catalog_no||'尚未取得'} · 貨源編號：{r.source_catalog_no||'尚未取得'}</small>
  </div>
  <div className="source-financials">
   <div><small>進貨標價</small><b>{r.source_price===null?'價格未取得':`${r.source_currency} ${money(r.source_price)}`}</b><small>{r.price_kind==='current_bid'?'拍賣參考出價':r.price_kind==='range'?'規格價格待確認':'未含運費'}</small></div>
   <div><small>Discogs 參考售價</small><b>{r.market_currency} {money(r.market_price)}</b><small>約 NT$ {money(r.sale_twd)} · 非成交價</small></div>
   <div className={loss?'profit negative':'profit positive'}><small>價差／毛利</small><b>{r.gross_twd==null?'尚無估算':`NT$ ${money(r.gross_twd)}`}</b><small>{r.cost_basis==='confirmed_total'?'售價 − 已確認總成本':'售價 − 貨源標價（同幣別）'}</small></div>
   <div className={loss?'profit negative':'profit positive'}><small>毛利率</small><b>{known?`${(margin*100).toFixed(1)}%`:'—'}</b><div className="profit-bar" role="img" aria-label={known?`預估毛利率 ${(margin*100).toFixed(1)}%，${loss?'虧損':'正毛利'}`:'毛利率尚未取得'}><i style={{left:`${loss?50-width:50}%`,width:`${width}%`}}/></div></div>
  </div>
  <small className="source-cost-note">{r.cost_basis==='confirmed_total'?'採已確認總成本':'尚未扣除進貨運費'}；毛利尚未扣除平台費等營運費用</small>
 </div>;
}
export default function RecordSources({rows}:{rows:Comparison[]}){
 const unique=[...new Map(rows.filter(r=>!r.excluded).map(r=>[r.source_url,r])).values()].sort((a,b)=>profit(b)-profit(a));
 return <section className="record-sources" aria-label="對應進貨賣場"><h3>對應進貨賣場 · {unique.length} 件{unique.length>1?' · 預估毛利由高到低':''}</h3>{unique.length?<><Source row={unique[0]}/>{unique.length>1&&<details><summary>展開其餘 {unique.length-1} 個賣場</summary>{unique.slice(1).map(r=><Source key={r.source_url} row={r}/>)}</details>}</>:<p>尚未找到對應貨源，資料會保留等待後續比對。</p>}</section>;
}
