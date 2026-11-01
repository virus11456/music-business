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
// Auction end written as 拍賣中／MM/DD HH:MM 結標 (Taipei time). The year is the one that puts it nearest to now.
export function auctionEnd(row:Pick<Comparison,'availability'>,now=new Date()):Date|null{
 const m=/(\d{2})\/(\d{2}) (\d{2}):(\d{2}) 結標/.exec(row.availability||'');if(!m)return null;
 const year=Number(new Intl.DateTimeFormat('en',{timeZone:'Asia/Taipei',year:'numeric'}).format(now));
 const at=(y:number)=>new Date(`${y}-${m[1]}-${m[2]}T${m[3]}:${m[4]}:00+08:00`);
 const candidates=[at(year-1),at(year),at(year+1)].filter(d=>!Number.isNaN(d.getTime()));
 return candidates.sort((a,b)=>Math.abs(a.getTime()-now.getTime())-Math.abs(b.getTime()-now.getTime()))[0]??null;
}
// Auctions that end within the next 24 hours: a low current bid there is the closest thing to a buyable price.
export function endingSoon(row:SupplyRow,now=new Date()){
 if(sourceAvailability(row)!=='auction')return false;
 const end=auctionEnd(row,now);if(!end)return false;
 const left=end.getTime()-now.getTime();return left>0&&left<=24*3600*1000;
}
export function meetsSupply(row:SupplyRow,filter:string,now=new Date()){
 if(filter==='ending')return endingSoon(row,now);
 const status=sourceAvailability(row);
 return filter==='all'||filter==='regular'&&(status==='stock'||status==='unknown')||status===filter;
}
