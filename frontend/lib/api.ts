export const hosted=typeof __HOSTED_FRONTEND__!=='undefined'&&__HOSTED_FRONTEND__;
export const apiOrigin=typeof __API_ORIGIN__!=='undefined'?__API_ORIGIN__:'';
let accessCode='';
let revision=0;
const pending=new Set<AbortController>();
export const accessRevision=()=>revision;
export function setAccessCode(value:string){accessCode=value;revision++;for(const c of pending)c.abort();pending.clear();}
export async function apiFetch(path:string,options:RequestInit={}){
 const headers=new Headers(options.headers);
 if(accessCode)headers.set('Authorization',`Bearer ${accessCode}`);
 const controller=new AbortController();pending.add(controller);
 const timeout=setTimeout(()=>controller.abort(),30000);
 try{return await fetch(apiOrigin+path,{...options,headers,signal:controller.signal,credentials:'omit',redirect:'error'});}
 finally{clearTimeout(timeout);pending.delete(controller);}
}
export async function downloadCsv(path:string,filename:string){
 const response=await apiFetch(path);
 if(!response.ok){let message='匯出失敗，請確認登入及所選商品幣別';try{const body=await response.json() as {error?:unknown};if(typeof body.error==='string')message=body.error;}catch{}throw Error(message);}
 const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
