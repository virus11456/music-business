import {jobReport} from '@/lib/job-report';
export default function JobReport({detail}:{detail:string|null}){
 return <details><summary>查看處理明細</summary><ul>{jobReport(detail).map((line,i)=><li key={i}>{line}</li>)}</ul></details>;
}
