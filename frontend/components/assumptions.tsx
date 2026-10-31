'use client';
import {useState,type FormEvent} from 'react';
import {Button} from '@/components/ui/button';
export type Assumptions={fee_pct:string;payment_pct?:string;payment_fixed?:string;conversion_pct?:string;tax_pct?:string;buyer_shipping?:string;shipping:string;packing:string;reserve:string;min_margin:string};
type Field=keyof Assumptions;
// Percent fields are shown as % and sent as fractions; max is the upper bound of each percent input.
const FIELDS:[Field,string,number?][]=[
 ['fee_pct','Discogs 手續費率（%，含運費部分）',99.99],
 ['payment_pct','PayPal 收款費率（%，含運費與稅）',99.99],
 ['payment_fixed','PayPal 每筆固定費（TWD）'],
 ['conversion_pct','美元提領換匯費率（%）',99.99],
 ['tax_pct','買家稅率估計（%）',100],
 ['buyer_shipping','向買家收取運費（換算 TWD）'],
 ['shipping','實際郵資（TWD）'],
 ['packing','包材（TWD）'],
 ['reserve','每件風險準備（TWD）'],
 ['min_margin','最低淨利率（%）',100],
];
const PERCENT=new Set<Field>(FIELDS.filter(f=>f[2]!==undefined).map(f=>f[0]));
export default function AssumptionsForm({values,locked,send}:{values:Assumptions;locked:boolean;send:(path:string,data:object)=>Promise<boolean>}){
 const [saving,setSaving]=useState(false);
 async function submit(e:FormEvent<HTMLFormElement>){
  e.preventDefault();const data:Record<string,string>={};
  new FormData(e.currentTarget).forEach((value,key)=>{const text=typeof value==='string'?value:'';data[key]=PERCENT.has(key as Field)?String(Number(text)/100):text});
  setSaving(true);try{await send('/api/assumptions',data)}finally{setSaving(false)}
 }
 return <section className="panel"><div className="section-title"><div><h2>費用與最低利潤</h2><p>依實際費用調整，儲存後重新計算本機比價與評分。</p></div></div><form onSubmit={submit} key={JSON.stringify(values)}><div className="form-grid">{FIELDS.map(([name,label,max])=>{const value=values[name]??'0';return <label className="field" key={name}><span>{label}</span><input name={name} type="number" required min="0" max={max} step="0.01" defaultValue={PERCENT.has(name)?Number((Number(value)*100).toFixed(2)):value} disabled={locked||saving}/></label>})}</div><Button type="submit" className="btn primary" disabled={locked||saving}>{saving?'重新計算中…':'儲存並重新計算'}</Button></form><div className="panel-foot">依 2026-11 三筆實際 Discogs／PayPal 帳單核對：Discogs 9% 收在商品＋買家運費；PayPal 4.4% 收在商品＋運費＋稅，另加每筆 US$0.30（約 NT$10）；美元提領至台灣銀行另收 2.5% 換匯。稅金由 Discogs 代收代繳，不算收入；美國買家約 8%、歐盟 VAT 20–27%。向買家收取的運費會抵銷實際郵資。這些是計算假設，請依實際帳單核對。Google Sheets 的 Inputs 可獨立調整，這裡儲存不會覆寫既有工作表設定。已建立草稿的售價不會自動改動。</div></section>
}
