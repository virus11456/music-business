import type {Comparison} from '@/components/comparison-table';
const names:Record<string,string>={yahoo_tw:'Yahoo 台灣拍賣',yahoo_jp:'Yahoo 日本拍賣',ruten:'露天市集',tower:'Tower'};
const money=(value:string|null)=>value===null?'價格未取得':Number(value).toLocaleString('zh-TW',{maximumFractionDigits:2});
function Source({row:r}:{row:Comparison}){
 let href:string|undefined;try{const url=new URL(r.source_url);if(['https:','http:'].includes(url.protocol))href=url.href}catch{/* Invalid links stay plain text. */}
 return <div className="record-source"><div><b>{names[r.vendor]||r.vendor}</b><p>{href?<a href={href} target="_blank" rel="noopener noreferrer">{r.source_title} ↗</a>:r.source_title}</p><small>{r.version_confirmed?'已核對版本':'可能配對，版本待核對'} · {r.availability}</small></div><div className="record-source-price"><b>{r.source_price===null?'價格未取得':`${r.source_currency} ${money(r.source_price)}`}</b><small>{r.price_kind==='current_bid'?'拍賣參考出價':r.price_kind==='range'?'規格價格待確認':'貨源標價，未含運費'}</small><small>{r.gross_twd===null?'毛利待取得價格／匯率':`預估毛利 NT$ ${money(r.gross_twd)}`}{r.cost_basis==='confirmed_total'?'（採已確認總成本）':''}</small>{href&&<a href={href} target="_blank" rel="noopener noreferrer">開啟商品賣場 ↗</a>}</div></div>;
}
export default function RecordSources({rows}:{rows:Comparison[]}){
 const unique=[...new Map(rows.filter(r=>!r.excluded).map(r=>[r.source_url,r])).values()];
 return <section className="record-sources" aria-label="對應進貨賣場"><h3>對應進貨賣場 · {unique.length} 件</h3>{unique.length?<>{unique.slice(0,3).map(r=><Source key={r.source_url} row={r}/>)}{unique.length>3&&<details><summary>展開其餘 {unique.length-3} 個賣場</summary>{unique.slice(3).map(r=><Source key={r.source_url} row={r}/>)}</details>}</>:<p>尚未找到對應貨源，資料會保留等待後續比對。</p>}</section>;
}
