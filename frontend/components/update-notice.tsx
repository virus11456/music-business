'use client';
import {useEffect,useState} from 'react';
export default function UpdateNotice(){
 const [available,setAvailable]=useState(false);
 useEffect(()=>{
  if(typeof __BUILD_ID__==='undefined')return;
  let disposed=false;let running=false;let last=0;let controller:AbortController|undefined;
  async function check(){
   if(document.visibilityState!=='visible'||running||Date.now()-last<60000)return;
   last=Date.now();running=true;controller=new AbortController();const timeout=setTimeout(()=>controller?.abort(),10000);
   try{const response=await fetch('/version.json',{cache:'no-store',credentials:'omit',redirect:'error',signal:controller.signal});if(!response.ok)return;const data=await response.json();if(!disposed)setAvailable(data!==null&&typeof data==='object'&&'buildId' in data&&typeof data.buildId==='string'&&data.buildId.length>0&&data.buildId!==__BUILD_ID__);}catch{/* Keep the current page usable when offline. */}finally{clearTimeout(timeout);running=false;}
  }
  void check();const timer=setInterval(()=>void check(),60000);const focus=()=>void check();document.addEventListener('visibilitychange',focus);
  return()=>{disposed=true;clearInterval(timer);controller?.abort();document.removeEventListener('visibilitychange',focus)};
 },[]);
 if(!available)return null;
 return <div className="alert" role="status"><span>網站已有更新。請先儲存編輯內容；重新整理後需再次登入。</span><button onClick={()=>window.location.reload()}>重新整理取得新版</button></div>;
}
