type Obj=Record<string,unknown>;
const obj=(v:unknown):Obj=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Obj:{};
const list=(v:unknown):unknown[]=>Array.isArray(v)?v:[];
const count=(v:unknown)=>typeof v==='number'&&Number.isInteger(v)&&v>=0?v:null;
export function refreshFailures(detail:string|null):{label:string;url:string}[]{
 let data:Obj;try{data=obj(JSON.parse(detail||'{}'))}catch{return []}
 const results:{label:string;url:string}[]=[];
 const platforms:Record<string,[string,string]>={tower:['Tower','https://tower.jp/item/'],yahoo_tw:['Yahoo 台灣','https://tw.bid.yahoo.com/item/'],yahoo_jp:['Yahoo 日本','https://auctions.yahoo.co.jp/jp/auction/'],ruten:['露天','https://www.ruten.com.tw/item/']};
 const reasons:Record<string,string>={title_changed:'名稱／版本標記不同，待核對',format_changed:'商品格式不同，待核對',unknown_state:'商品狀態未能識別',page_structure:'商品頁結構未能識別',product_structure:'商品資料缺失或不唯一',wrong_product:'回傳商品編號不符',invalid_id:'商品編號無效',currency:'價格幣別不符',missing_price_or_title:'缺少有效價格或名稱',auction_time:'拍賣時間未能識別',timeout:'連線逾時',connection:'連線失敗',invalid_json:'商品資料格式無效',missing_field:'缺少必要商品欄位',not_returned:'來源未回傳此商品',unclassified:'尚未分類的更新錯誤'};
 for(const batch of Array.isArray(data.batches)?data.batches:[data]){
  const q=obj(obj(batch).source_refresh);
  for(const raw of Array.isArray(q.platforms)?q.platforms:[q]){
   const part=obj(raw),platform=String(part.platform),source=platforms[platform];if(!source)continue;
   for(const rawFailure of list(part.failures).slice(0,40)){
    const f=obj(rawFailure),id=String(f.external_id??''),code=String(f.reason??'');
    if(!(platform==='yahoo_jp'?/^[a-zA-Z0-9]{1,40}$/:/^\d{1,40}$/).test(id))continue;
    const reason=reasons[code]??(/^http_[1-5]\d{2}$/.test(code)?`來源回應 HTTP ${code.slice(5)}`:'尚未分類的更新錯誤');
    results.push({label:`${source[0]} #${id}：${reason}（舊資料未更新）`,url:source[1]+id});
   }
  }
 }
 return results;
}
export function jobReport(detail:string|null):string[]{
 let data:Obj;try{data=obj(JSON.parse(detail||'{}'))}catch{return ['未保存步驟明細；請檢查連線與設定後重試。']}
 const lines:string[]=[];
 const names:Record<string,string>={yahoo_tw:'Yahoo 台灣',yahoo_jp:'Yahoo 日本',ruten:'露天',tower:'Tower'};
 function source(value:unknown,prefix=''){
  const s=obj(value);
  for(const raw of list(s.platforms)){
   const p=obj(raw),name=names[String(p.platform)];if(!name)continue;
   const n=count(p.count);
   if(count(p.page)!==null)lines.push(prefix+name+`：第 ${p.page} 頁${count(p.total_pages)!==null?`／共 ${p.total_pages} 頁`:''}`);
   lines.push(prefix+name+'：'+(p.status==='success'?`取得 ${n??'未知'} 件候選`:p.status==='empty'?'沒有搜尋結果（不代表平台沒有庫存）':'未完成，請至進貨頁檢查平台紀錄或人工查找'));
  }
  if(count(s.possible_matches)!==null)lines.push(prefix+`可能配對 ${s.possible_matches} 件，仍需核對版本`);
  if(!list(s.platforms).length&&count(s.failed_platforms)!==null)lines.push(prefix+`平台失敗 ${s.failed_platforms} 個；舊紀錄未保存各平台明細`);
 }
 function batch(value:unknown){
  const b=obj(value);
  const quotes=obj(b.source_refresh);
  const quoteParts=list(quotes.platforms).length?list(quotes.platforms):quotes.platform==='ruten'?[quotes]:[];
  for(const raw of quoteParts){
   const q=obj(raw),name=names[String(q.platform)];if(!name)continue;
   lines.push(`${name}已存報價：檢查 ${count(q.attempted)??0} 件 · 更新 ${count(q.updated)??0} 件 · 未回傳 ${count(q.missing)??0} 件 · 失敗 ${count(q.failed)??0} 件`);
  }
  if(b.flow==='source_first'){
   source(b.collection);
   lines.push(`反查 ${count(b.checked)??0} 件 · 有配對 ${count(b.matched)??0} 件 · 留待配對 ${count(b.unmatched)??0} 件 · 沿用快取 ${count(b.cached)??0} 件 · 待處理 ${count(b.pending)??0} 件`);
  }
  for(const raw of list(b.releases)){
   const r=obj(raw),id=count(r.release_id);if(id===null)continue;
   const prefix=`版本 #${id} · `;
   lines.push(prefix+'Discogs 行情：'+(r.market==='完成'?'完成':'未完成，請重新更新行情'));
   source(r.sourcing,prefix);
  }
  for(const raw of list(b.errors)){
   const e=obj(raw),id=count(e.release_id);
   const steps:Record<string,string>={market:'Discogs 行情',sourcing:'找貨',sheets:'Google Sheets 同步',fx:'參考匯率',reverse_match:'反查版本',source_refresh:'貨源報價刷新'};
   if(steps[String(e.step)])lines.push(`${id===null?'':`版本 #${id} · `}${steps[String(e.step)]}未完成；請檢查該服務的連線與設定後重試`);
  }
  if(obj(b.sheet_sync).synced===true)lines.push('Google Sheets 同步完成');
 }
 if(data.collection_paused===true)lines.push(`先處理已存商品（待反查 ${count(data.pending_before)??'未知'} 件），本輪不新增收集`);
 if(count(data.versions)!==null)lines.push(`本次排程涵蓋 ${data.versions} 個版本`);
 if(Array.isArray(data.batches))for(const b of data.batches)batch(b);else batch(data);
 source(data);
 if(data.synced===true)lines.push(`Google Sheets 同步完成：行情 ${count(data.market_rows)??'未知'} 列、報價 ${count(data.source_rows)??'未知'} 列`);
 return lines.length?lines:['此工作未保存可顯示的步驟明細。'];
}
