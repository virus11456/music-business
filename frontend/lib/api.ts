export const hosted=typeof __HOSTED_FRONTEND__!=='undefined'&&__HOSTED_FRONTEND__;
export const apiOrigin=typeof __API_ORIGIN__!=='undefined'?__API_ORIGIN__:'';
let accessCode='';
export function setAccessCode(value:string){accessCode=value;}
export async function apiFetch(path:string,options:RequestInit={}){
 const headers=new Headers(options.headers);
 if(accessCode)headers.set('Authorization',`Bearer ${accessCode}`);
 return fetch(apiOrigin+path,{...options,headers,credentials:'omit',redirect:'error'});
}
export async function downloadCsv(path:string,filename:string){
 const response=await apiFetch(path);
 if(!response.ok){let message='匯出失敗，請確認登入及所選商品幣別';try{const body=await response.json() as {error?:unknown};if(typeof body.error==='string')message=body.error;}catch{}throw Error(message);}
 const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
