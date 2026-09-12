import type {Comparison} from '@/components/comparison-table';
export type Supply='stock'|'unknown'|'auction'|'unavailable';
type SupplyRow=Pick<Comparison,'availability'|'price_kind'>&Partial<Pick<Comparison,'source_title'>>;
export function sourceAvailability(row:SupplyRow):Supply{
 const value=(row.availability||'').normalize('NFKC').trim();
 const title=(row.source_title||'').normalize('NFKC');
 if(/待補貨|勿下[標单單]|已售[出完罄]|缺貨中|預購商品/.test(title))return 'unavailable';
 if(/取扱なし|お取り寄せ|予約|預購|缺貨|售完|售罄|無現貨|已售出|out of stock|sold out/i.test(value))return 'unavailable';
 if(row.price_kind==='current_bid'||/拍賣中|需確認結標/.test(value))return 'auction';
 if(['在庫あり','在庫わずか','來源標示有庫存'].includes(value))return 'stock';
 return 'unknown';
}
export const supplyLabels:Record<Supply,string>={stock:'來源標示現貨',unknown:'供貨待確認',auction:'拍賣未結標',unavailable:'缺貨／預購／待調貨'};
export function meetsSupply(row:SupplyRow,filter:string){
 const status=sourceAvailability(row);
 return filter==='all'||filter==='regular'&&(status==='stock'||status==='unknown')||status===filter;
}
