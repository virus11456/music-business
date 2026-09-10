export type ProfitReview={sale_twd:string|null;cost_twd:string|null;gross_twd:string|null;fees_twd:string|null;net_twd:string|null;net_margin:number|null;ready:boolean;issues:string[]};
const amount=(value:string|null)=>value===null?'待補資料':`NT$ ${Number(value).toLocaleString('zh-TW',{maximumFractionDigits:2})}`;
export default function DraftProfit({review}:{review?:ProfitReview}){
 if(!review)return <p>利潤檢查尚未取得，請更新本機服務。</p>;
 return <section aria-label="草稿利潤檢查"><h4>依目前草稿售價估算</h4><div className="assumptions">
  <div><span>售價換算</span><b>{amount(review.sale_twd)}</b></div>
  <div><span>含運進貨成本</span><b>{amount(review.cost_twd)}</b></div>
  <div><span>毛利</span><b>{amount(review.gross_twd)}</b></div>
  <div><span>預估費用</span><b>{amount(review.fees_twd)}</b></div>
  <div><span>預估淨利</span><b>{amount(review.net_twd)}</b></div>
  <div><span>淨利率</span><b>{review.net_margin===null?'待補資料':`${(review.net_margin*100).toFixed(1)}%`}</b></div>
 </div><p>{review.ready?'目前資料符合設定的利潤門檻，尚未刊登':'利潤或資料待確認'}</p>
 {review.issues.map(issue=><p key={issue}>待辦：{issue}</p>)}
 <small>依最新報價、有效匯率與本機費用設定估算，不是成交保證。此檢查供決策參考；匯出檔案仍依基本資料與供貨檢查判定。</small></section>;
}
