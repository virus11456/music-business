'use client';
import {useEffect,useState} from 'react';
import {apiFetch} from '@/lib/api';

type Point={captured_at:string;lowest_price:string|null;currency:string|null};
export function historyRows(body:unknown,releaseId:number):Point[]|null{
 const data=body as {release_id?:unknown;history?:unknown};
 if(!data||data.release_id!==releaseId||!Array.isArray(data.history))return null;
 return data.history.filter((p):p is Point=>!!p&&typeof (p as Point).captured_at==='string');
}
const amount=(v:string|null)=>v==null?'—':Number(v).toLocaleString('zh-TW',{maximumFractionDigits:2});
const time=(v:string)=>new Date(v).toLocaleString('zh-TW',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});

/** Price history is loaded only when a record's detail opens; the list itself no longer carries it. */
export default function PriceHistory({releaseId}:{releaseId:number}){
 const [rows,setRows]=useState<Point[]|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  let live=true;setRows(null);setError('');
  apiFetch(`/api/history?release_id=${releaseId}`).then(async r=>{
   if(!r.ok)throw Error();
   const parsed=historyRows(await r.json(),releaseId);if(!parsed)throw Error();
   if(live)setRows(parsed);
  }).catch(()=>{if(live)setError('行情紀錄讀取失敗，請稍後再開一次')});
  return()=>{live=false};
 },[releaseId]);
 if(error)return <p className="detail-note">{error}</p>;
 if(!rows)return <p className="detail-note">正在讀取行情紀錄…</p>;
 if(!rows.length)return <p className="detail-note">尚無行情紀錄</p>;
 return <div className="history">{rows.map(h=><div key={h.captured_at}><span>{time(h.captured_at)}</span><b>{h.currency} {amount(h.lowest_price)}</b></div>)}</div>;
}
