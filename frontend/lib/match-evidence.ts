import type {Comparison} from '@/components/comparison-table';
const normalize=(value:string)=>value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
const catalog=(value:string)=>{const normalized=normalize(value);return ['','none','na','未確認','unknown'].includes(normalized)?'':normalized};
export function matchLevel(row:Pick<Comparison,'version_confirmed'|'format'|'source_format'|'source_catalog_no'|'catalog_no'>):'confirmed'|'catalog'|'candidate'{
 if(row.version_confirmed)return 'confirmed';
 const source=catalog(row.source_catalog_no||'');
 if(row.format&&row.format===row.source_format&&source&&(row.catalog_no||'').split(',').some(value=>catalog(value)===source))return 'catalog';
 return 'candidate';
}
export function hasStrongMatch(row:Parameters<typeof matchLevel>[0]){return matchLevel(row)!=='candidate'}
export function matchLabel(row:Parameters<typeof matchLevel>[0]){
 return {confirmed:'已人工核對版本',catalog:'唱片編號一致 · 壓片待核對',candidate:'可能配對：同名／同格式，版本待核對'}[matchLevel(row)];
}
