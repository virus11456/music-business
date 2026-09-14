import {useEffect,useState} from 'react';
import {apiFetch} from '@/lib/api';
export default function LoginForm({onLogin}:{onLogin:(token:string)=>void}){
 const [resetToken,setResetToken]=useState(''),[resetMode,setResetMode]=useState(false),[done,setDone]=useState('');
 useEffect(()=>{const params=new URLSearchParams(window.location.hash.slice(1));const token=params.get('reset_token');if(token){setResetToken(token);setResetMode(true);window.history.replaceState(null,'',window.location.pathname+window.location.search)}},[]);
 const [legacy,setLegacy]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function submit(e:React.FormEvent<HTMLFormElement>){
  e.preventDefault();if(busy)return;const form=e.currentTarget,data=new FormData(form);
  if(resetMode&&String(data.get('password'))!==String(data.get('confirm_password'))){setError('兩次密碼不同，請重新確認');return}
  if(resetMode&&!resetToken){setError('請使用管理者提供的一次性重設連結');return}
  if(legacy&&!resetMode){onLogin(String(data.get('access_code')||''));form.reset();return}
  setBusy(true);setError('');
  try{
   const response=await apiFetch(resetMode?'/api/account/reset':'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:String(data.get('username')||''),password:String(data.get('password')||''),...(resetMode?{reset_token:resetToken}:{})})});
   const raw=await response.json();
   if(!raw||typeof raw!=='object')throw Error('登入回應無效，請稍後重試');
   const body=raw as {error?:unknown;session_token?:unknown};
   if(!response.ok)throw Error(typeof body.error==='string'?body.error:'登入未完成');
   if(resetMode){form.reset();setResetToken('');setResetMode(false);setDone('帳號密碼已更新，請用新帳密登入。');return}
   if(typeof body.session_token!=='string'||!body.session_token)throw Error('登入回應無效，請稍後重試');
   form.reset();onLogin(body.session_token);
  }catch(e){setError(e instanceof Error&&e.name==='AbortError'?'登入連線逾時，請稍後重試':e instanceof Error?e.message:'登入失敗')}
  finally{setBusy(false)}
 }
 return <form className="panel" onSubmit={submit}><h2>{resetMode?'設定／重設帳號密碼':'登入工作室'}</h2>{done&&<p role="status">{done}</p>}{resetMode&&!resetToken&&<p>重設需要短效驗證連結。請由已登入的管理者或這次協助設定的人提供；不需操作終端，也不要傳送密碼。</p>}{legacy&&!resetMode?<label className="field"><span>管理者存取碼</span><input name="access_code" type="password" autoComplete="off" required disabled={busy}/></label>:<><label className="field"><span>帳號</span><input name="username" autoComplete="username" defaultValue="admin" required maxLength={100} disabled={busy}/></label><label className="field"><span>密碼</span><input name="password" type="password" autoComplete={resetMode?"new-password":"current-password"} required minLength={resetMode?15:undefined} maxLength={1024} disabled={busy}/></label>{resetMode&&<label className="field"><span>再次輸入新密碼</span><input name="confirm_password" type="password" autoComplete="new-password" required minLength={15} maxLength={1024} disabled={busy}/></label>}</>}
 <button type="submit" className="btn primary" disabled={busy}>{busy?'處理中…':resetMode?'儲存新帳號密碼':'登入工作室'}</button><button type="button" className="text-button" disabled={busy} onClick={()=>{setLegacy(!legacy);setResetMode(false);setError('')}}>{legacy?'使用帳號密碼':'使用原管理者存取碼'}</button><button type="button" className="text-button" disabled={busy} onClick={()=>{setResetMode(!resetMode);setError('')}}>{resetMode?'返回登入':'忘記帳號或密碼？'}</button>{error&&<p role="alert">{error}</p>}<p>{legacy?'存取碼只保留於本次頁面記憶體。':'登入最多有效8小時；重新整理後可用瀏覽器密碼管理器重新登入。'}</p></form>;
}
