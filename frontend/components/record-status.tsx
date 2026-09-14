import type {Comparison} from '@/components/comparison-table';
type ListingState='listed'|'unlisted'|'unknown';
export function recordListingStates(rows:Pick<Comparison,'release_id'|'listing_status'>[]){
 const states=new Map<number,ListingState>();
 for(const row of rows){
  const value:ListingState=row.listing_status==='listed'||row.listing_status==='unlisted'?row.listing_status:'unknown';
  const previous=states.get(row.release_id);
  states.set(row.release_id,previous==='listed'||value==='listed'?'listed':previous==='unknown'||value==='unknown'?'unknown':'unlisted');
 }
 return states;
}
const decisions:Record<string,string>={want:'要進貨',watch:'觀察中',skip:'已跳過'};
export default function RecordStatus({status='unknown',decision}:{status?:ListingState;decision?:string}){
 return <span className="record-state"><span className={'badge '+(status==='listed'?'green':status==='unknown'?'amber':'')}>{{listed:'已上架',unlisted:'未上架',unknown:'刊登狀態待確認'}[status]}</span>{decision&&decisions[decision]&&<small>{decisions[decision]}</small>}</span>;
}
export function matchesListingStatus(releaseId:number,states:Map<number,ListingState>,filter:string){
 return filter==='all'||(states.get(releaseId)||'unknown')===filter;
}
