import type {DraftFilter as Filters} from '@/lib/draft-filter';
export default function DraftFilter({value,onChange,count,total,hiddenSelected}:{value:Filters;onChange:(value:Filters)=>void;count:number;total:number;hiddenSelected:number}){
 return <section className="panel-foot" aria-label="草稿篩選"><div className="form-grid">
 <label className="field"><span>搜尋草稿</span><input value={value.query} onChange={e=>onChange({...value,query:e.target.value})} placeholder="歌手、專輯、草稿或版本編號"/></label>
 <label className="field"><span>商品格式</span><select value={value.format} onChange={e=>onChange({...value,format:e.target.value})}>{[['all','全部格式'],['Vinyl','黑膠'],['CD','CD'],['Cassette','卡帶'],['other','其他／待確認']].map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
 <label className="field"><span>上架狀態</span><select value={value.listing||'all'} onChange={e=>onChange({...value,listing:e.target.value})}><option value="unlisted">未上架</option><option value="listed">已上架</option><option value="all">全部（含狀態待確認）</option></select></label>
 <label className="field"><span>草稿狀態</span><select value={value.status} onChange={e=>onChange({...value,status:e.target.value})}><option value="all">全部狀態</option><option value="ready">符合利潤與匯出條件</option><option value="attention">需要處理（含幣別不符）</option></select></label>
 <label className="field"><span>排列方式</span><select value={value.sort} onChange={e=>onChange({...value,sort:e.target.value})}><option value="newest">最新草稿優先</option><option value="profit">預估淨利由高到低</option></select></label>
 </div><p>顯示 {count} / {total} 件。預設只看未上架，已上架紀錄仍保留。調整篩選或排序會清除選取；批次選取只包含目前結果。</p>
 {hiddenSelected>0&&<p role="alert">資料更新後，有 {hiddenSelected} 件已選商品不在目前結果中。請清除選取或切回全部檢查。</p>}
 <button className="btn secondary" onClick={()=>onChange({query:'',format:'all',status:'all',sort:'newest',listing:'unlisted'})}>重設篩選</button></section>;
}
