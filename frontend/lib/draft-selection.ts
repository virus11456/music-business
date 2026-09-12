export type ExportDraft={listing_status?:string;id:number;currency:string;export_issues?:string[];profit_review?:{ready:boolean}};
export function exportIssues(draft:ExportDraft,currency:string):string[]{
 return [...new Set([...(draft.listing_status==='listed'?['此貨源版本已登錄上架，避免重複匯出']:[]),...(draft.export_issues??['尚未取得匯出檢查']),...(draft.currency===currency?[]:['幣別與賣家設定不同'])])];
}
export function draftSelection(drafts:ExportDraft[],ids:number[],currency:string){
 const byId=new Map(drafts.map(d=>[d.id,d]));
 const selected=[...new Set(ids)];
 const blocked=selected.flatMap(id=>{const d=byId.get(id);const issues=d?exportIssues(d,currency):['草稿不存在，請清除選取'];return issues.length?[{id,issues}]:[]});
 const warnings=selected.filter(id=>{const d=byId.get(id);return d&&!d.profit_review?.ready});
 const eligible=drafts.filter(d=>!exportIssues(d,currency).length&&d.profit_review?.ready).map(d=>d.id);
 return {selected,blocked,warnings,eligible,canExport:selected.length>0&&selected.length<=500&&!blocked.length};
}
