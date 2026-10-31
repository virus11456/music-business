type Obj=Record<string,unknown>;
const obj=(v:unknown):Obj=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Obj:{};
const list=(v:unknown):unknown[]=>Array.isArray(v)?v:[];
const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0?v:null;
export function refreshFailures(detail:string|null):{label:string;url:string}[]{
 let data:Obj;try{data=obj(JSON.parse(detail||'{}'))}catch{return []}
 const results:{label:string;url:string}[]=[];
 const platforms:Record<string,[string,string]>={rottenblues:['Rotten Blues',''],tower:['Tower','https://tower.jp/item/'],yahoo_tw:['Yahoo 台灣','https://tw.bid.yahoo.com/item/'],yahoo_jp:['Yahoo 日本','https://auctions.yahoo.co.jp/jp/auction/'],ruten:['露天','https://www.ruten.com.tw/item/']};
 const reasons:Record<string,string>={title_changed:'名稱／版本標記不同，待核對',format_changed:'商品格式不同，待核對',unknown_state:'商品狀態未能識別',page_structure:'商品頁結構未能識別',product_structure:'商品資料缺失或不唯一',wrong_product:'回傳商品編號不符',invalid_id:'商品編號無效',currency:'價格幣別不符',missing_price_or_title:'缺少有效價格或名稱',auction_time:'拍賣時間未能識別',timeout:'連線逾時',connection:'連線失敗',invalid_json:'商品資料格式無效',missing_field:'缺少必要商品欄位',not_returned:'來源未回傳此商品',unclassified:'尚未分類的更新錯誤'};
 for(const batch of Array.isArray(data.batches)?data.batches:[data]){
  const q=obj(obj(batch).source_refresh);
  for(const raw of Array.isArray(q.platforms)?q.platforms:[q]){
   const part=obj(raw),platform=String(part.platform),source=platforms[platform];if(!source)continue;
   for(const rawFailure of list(part.failures).slice(0,40)){
    const f=obj(rawFailure),id=String(f.external_id??''),code=String(f.reason??'');
    if(!(platform==='yahoo_jp'?/^[a-zA-Z0-9]{1,40}$/:/^\d{1,40}$/).test(id))continue;
    const reason=reasons[code]??(/^http_[1-5]\d{2}$/.test(code)?`來源回應 HTTP ${code.slice(5)}`:'尚未分類的更新錯誤');
    let url=source[1]+id;
    if(platform==='rottenblues'){try{const u=new URL(String(f.source_url));if(u.origin!=='https://www.rottenblues.com'||!/^\/products\/[^/]+$/.test(u.pathname)||u.searchParams.get('variant')!==id)continue;url=u.href}catch{continue}}
    results.push({label:`${source[0]} #${id}：${reason}（舊資料未更新）`,url});
   }
  }
 }
 return results;
}
export function jobReport(detail:string|null):string[]{
 let data:Obj;try{data=obj(JSON.parse(detail||'{}'))}catch{return ['未保存可讀的步驟明細；請先確認工作狀態與 Sheet 結果，勿直接重送。']}
 const lines:string[]=[];
 function verification(value:Obj){if(Array.isArray(value.changed_tables)&&Array.isArray(value.unchanged_tables))lines.push(`本次寫入 ${value.changed_tables.length} 個分頁，${value.unchanged_tables.length} 個分頁資料未變、略過重寫`);const v=obj(value.verification);if(v.ok===true)lines.push(`Sheet 寫入後核對通過：${count(v.tables)??'未知'} 個分頁，價格與比對資料已讀回確認`);}
 const names:Record<string,string>={yahoo_tw:'Yahoo 台灣',yahoo_jp:'Yahoo 日本',ruten:'露天',tower:'Tower',rottenblues:'Rotten Blues 爛調唱片',rakuten:'樂天市場',ebay:'eBay'};
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
   if(count(obj(q.selection).rotation)!==null)lines.push(`${name}刷新排序：優先商品 ${count(obj(q.selection).priority)??'未知'} 件 · 舊資料保留名額 ${count(obj(q.selection).rotation)??'未知'} 件`);
   lines.push(`${name}已存報價：檢查 ${count(q.attempted)??'未知'} 件 · 更新 ${count(q.updated)??'未知'} 件 · 未回傳 ${count(q.missing)??'未知'} 件 · 失敗 ${count(q.failed)??'未知'} 件`);
  }
  if(b.flow==='source_first'){
   if(names[String(b.source_platform)])lines.push('指定比對來源：'+names[String(b.source_platform)]);
   source(b.collection);
   lines.push(`反查 ${count(b.checked)??'未知'} 件 · 有版本候選 ${count(b.matched)??'未知'} 件 · 留待配對 ${count(b.unmatched)??'未知'} 件 · 沿用快取 ${count(b.cached)??'未知'} 件 · 待處理 ${count(b.pending)??'未知'} 件`);
  }
  if(b.flow==='demand_night'){
   const scan=obj(b.scan),demand=obj(b.demand);
   lines.push(`Discogs 稀缺掃描：新增 ${count(scan.discovered)??'未知'} 個版本 · 用掉 ${count(scan.requests)??'未知'} 次請求 · 搜尋結果先篩掉 ${count(scan.prefiltered)??'未知'} 筆${scan.budget_exhausted===true?' · 已達今晚上限，下次接續':''}`);
   lines.push(`依稀缺名單找貨：搜尋 ${count(demand.albums)??'未知'} 張專輯（${count(demand.versions)??'未知'} 個版本，合格 ${count(demand.eligible_albums)??'未知'} 張，7 天內已搜略過 ${count(demand.skipped_recent)??'未知'} 張） · 取得 ${count(demand.candidates)??'未知'} 件候選 · 可能配對 ${count(demand.linked)??'未知'} 組，仍需核對版本`);
   if(count(demand.failed_platforms))lines.push(`找貨時有 ${demand.failed_platforms} 次平台未完成，請至進貨頁檢查平台紀錄`);
   for(const raw of list(demand.errors))lines.push(`找貨未完成：${String(obj(raw).album||'').slice(0,80)}`);
  }
  if(count(b.market_updated)!==null)lines.push(`本輪更新 Discogs 行情 ${b.market_updated} 個版本（最低掛牌價，非成交價）`);
  for(const raw of list(b.releases)){
   const r=obj(raw),id=count(r.release_id);if(id===null)continue;
   const prefix=`版本 #${id} · `;
   lines.push(prefix+'Discogs 行情：'+(r.market==='完成'?'完成':'未完成，請重新更新行情'));
   source(r.sourcing,prefix);
  }
  for(const raw of list(b.errors)){
   const e=obj(raw),id=count(e.release_id);
   const steps:Record<string,string>={market:'Discogs 行情',sourcing:'找貨',sheets:'Google Sheets 同步',fx:'參考匯率',reverse_match:'反查版本',source_refresh:'貨源報價刷新'};
   const syncCodes:Record<string,string>={comparison_invalid:'比對資料檢查未通過；請檢查格式、版本編號與毛利',read_failed:'無法讀取工作表；請檢查連線、分享權限與服務狀態',write_rejected:'Google 拒絕寫入；請檢查分享權限、配額及工作表設定',write_unknown:'寫入結果尚未確認；請先查看 Sheet，勿連續重送',readback_failed:'已送出寫入，但無法讀回核對；尚未確認同步成功',readback_mismatch:'寫入後讀回不一致；請檢查下列分頁是否遭同時修改',ownership_conflict:'同名分頁非系統管理，已停止覆寫'};
   if(e.step==='sheets' && syncCodes[String(e.code)]){
    const allowed=['Comparisons','PlatformCandidates','Discogs','Sources','Inputs','Analysis'];
    const tabs=list(e.tables).filter(t=>typeof t==='string'&&allowed.includes(t));
    lines.push('Google Sheets：'+syncCodes[String(e.code)]+(tabs.length?'（'+tabs.map(t=>'SIMPLES_'+t).join('、')+'）':''));continue;
   }
   if(e.step==='sheets'){lines.push('Google Sheets 同步未完成；舊紀錄未保存可判定的寫入結果，請先讀回 Sheet，勿直接重送');continue;}
   if(steps[String(e.step)])lines.push(`${id===null?'':`版本 #${id} · `}${steps[String(e.step)]}未完成；請檢查該服務的連線與設定後重試`);
  }
  if(obj(b.sheet_sync).synced===true)lines.push('Google Sheets 同步完成');
  verification(obj(b.sheet_sync));
 }
 if(data.collection_paused===true)lines.push(`先處理已存商品（待反查 ${count(data.pending_before)??'未知'} 件），本輪不新增收集`);
 if(count(data.versions)!==null)lines.push(`排程開始時已存 ${data.versions} 個版本（本輪分批更新）`);
 if(Array.isArray(data.batches))for(const b of data.batches)batch(b);else batch(data);
 source(data);
 verification(data);
 if(data.synced===true)lines.push(`Google Sheets 同步完成：行情 ${count(data.market_rows)??'未知'} 列、報價 ${count(data.source_rows)??'未知'} 列`);
 return lines.length?lines:['此工作未保存可顯示的步驟明細。'];
}
