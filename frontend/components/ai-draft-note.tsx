import {useState} from 'react';
import {apiFetch,accessRevision} from '@/lib/api';
export default function AIDraftNote({draftId,csrf,configured,locked,onApply}:{draftId:number;csrf?:string;configured:boolean;locked:boolean;onApply:(note:string)=>void}){
 const [busy,setBusy]=useState(false),[suggestion,setSuggestion]=useState(''),[error,setError]=useState('');
 async function generate(){
  const revision=accessRevision();setBusy(true);setError('');setSuggestion('');
  try{
   const r=await apiFetch('/api/drafts/suggest-note',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf||''},body:JSON.stringify({draft_id:draftId})});
   const data=await r.json() as {error?:string;suggestion?:unknown};if(revision!==accessRevision())return;
   if(!r.ok)throw Error(data.error||'文案產生失敗');
   if(typeof data.suggestion!=='string')throw Error('文案回應無效');
   setSuggestion(data.suggestion);
  }catch(e){if(revision===accessRevision())setError(e instanceof Error?e.message:'文案產生失敗');}
  finally{setBusy(false);}
 }
 return <div className="panel-foot"><button type="button" className="btn secondary" disabled={locked||busy||!configured||!csrf} onClick={()=>void generate()}>{busy?'AI 正在產生建議…':'AI 協助英文文案'}</button><p>{configured?'將已儲存草稿的歌手、專輯、格式、品相與補充內容傳給 OpenAI；不傳送進貨成本或賣場連結。':'AI 尚未設定，請先在後端設定金鑰與模型。'}</p>{error&&<p role="alert">{error}</p>}{suggestion&&<><p>待人工核對（尚未儲存）</p><textarea aria-label="AI 文案建議" value={suggestion} maxLength={220} onChange={e=>setSuggestion(e.target.value)}/><button type="button" className="btn secondary" disabled={locked||!suggestion.trim()} onClick={()=>{onApply(suggestion);setSuggestion('')}}>套用到補充欄位</button></>}</div>;
}
