export function listingState(value:unknown):'listed'|'unlisted'|'unknown'{
 return value==='listed'||value==='unlisted'?value:'unknown';
}
export function listingLabel(value:unknown){
 return {listed:'已上架',unlisted:'未上架',unknown:'刊登狀態待確認'}[listingState(value)];
}
export function matchesListing(value:unknown,filter:string){
 return filter==='all'||listingState(value)===filter;
}
