import CollectionProgress, {type SourceQueueProgress} from '@/components/collection-progress';
import {latestCollectionJob} from '@/lib/collection-job';
import JobReport from '@/components/job-report';
export type CollectionSchedule={enabled:boolean;next_run:string;last_run:{at:string;status:string}|null;times:string[];timezone:string};
export type CollectionJob={id:number;name:string;status:string;started_at:string;detail:string|null};
const stamp=(v:string)=>{const d=new Date(v);return Number.isNaN(d.getTime())?'時間待確認':d.toLocaleString('zh-TW',{timeZone:'Asia/Taipei',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});};
const status:Record<string,string>={complete:'完成',success:'完成',partial:'部分失敗',failed:'失敗',started:'已開始',running:'執行中'};
export default function CollectionStatus({schedule,jobs,topics,active,queue}:{queue?:SourceQueueProgress;schedule?:CollectionSchedule;jobs:CollectionJob[];topics:{query:string}[];active:string|null}){
 const recent=latestCollectionJob(jobs);
 return <section className="panel" aria-label="自動收集狀態"><div className="section-title"><div><h2>自動更新</h2><p>每天 10:00、16:00、22:00（台灣時間），網站關閉後仍由伺服器執行。</p></div><span className={'badge '+(schedule?.enabled?'green':'amber')}>{schedule?.enabled?'排程已啟用':schedule?'排程未啟用':'排程狀態待取得'}</span></div><div className="panel-foot"><div><b>下次更新：{schedule?.enabled?stamp(schedule.next_run):'待恢復排程'}</b><p>{schedule?.last_run?`上次定時更新：${stamp(schedule.last_run.at)} · ${status[schedule.last_run.status]||'狀態待確認'}`:'尚無定時更新紀錄'}</p>{active&&<p role="status">正在執行：{active}</p>}<p>已保存收集主題：{topics.length?topics.map(t=>t.query).join('、'):'尚未設定，請在下方輸入商品並開始收集。'}</p><p>依保存主題分頁收集，不是全站所有商品。待反查超過 20 件時先處理既存商品；未配對商品留待後續重查。</p><CollectionProgress queue={queue}/>{recent&&<div><b>最近收集／比對：{stamp(recent.started_at)} · {status[recent.status]||'狀態待確認'}</b><JobReport detail={recent.detail}/></div>}</div></div></section>;
}
