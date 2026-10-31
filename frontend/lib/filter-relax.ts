// When a filtered list is empty, count what each active filter is hiding: the list size with that one filter
// lifted, and with every active filter lifted together.
export type Relaxation<F>={label:string;active:boolean;relax:(filters:F)=>F};
export function relaxedCounts<F>(filters:F,relaxations:Relaxation<F>[],count:(filters:F)=>number){
 const active=relaxations.filter(r=>r.active);
 return {each:active.map(r=>({label:r.label,count:count(r.relax(filters))})),
  all:active.length?count(active.reduce((f,r)=>r.relax(f),filters)):count(filters)};
}
