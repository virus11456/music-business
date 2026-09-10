'use client';
import {useState,type FormEvent} from 'react';
import {Button} from '@/components/ui/button';
export type Assumptions={fee_pct:string;shipping:string;packing:string;reserve:string;min_margin:string};
export default function AssumptionsForm({values,locked,send}:{values:Assumptions;locked:boolean;send:(path:string,data:object)=>Promise<boolean>}){
 const [saving,setSaving]=useState(false);
 async function submit(e:FormEvent<HTMLFormElement>){
  e.preventDefault();const form=new FormData(e.currentTarget);
  const data=Object.fromEntries(form);
  data.fee_pct=String(Number(data.fee_pct)/100);data.min_margin=String(Number(data.min_margin)/100);
  setSaving(true);try{await send('/api/assumptions',data)}finally{setSaving(false)}
 }
 return <section className="panel"><div className="section-title"><div><h2>費用與最低利潤</h2><p>依實際費用調整，儲存後重新計算本機比價與評分。</p></div></div><form onSubmit={submit} key={JSON.stringify(values)}><div className="form-grid">{([['fee_pct','平台／收款合計費率（%）'],['shipping','淨出貨運費（TWD）'],['packing','包材（TWD）'],['reserve','每件風險準備（TWD）'],['min_margin','最低淨利率（%）']] as const).map(([name,label])=>{const percentage=name==='fee_pct'||name==='min_margin';return <label className="field" key={name}><span>{label}</span><input name={name} type="number" required min="0" max={name==='fee_pct'?99.99:name==='min_margin'?100:undefined} step="0.01" defaultValue={percentage?Number((Number(values[name])*100).toFixed(2)):values[name]} disabled={locked||saving}/></label>})}</div><Button type="submit" className="btn primary" disabled={locked||saving}>{saving?'重新計算中…':'儲存並重新計算'}</Button></form><div className="panel-foot">這些是計算假設，請依實際帳單核對。Google Sheets 的 Inputs 可獨立調整，這裡儲存不會覆寫既有工作表設定。已建立草稿的售價不會自動改動。</div></section>
}
