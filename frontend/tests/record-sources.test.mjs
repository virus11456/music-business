import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const source=await readFile(new URL('../components/record-sources.tsx',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const supplySource=await readFile(new URL('../lib/source-availability.ts',import.meta.url),'utf8');
const supply={};new Function('exports',ts.transpileModule(supplySource,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(supply);
const prices={};new Function('exports',ts.transpileModule(await readFile(new URL('../lib/comparison-sort.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(prices);
const evidence={};new Function('exports',ts.transpileModule(await readFile(new URL('../lib/match-evidence.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(evidence);
const exports={};new Function('require','exports',js)(id=>id==='@/lib/source-availability'?supply:id==='@/lib/comparison-sort'?prices:id==='@/lib/match-evidence'?evidence:createRequire(import.meta.url)(id),exports);
const row={source_url:'https://www.ruten.com.tw/item/show?123',vendor:'ruten',source_title:'Album A',source_price:'350',source_currency:'TWD',price_kind:'listed',gross_twd:'120',availability:'來源標示有庫存'};
const render=rows=>renderToStaticMarkup(React.createElement(exports.default,{rows}));
test('record source cards show actual quote, destination and candidate status',()=>{
 const html=render([row]);for(const text of ['露天市集','Album A','TWD 350','NT$ 120','可能配對','href="'+row.source_url+'"'])assert.ok(html.includes(text));
 assert.ok(!html.includes('<button'));
});
test('excluded and duplicate sources do not inflate listings and invalid links cannot execute',()=>{
 const html=render([row,row,{...row,source_url:'https://example.com/excluded',excluded:true}]);assert.ok(html.includes('對應進貨賣場 · 1 件'));
 const invalid=render([{...row,source_url:'javascript:alert(1)'}]);assert.ok(!invalid.includes('href='));
 assert.ok(render([]).includes('尚未找到對應貨源'));
});
test('profit chart preserves signed percentage and separates sale price from spread',()=>{
 const html=render([{...row,source_format:'CD',market_currency:'USD',market_price:'30',sale_twd:'900',spread_twd:'550',gross_margin:-1.25,gross_twd:'-1125'}]);
 for(const value of ['價差','毛利率','-125.0%','NT$ -1,125','USD','CD','虧損','left:0%','width:50%'])assert.ok(html.includes(value),value);
 const missing=render([{...row,gross_margin:null}]);assert.ok(missing.includes('毛利率尚未取得'));assert.ok(!missing.includes('NaN'));
});
test('only highest known gross is outside collapsed sources, even when all offers lose money',()=>{
 const html=render([{...row,source_title:'unknown',gross_twd:null},{...row,source_url:'https://example.com/loss',source_title:'larger loss',gross_twd:'-200'},{...row,source_url:'https://example.com/best',source_title:'best offer',gross_twd:'-20'}]);
 const [visible,collapsed]=html.split('<details>');
 assert.ok(visible.includes('best offer'));assert.ok(!visible.includes('larger loss'));assert.ok(!visible.includes('unknown'));
 assert.ok(collapsed.includes('展開其餘 2 個賣場'));assert.ok(collapsed.indexOf('larger loss')<collapsed.indexOf('unknown'));
 assert.ok(visible.includes('價差／毛利'));assert.ok(visible.includes('<small>毛利率</small><b>—</b>'));
});
test('source action shows readiness and disables while locked or market missing',()=>{
 const action=(extra,locked=false)=>renderToStaticMarkup(React.createElement(exports.default,{rows:[{...row,...extra}],locked,onAction:()=>{}}));
 assert.ok(action({has_market:true,ready:false}).includes('核對貨源'));
 assert.ok(action({has_market:true,ready:true}).includes('建立草稿'));
 assert.ok(action({has_market:true,ready:true},true).includes('disabled=""'));
 assert.ok(action({has_market:false}).includes('disabled=""'));
});

test('stock, auction and unavailable offers are visibly distinguished',()=>{
 for(const [extra,label] of [[{availability:'來源標示有庫存'},'來源標示現貨'],[{availability:'未確認'},'供貨待確認'],[{price_kind:'current_bid'},'拍賣未結標'],[{availability:'現在オンラインショップ取扱なし'},'缺貨／預購／待調貨']])assert.ok(render([{...row,...extra}]).includes(label));
});

test('quote dates keep source fetch separate from newer confirmed cost',()=>{
 const now=new Date().toISOString();
 const html=render([{...row,has_market:true,market_at:now,source_at:'2020-01-01T00:00:00Z',cost_at:now,cost_basis:'confirmed_total'}]);
 assert.ok(html.includes('超過 48 小時'));assert.ok(html.includes('採已確認總成本'));assert.ok(html.includes('48 小時內'));
 const missing=render([{...row,has_market:true,market_at:now}]);assert.ok(missing.includes('貨源 時間未取得'));
});

test('positive gross never hides a loss after configured costs',()=>{
 const html=render([{...row,gross_twd:'1100.91',net_twd:'-979.22'}]);
 assert.ok(html.includes('NT$ 1,100.91'));assert.ok(html.includes('扣已設定費用後：NT$ -979.22 · 估算虧損'));
 assert.ok(render([{...row,net_twd:null}]).includes('扣費後金額待取得'));
 assert.ok(!render([{...row,net_twd:null}]).includes('NT$ 0'));
});

test('margin sorting promotes the highest percentage, not the largest gross amount',()=>{
 const rows=[{...row,source_title:'large amount',gross_twd:'500',gross_margin:0.1},{...row,source_url:'https://example.com/rate',source_title:'best percentage',gross_twd:'100',gross_margin:0.5}];
 const html=renderToStaticMarkup(React.createElement(exports.default,{rows,sortBy:'margin'}));
 const [visible,collapsed]=html.split('<details>');
 assert.ok(visible.includes('best percentage'));assert.ok(!visible.includes('large amount'));assert.ok(collapsed.includes('large amount'));
 assert.ok(visible.includes('預估毛利率由高到低'));
 assert.ok(render(rows).split('<details>')[0].includes('large amount'));
});
test('missing and nonfinite margins remain behind losses without becoming zero',()=>{
 for(const value of [null,undefined,NaN,Infinity,''])assert.equal(prices.candidateProfit({...row,gross_margin:value},'margin'),-Infinity);
 const rows=[{...row,source_title:'unknown',gross_margin:null},{...row,source_url:'https://example.com/negative',source_title:'known loss',gross_margin:-0.3}];
 const html=renderToStaticMarkup(React.createElement(exports.default,{rows,sortBy:'margin'}));
 assert.ok(html.split('<details>')[0].includes('known loss'));
});
test('catalog inferred from title is labeled rather than presented as supplied metadata',()=>{
 const html=render([{...row,source_catalog_no:'AP-8156',source_catalog_from_title:true}]);
 assert.ok(html.includes('AP-8156'));assert.ok(html.includes('由標題辨識，待核對'));
 assert.ok(!render([{...row,source_catalog_no:'AP-8156'}]).includes('由標題辨識'));
});


test('a full purchase list blocks adding without disabling source review',()=>{
 const html=renderToStaticMarkup(React.createElement(exports.default,{rows:[{...row,has_market:true}],onAction:()=>{},onPurchase:()=>{},purchaseLocked:true}));
 assert.match(html,/<button[^>]*disabled=""[^>]*>加入採購清單/);
 assert.match(html,/<button type="button" class="btn secondary">核對貨源/);
});
