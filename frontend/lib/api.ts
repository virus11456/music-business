import {normalizeState,PACKED_MEDIA_TYPE} from './state-pack';
export const hosted=typeof __HOSTED_FRONTEND__!=='undefined'&&__HOSTED_FRONTEND__;
export const apiOrigin=typeof __API_ORIGIN__!=='undefined'?__API_ORIGIN__:'';
let accessCode='';
let revision=0;
const pending=new Set<AbortController>();
export const accessRevision=()=>revision;
let stateEtag='';
export function setAccessCode(value:string){accessCode=value;revision++;stateEtag='';for(const c of pending)c.abort();pending.clear();}
export async function apiFetch(path:string,options:RequestInit={}){
 const headers=new Headers(options.headers);
 if(accessCode)headers.set('Authorization',`Bearer ${accessCode}`);
 const controller=new AbortController();pending.add(controller);
 const timeout=setTimeout(()=>controller.abort(),30000);
 try{return await fetch(apiOrigin+path,{...options,headers,signal:controller.signal,credentials:'omit',redirect:'error'});}
 finally{clearTimeout(timeout);pending.delete(controller);}
}
export async function downloadCsv(path:string,filename:string){
 const startedRevision=accessRevision();
 const response=await apiFetch(path);
 if(!response.ok){let message='匯出失敗，請確認登入及所選商品幣別';try{const body=await response.json() as {error?:unknown};if(typeof body.error==='string')message=body.error;}catch{}throw Error(message);}
 const blob=await response.blob();
 if(startedRevision!==accessRevision())throw Error('登入狀態已變更，已取消下載；請重新登入後核對匯出紀錄。');
 const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export type StateFetch={status:number;ok:boolean;unchanged:boolean;body?:unknown};
/** Read /api/state with a validator so an unchanged server state returns 304 and no body to parse or render. */
export async function fetchState():Promise<StateFetch>{
 // A CORS-safelisted Accept value: older servers ignore it and reply in the original shape.
 const headers:Record<string,string>={Accept:`${PACKED_MEDIA_TYPE}, application/json`};
 if(stateEtag)headers['If-None-Match']=stateEtag;
 const response=await apiFetch('/api/state',{headers});
 if(response.status===304){
  if(stateEtag)return {status:304,ok:true,unchanged:true};
  throw Error('資料服務回應不完整，請重新整理');
 }
 if(!response.ok)return {status:response.status,ok:false,unchanged:false};
 const body=normalizeState(await response.json() as unknown);
 stateEtag=response.headers.get('ETag')||'';
 return {status:response.status,ok:true,unchanged:false,body};
}
