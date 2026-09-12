import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),cache={};
function load(name){if(cache[name])return cache[name];const out=cache[name]={};const source=readFileSync(new URL('../'+name,import.meta.url),'utf8');
 new Function('require','exports',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(id=>id.startsWith('@/')?load(id.slice(2)+'.ts'):id.startsWith('./')?load('lib/'+id.slice(2)+'.ts'):require(id),out);return out;}
const {parsePicks,purchaseRows,purchaseGroups,purchaseTotals,purchaseCsv}=load('lib/purchase-list.ts');
const now=Date.parse('2026-09-12T12:00:00Z'),stamp=new Date(now).toISOString();
const row={key:'candidate-1',release_id:1,source_url:'https://example.com/item/1',source_title:'Test album',format:'CD',source_format:'CD',version_confirmed:true,source_catalog_no:'ABC-1',catalog_no:'ABC 1',source_price:'500',source_currency:'TWD',has_market:true,want:20,market_price:'30',market_currency:'USD',source_at:stamp,market_at:stamp,cost_basis:'source_price',source_twd:'500',gross_twd:'400',gross_margin:0.44,availability:'來源標示有庫存',vendor:'ruten'};
const pick={key:row.key,release_id:1,source_url:row.source_url,title:row.source_title,seller:''};
test('saved selections validate shape, deduplicate and resolve only the same identity',()=>{
 assert.deepEqual(parsePicks('broken'),[]);assert.deepEqual(parsePicks('{}'),[]);
 assert.equal(parsePicks(JSON.stringify([pick,pick,{...pick,key:'bad',source_url:'javascript:alert(1)'}])).length,1);
 const [item]=purchaseRows([pick],[{...row,release_id:2}],now);assert.equal(item.row,undefined);assert.equal(item.issues.length,1);
});
test('latest stock, format, price and date determine totals; missing rows remain visible',()=>{
 assert.deepEqual(purchaseTotals(purchaseRows([pick],[row],now)),{count:1,cost:500,gross:400});
 for(const patch of [{availability:'售完'},{source_at:'2020-01-01T00:00:00Z'},{source_at:null},{source_at:'2099-01-01T00:00:00Z'},{gross_margin:-0.1},{source_format:'Vinyl'},{version_confirmed:false},{source_catalog_no:'OTHER-2'}]){
  const items=purchaseRows([pick],[{...row,...patch}],now);assert.ok(items[0].issues.length,JSON.stringify(patch));assert.equal(purchaseTotals(items).count,0);
 }
 const missing=purchaseRows([pick],[],now);assert.equal(missing.length,1);assert.equal(purchaseTotals(missing).count,0);
});
test('unknown sellers stay separate; explicit groups never cross platforms',()=>{
 const second={...pick,key:'2',source_url:'https://example.com/item/2'};
 const rows=[row,{...row,key:'2',source_url:second.source_url}];
 assert.equal(purchaseGroups(purchaseRows([pick,second],rows,now)).length,2);
 const grouped=[{...pick,seller:'A'},{...second,seller:'A'}];
 assert.equal(purchaseGroups(purchaseRows(grouped,rows,now)).length,1);
 assert.equal(purchaseGroups(purchaseRows(grouped,[row,{...rows[1],vendor:'tower'}],now)).length,2);
});
test('CSV keeps unresolved items and escapes formulas and quotes',()=>{
 const csv=purchaseCsv(purchaseRows([{...pick,title:'=cmd,"album"'}],[],now));
 assert.ok(csv.startsWith('\uFEFF'));assert.ok(csv.includes("'=cmd,"));assert.ok(csv.includes('""album""'));assert.ok(csv.includes('目前資料未找到'));
});
test('purchase panel shows issues, no automatic purchase, and review-only export',()=>{
 const View=load('components/purchase-list.tsx').default;
 const html=renderToStaticMarkup(React.createElement(View,{picks:[pick],rows:[],onChange:()=>{},storageError:''}));
 for(const text of ['採購清單','不會下單或上架','目前資料未找到','匯出採購審閱 CSV','不跨裝置同步'])assert.ok(html.includes(text),text);
});

test('same source matched to multiple releases is not counted as multiple available copies',()=>{
 const second={...pick,key:'2',release_id:2};
 const items=purchaseRows([pick,second],[row,{...row,key:'2',release_id:2}],now);
 assert.equal(purchaseTotals(items).count,0);assert.ok(items.every(i=>i.issues.some(x=>x.includes('多個版本'))));
});
