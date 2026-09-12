import {jobReport,refreshFailures} from '@/lib/job-report';
export default function JobReport({detail}:{detail:string|null}){
 return <details><summary>查看處理明細</summary><ul>{jobReport(detail).map((line,i)=><li key={i}>{line}</li>)}</ul>{refreshFailures(detail).length>0&&<><p>未更新的商品</p><ul>{refreshFailures(detail).map((failure,i)=><li key={i}><a href={failure.url} target="_blank" rel="noopener noreferrer">{failure.label} ↗</a></li>)}</ul></>}</details>;
}
