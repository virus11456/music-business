type Job={id:number;name:string;detail:string|null};
export function latestCollectionJob<T extends Job>(jobs:T[]):T|undefined {
 return jobs.filter(j=>{
  // Failed jobs can have only an exception name, or no detail while running.
  if(j.name==='先找貨 → 反查需求 → 比價同步'||j.name.startsWith('定時更新：'))return true;
  try {const d=JSON.parse(j.detail||'null');return d?.flow==='source_first'||typeof d?.scheduled_slot==='string';}
  catch {return false;}
 }).reduce<T|undefined>((latest,j)=>!latest||j.id>latest.id?j:latest,undefined);
}
