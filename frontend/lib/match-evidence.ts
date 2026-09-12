import type {Comparison} from '@/components/comparison-table';
const normalize=(value:string)=>value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
const catalog=(value:string)=>{const normalized=normalize(value);return ['','none','na','未確認','unknown'].includes(normalized)?'':normalized};
type MatchRow=Pick<Comparison,'version_confirmed'|'format'|'source_format'|'source_catalog_no'|'catalog_no'|'source_catalog_from_title'|'barcodes'|'source_barcodes'>;
export function matchConflicts(row:MatchRow):string[]{
 const conflicts:string[]=[];
 if(row.barcodes?.length&&row.source_barcodes?.length&&!row.source_barcodes.some(code=>row.barcodes!.includes(code)))conflicts.push('條碼衝突');
 if(row.format&&row.source_format&&row.format!==row.source_format)conflicts.push('商品格式衝突');
 const source=catalog(row.source_catalog_no||''),targets=(row.catalog_no||'').split(',').map(catalog).filter(Boolean);
 if(source&&targets.length&&!targets.includes(source))conflicts.push('唱片編號衝突');
 return conflicts;
}
export function matchLevel(row:MatchRow):'confirmed'|'catalog'|'candidate'{
 if(matchConflicts(row).length)return 'candidate';
 if(row.version_confirmed&&row.format&&row.format===row.source_format)return 'confirmed';
 const source=catalog(row.source_catalog_no||'');
 if(row.format&&row.format===row.source_format&&source&&!row.source_catalog_from_title&&(row.catalog_no||'').split(',').some(value=>catalog(value)===source))return 'catalog';
 return 'candidate';
}
export function hasStrongMatch(row:Parameters<typeof matchLevel>[0]){return matchLevel(row)!=='candidate'}
export function matchLabel(row:Parameters<typeof matchLevel>[0]){
 const conflicts=matchConflicts(row);if(conflicts.length)return conflicts.join(' · ')+'，需重新核對';
 if(!row.version_confirmed&&row.barcodes?.length&&row.source_barcodes?.some(code=>row.barcodes!.includes(code)))return '有效條碼一致 · 壓片仍待核對';
 if(row.source_catalog_from_title&&!row.version_confirmed)return '編號取自標題，僅為線索，版本待核對';
 return {confirmed:'已人工核對版本',catalog:'唱片編號一致 · 壓片待核對',candidate:'可能配對：同名／同格式，版本待核對'}[matchLevel(row)];
}
