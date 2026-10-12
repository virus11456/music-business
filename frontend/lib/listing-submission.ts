export type Submission={draft_id:number;release_id:number;artist?:string;title?:string;price?:string;currency?:string;status:string;listing_id:number|null;reason:string|null;requested_status:string;started_at:string;finished_at:string|null;attempts?:number};
export type SubmissionState={enabled:boolean;counts:Record<string,number>;rows:Submission[];limit:number};
export const SUBMISSION_LABELS:Record<string,string>={submitting:'送出中／結果待確認',listed:'Discogs 已建立',failed:'未建立，可修正後重送',uncertain:'結果不明，請核對'};
export function submissionLabel(status:unknown){
 return typeof status==='string'&&status in SUBMISSION_LABELS?SUBMISSION_LABELS[status]:'狀態待確認';
}
export function needsReview(row:{status:string;started_at?:string},now=Date.now()){
 if(row.status==='uncertain')return true;
 if(row.status!=='submitting')return false;
 const started=Date.parse(row.started_at||'');
 return Number.isNaN(started)||now-started>10*60*1000;
}
export function canSubmit(input:{enabled:boolean;selected:number;blocked:number;hidden:number;locked:boolean;open:number}){
 return input.enabled&&!input.locked&&input.selected>0&&input.selected<=50&&input.blocked===0&&input.hidden===0&&input.open===0;
}
export function openCount(rows:Submission[]|undefined){
 return (rows||[]).filter(r=>r.status==='submitting'||r.status==='uncertain').length;
}
export function listingUrl(listingId:number|null){
 return typeof listingId==='number'&&Number.isInteger(listingId)&&listingId>0?`https://www.discogs.com/sell/item/${listingId}`:null;
}
