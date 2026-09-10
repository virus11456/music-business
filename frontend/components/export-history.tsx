export type ExportBatch={id:number;generated_at:string;currency:string;items:{id:number;release_id:number;artist:string;title:string;format:string;price:string;media_cond:string;sleeve_cond:string}[]};
export default function ExportHistory({batches}:{batches:ExportBatch[]}){
 return <section className="panel" aria-label="匯出紀錄"><div className="section-title"><div><h2>匯出紀錄</h2><p>最近 20 批 Quicklister 檔案產生紀錄，保留當時商品與售價。</p></div></div>
 {batches.length?batches.map(batch=><details className="draft-row" key={batch.id}><summary>批次 #{batch.id} · {new Date(batch.generated_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})}（台北） · {batch.items.length} 件 · {batch.currency}</summary>
 {batch.items.map(item=><div className="setting-row" key={item.id}><div><b>{item.artist} — {item.title}</b><small>{item.format} · 草稿 #{item.id} · Discogs #{item.release_id}</small><small>{item.media_cond} / {item.sleeve_cond}</small></div><b>{batch.currency} {Number(item.price).toLocaleString()}</b></div>)}
 </details>):<div className="empty compact">尚未產生 Quicklister 匯出紀錄。</div>}
 <div className="panel-foot">紀錄表示系統已產生檔案，不代表瀏覽器已下載完成、Discogs 已匯入或已刊登。後續修改草稿不會改動歷史紀錄；較早的匯出不會補登。下載後稍候，紀錄會隨頁面資料更新顯示。</div></section>;
}
