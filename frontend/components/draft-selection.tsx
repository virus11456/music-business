import {draftSelection,type ExportDraft} from '@/lib/draft-selection';
export default function DraftSelection({drafts,ids,currency,locked,onSelect,onCurrency}:{drafts:ExportDraft[];ids:number[];currency:string;locked:boolean;onSelect:(ids:number[])=>void;onCurrency:(currency:string)=>void}){
 const state=draftSelection(drafts,ids,currency);
 return <section className="panel-foot" aria-label="批次匯出檢查"><h3>批次匯出檢查</h3>
 <label className="field"><span>Discogs 賣家設定的幣別（請核對）</span><select disabled={locked} value={currency} onChange={e=>onCurrency(e.target.value)}>{['USD','JPY','TWD','EUR','GBP'].map(cc=><option key={cc}>{cc}</option>)}</select></label>
 <p>切換幣別會清除選取，不會換算或修改草稿售價。</p>
 <button className="btn secondary" disabled={locked||!state.eligible.length} onClick={()=>onSelect(state.eligible.slice(0,500))}>選取符合利潤與匯出條件的商品（{Math.min(state.eligible.length,500)} 件）</button>
 <button className="btn secondary" disabled={locked||!ids.length} onClick={()=>onSelect([])}>清除選取</button>
 <p aria-live="polite">已選 {state.selected.length} 件 · 匯出需處理 {state.blocked.length} 件 · 利潤待確認 {state.warnings.length} 件</p>
 {state.selected.length>500&&<p role="alert">每批最多 500 件，請減少選取。</p>}
 {state.blocked.map(row=><p key={row.id}>草稿 #{row.id}：{row.issues.join('；')}</p>)}
 {state.warnings.length>0&&<p>草稿 {state.warnings.map(id=>`#${id}`).join('、')} 的利潤或資料待確認，請查看下方各商品明細。手動選取仍可依基本匯出條件下載。</p>}
 </section>;
}
