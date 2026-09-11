import type {Comparison} from '@/components/comparison-table';
export function listedReleaseIds(rows:Pick<Comparison,'release_id'|'listing_status'>[]){
 return new Set(rows.filter(row=>row.listing_status==='listed').map(row=>row.release_id));
}
const decisions:Record<string,string>={want:'要進貨',watch:'觀察中',skip:'已跳過'};
export default function RecordStatus({listed,decision}:{listed:boolean;decision?:string}){
 return <span className="record-state"><span className={'badge '+(listed?'green':'')}>{listed?'已上架':'未上架'}</span>{decision&&decisions[decision]&&<small>{decisions[decision]}</small>}</span>;
}
