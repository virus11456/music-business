'use client';
import {useState,type FormEvent} from 'react';
export type SourceTopic={query:string;platforms?:string;collected_at?:string};
type Platform={id:string;name:string;supported:boolean};
export function topicPlatforms(topic:SourceTopic,catalog:Platform[]){
 try{const parsed:unknown=JSON.parse(topic.platforms||'[]');return Array.isArray(parsed)?[...new Set(parsed.filter((id):id is string=>typeof id==='string'&&catalog.some(p=>p.supported&&p.id===id)))]:[]}catch{return []}
}
export function collectionRequest(query:string,selected:string[],catalog:Platform[]){
 const clean=query.trim(),platforms=[...new Set(selected.filter(id=>catalog.some(p=>p.supported&&p.id===id)))];
 return clean&&clean.length<=120&&platforms.length?{query:clean,platforms}:null;
}
export default function SourceCollectionForm({topics,catalog,locked,send}:{topics:SourceTopic[];catalog:Platform[];locked:boolean;send:(path:string,data:object)=>Promise<boolean>}){
 const [query,setQuery]=useState(''),[selected,setSelected]=useState(()=>catalog.filter(p=>p.supported).map(p=>p.id)),[saving,setSaving]=useState(false);
 const existing=topics.find(t=>t.query===query.trim());
 const request=collectionRequest(query,selected,catalog),disabled=locked||saving;
 function choose(value:string){const topic=topics.find(t=>t.query===value);setQuery(topic?.query||'');setSelected(topic?topicPlatforms(topic,catalog):catalog.filter(p=>p.supported).map(p=>p.id))}
 async function run(data:object){if(disabled)return;setSaving(true);try{await send('/api/sourcing/reverse',data)}finally{setSaving(false)}}
 function submit(e:FormEvent){e.preventDefault();if(request)void run(request)}
 return <form className="platform-form" onSubmit={submit}>
  <label className="field"><span>搜尋主題</span><select value={existing?.query||''} disabled={disabled} onChange={e=>choose(e.target.value)}><option value="">新增搜尋主題</option>{topics.map(t=><option key={t.query} value={t.query}>{t.query}</option>)}</select></label>
  <label className="field"><span>要收集的商品</span><input name="query" value={query} onChange={e=>{const value=e.target.value;setQuery(value);const topic=topics.find(t=>t.query===value.trim());if(topic)setSelected(topicPlatforms(topic,catalog))}} disabled={disabled} required maxLength={120} placeholder="例如：黑膠、CD、卡帶、The Beatles"/></label>
  <div className="platform-options">{catalog.filter(p=>p.supported).map(p=><label className="check-field" key={p.id}><input type="checkbox" name="platforms" value={p.id} checked={selected.includes(p.id)} disabled={disabled} onChange={e=>setSelected(e.target.checked?[...selected,p.id]:selected.filter(id=>id!==p.id))}/>{p.name}</label>)}</div>
  {selected.includes('rottenblues')&&<p>Rotten Blues 每次讀取一頁商品目錄，再依文字或格式篩選。收集全店唱片請填「Rotten Blues 全部唱片」；本頁無符合商品仍會接續下一頁。</p>}
  {!selected.length&&<p role="status">請至少選擇一個進貨平台。</p>}
  <p>{existing?'接續這個主題已保存的頁碼；送出後更新它的平台設定。':'完成首次收集後，這個主題與所選平台會保存並納入定時更新。'}每天 10:00、16:00、22:00 輪流處理；佇列較多時先完成已存商品比對。</p>
  <button type="submit" className="btn primary" disabled={disabled||!request}>{existing?'接續此主題 → 反查需求 → 同步 Sheets':'新增主題並收集 → 反查需求 → 同步 Sheets'}</button>
  <button type="button" className="btn secondary" disabled={disabled} onClick={()=>void run({})}>只處理已存商品的下一批</button>
 </form>;
}
