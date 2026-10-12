'use client';
import {useState} from 'react';
import {canSubmit,listingUrl,needsReview,openCount,submissionLabel,type SubmissionState} from '@/lib/listing-submission';
type Props={data?:SubmissionState;enabled:boolean;selected:number[];blocked:number;hidden:number;currency:string;locked:boolean;send:(path:string,data:object,onError?:(message:string)=>void)=>Promise<boolean>;onSubmitted:()=>void};
export default function ListingSubmission({data,enabled,selected,blocked,hidden,currency,locked,send,onSubmitted}:Props){
 const [status,setStatus]=useState<'Draft'|'For Sale'>('Draft');
 const [confirming,setConfirming]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [review,setReview]=useState<{draft_id:number;outcome:'listed'|'not_listed'}|null>(null);
 const [listingId,setListingId]=useState('');
 const open=openCount(data?.rows);
 const ready=canSubmit({enabled,selected:selected.length,blocked,hidden,locked:locked||busy,open});
 async function publish(){
  setBusy(true);setError('');
  try{if(await send('/api/listings/publish',{draft_ids:selected,currency,status},message=>setError(message))){setConfirming(false);onSubmitted()}}
  finally{setBusy(false)}
 }
 async function resolve(){
  if(!review)return;setBusy(true);setError('');
  try{if(await send('/api/listings/submissions/resolve',{draft_id:review.draft_id,outcome:review.outcome,listing_id:review.outcome==='listed'?listingId.trim():undefined},message=>setError(message))){setReview(null);setListingId('')}}
  finally{setBusy(false)}
 }
 return <section className="panel" aria-label="Discogs 刊登送出"><div className="section-title"><div><h2>送出到 Discogs</h2><p>以已勾選、通過匯出檢查的草稿直接建立 Discogs 刊登，每件只送一次；結果不明時停止，不自動重送。</p></div></div>
 <div className="panel-foot">
 {!data?<p>Discogs 刊登送出功能等待後端更新。</p>:!enabled?<p>後端尚未啟用 Discogs 刊登寫入（DISCOGS_LISTING_WRITE），目前只能匯出 Quicklister 檔。</p>:<>
 <label className="field"><span>建立方式</span><select disabled={locked||busy||confirming} value={status} onChange={e=>setStatus(e.target.value as 'Draft'|'For Sale')}><option value="Draft">Discogs 草稿（先在 Discogs 核對再出售）</option><option value="For Sale">直接出售（For Sale）</option></select></label>
 <p aria-live="polite">已選 {selected.length} 件 · 幣別 {currency} · 匯出檢查未通過 {blocked} 件{hidden>0?` · 篩選外已選 ${hidden} 件`:''}{open>0?` · 仍有 ${open} 件結果待核對，請先處理`:''}</p>
 {!confirming?<button className="btn primary" disabled={!ready} onClick={()=>setConfirming(true)}>送出 {selected.length} 件到 Discogs</button>:<div role="group" aria-label="確認送出"><p>將為 {selected.length} 件草稿各建立一筆 {status==='Draft'?'Discogs 草稿刊登':'For Sale 刊登'}，價格依草稿售價（{currency}）。送出後請到 Discogs 核對版本、照片與出貨條款。</p><button className="btn primary" disabled={!ready} onClick={()=>void publish()}>{busy?'送出中…':'確認送出'}</button>{' '}<button className="btn secondary" disabled={busy} onClick={()=>setConfirming(false)}>取消</button></div>}
 {error&&<p role="alert">{error}</p>}
 </>}
 {data&&<><p>{['submitting','listed','failed','uncertain'].map(key=>`${submissionLabel(key)} ${data.counts?.[key]||0}`).join(' · ')}</p>
 <details><summary>最近 {data.limit} 筆送出紀錄</summary>{data.rows.length?data.rows.map(row=>{const url=listingUrl(row.listing_id);return <div className="setting-row" key={`${row.draft_id}:${row.started_at}`}><div><b>草稿 #{row.draft_id} · 版本 {row.release_id} · {submissionLabel(row.status)}</b><small>{row.artist?`${row.artist} — ${row.title}`:''} · {row.currency} {row.price} · 要求 {row.requested_status} · {new Date(row.started_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei'})}（台北）</small>{url&&<small><a href={url} target="_blank" rel="noreferrer">Discogs 刊登 #{row.listing_id}</a></small>}{row.reason&&<small>{row.reason}</small>}{needsReview(row)&&<><p>請先到 Discogs 賣場或讀回刊登狀態確認是否已建立；系統不會重送。</p><button className="btn secondary" disabled={locked||busy} onClick={()=>setReview({draft_id:row.draft_id,outcome:'listed'})}>已核對有此刊登</button>{' '}<button className="btn secondary" disabled={locked||busy} onClick={()=>setReview({draft_id:row.draft_id,outcome:'not_listed'})}>確認未建立</button></>}</div></div>}):<p>尚未送出任何刊登。</p>}</details>
 {review&&<div role="group" aria-label="確認刊登核對結果"><p>草稿 #{review.draft_id}：{review.outcome==='listed'?'登錄 Discogs 已建立的刊登編號，並標記此貨源版本已上架。':'標記 Discogs 未建立刊登；草稿可重新確認後再送出。'}</p>{review.outcome==='listed'&&<label className="field"><span>Discogs 刊登編號</span><input value={listingId} onChange={e=>setListingId(e.target.value)} inputMode="numeric" placeholder="例如 123456789"/></label>}<button className="btn" disabled={locked||busy||(review.outcome==='listed'&&!/^\d+$/.test(listingId.trim()))} onClick={()=>void resolve()}>確認登錄</button>{' '}<button className="btn secondary" disabled={busy} onClick={()=>{setReview(null);setListingId('')}}>取消</button></div>}</>}
 <p>每件送出前先記錄，再呼叫 Discogs；回應不完整、連線中斷或伺服器錯誤會標為結果不明並停止後續草稿。讀回刊登狀態時若找到相同識別碼會自動對帳。這是建立刊登，不是售出保證；照片仍須在 Discogs 補上。</p>
 </div></section>;
}
