export type DraftFilter={query:string;format:string;status:string;sort:string;listing?:string};
type Row={listing_status?:string;id:number;release_id:number;artist:string;title:string;format:string;currency:string;export_issues?:string[];profit_review?:{ready:boolean;net_twd:string|null}};
export function formatMatches(value:string,format:string){
 const text=value.toUpperCase();
 const found=[/VINYL|\bLP\b|黑膠|アナログ/.test(text)?'Vinyl':'',/\bCD\b/.test(text)?'CD':'',/CASSETTE|卡帶|カセット/.test(text)?'Cassette':''].filter(Boolean);
 return format==='all'||(format==='other'?!found.length:found.includes(format));
}
export function filterDrafts<T extends Row>(rows:T[],filter:DraftFilter,currency:string):T[]{
 const query=filter.query.normalize('NFKC').toLocaleLowerCase().trim();
 return rows.filter(row=>{
  const ready=row.listing_status!=='listed'&&row.currency===currency&&row.export_issues?.length===0&&row.profit_review?.ready;
  return (!filter.listing||filter.listing==='all'||row.listing_status===filter.listing)&&formatMatches(row.format,filter.format)&&(!query||`${row.artist} ${row.title} ${row.id} ${row.release_id}`.normalize('NFKC').toLocaleLowerCase().includes(query))&&(filter.status==='all'||(filter.status==='ready'?ready:!ready));
 }).sort((a,b)=>{
  if(filter.sort==='profit'){
   const av=a.profit_review?.net_twd,bv=b.profit_review?.net_twd;
   const an=av==null?NaN:Number(av),bn=bv==null?NaN:Number(bv);
   if(Number.isFinite(an)!==Number.isFinite(bn))return Number.isFinite(an)?-1:1;
   if(Number.isFinite(an)&&an!==bn)return bn-an;
  }
  return b.id-a.id;
 });
}
