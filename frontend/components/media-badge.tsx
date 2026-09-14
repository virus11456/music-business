// Use only explicit format metadata; never infer media from product titles.
export function mediaLabels(value?:string|null){
 const text=(value||'').normalize('NFKC');
 const labels:string[]=[];
 if(/\bVinyl\b|\bLP\b|黑膠|アナログ/i.test(text))labels.push('黑膠');
 if(/\bCD\b/i.test(text))labels.push('CD');
 if(/\bCassette\b|卡帶|カセット/i.test(text))labels.push('卡帶');
 return labels.length?labels:['格式待確認'];
}
export default function MediaBadge({format}:{format?:string|null}){
 return <span className="media-tags" aria-label="商品格式">{mediaLabels(format).map(label=><span key={label} className={'badge media-type '+({'黑膠':'media-vinyl','CD':'media-cd','卡帶':'media-cassette'}[label]||'media-unknown')}>{label}</span>)}</span>;
}
