export type SourceQueueProgress={total:number;unchecked:number;pending?:number;statuses:Record<string,number>};
export default function CollectionProgress({queue}:{queue?:SourceQueueProgress}){
 if(!queue)return <p>收集進度尚未取得。</p>;
 const valid=(n:unknown):n is number=>typeof n==='number'&&Number.isSafeInteger(n)&&n>=0;
 const total=queue.total,remaining=queue.unchecked;
 if(!valid(total)||!valid(remaining)||remaining>total)return <p>收集進度資料待重新讀取。</p>;
 const checked=total-remaining,percent=total?Math.round(checked/total*100):0;
 const pending=queue.pending,hasPending=valid(pending)&&pending>=remaining&&pending<=total;
 const count=(name:string)=>queue.statuses?.[name]===undefined?0:valid(queue.statuses[name])?queue.statuses[name]:'待取得';
 return <div className="collection-progress" aria-label="貨源比對進度"><p><b>已收集 {total.toLocaleString()} 件 · 已完成首次反查 {checked.toLocaleString()} 件</b></p><progress max={total||1} value={checked} aria-label="首次反查完成進度"/><p>首次反查進度 {percent}% · 尚未首次反查 {remaining.toLocaleString()} 件</p><p>有候選匹配 {count('matched')} 件 · 暫未匹配 {count('unmatched')} 件 · 查詢失敗 {queue.statuses?.failed===undefined?0:count('failed')} 件</p>{hasPending?<p>目前待反查 {pending.toLocaleString()} 件（首次 {remaining.toLocaleString()} 件 · 到期或身份變更重查 {(pending-remaining).toLocaleString()} 件）</p>:<p>目前待反查總數待取得；首次進度不包含到期或身份變更重查。</p>}<small>每批最多 20 件。首次反查完成包含未配對及失敗紀錄；失敗、到期或商品身份變更仍可能再查。有候選匹配不等於版本已確認或有正毛利。</small></div>;
}
