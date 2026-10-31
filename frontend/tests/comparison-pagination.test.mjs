import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createRequire} from 'node:module';import ts from 'typescript';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),cache={};
function load(name){if(cache[name])return cache[name];const out=cache[name]={};new Function('require','exports',ts.transpileModule(readFileSync(new URL('../'+name,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(id=>id==='@/components/ui/button'?{Button:props=>React.createElement('button',props)}:id.startsWith('@/')?load(id.slice(2)+(id.startsWith('@/components/')?'.tsx':'.ts')):require(id),out);return out;}
const View=load('components/comparison-table.tsx').default;
const row={market_at:new Date().toISOString(),source_at:new Date().toISOString(),want:10,format:'CD',source_format:'CD',gross_twd:'100',gross_margin:0.2,source_price:'500',source_currency:'TWD',market_price:'20',market_currency:'USD',issues:[],version_confirmed:false,source_catalog_no:'CAT-1',catalog_no:'CAT-1',has_market:true,offer:null,listing_status:'unlisted'};
const render=n=>renderToStaticMarkup(React.createElement(View,{rows:Array.from({length:n},(_,i)=>({...row,key:String(i).padStart(4,'0'),source_title:'item-'+i,release_title:'Album',source_url:'https://example.com/'+i,release_id:i+1})),locked:false,send:async()=>true,onReview:()=>{},onDraft:()=>{}}));
test('large comparison sets render at most 50 rows while preserving the total and pagination',()=>{
 const html=render(121),tbody=html.split('<tbody>')[1].split('</tbody>')[0];
 assert.equal((tbody.match(/<tr>/g)||[]).length,50);
 assert.ok(html.includes('符合條件 121 筆'));assert.ok(html.includes('第 1／3 頁'));assert.ok(html.includes('item-49'));assert.ok(!html.includes('item-50'));
 assert.ok(html.includes('批次選取限本頁'));
});
test('empty comparison set remains a valid empty first page',()=>{
 const html=render(0);assert.ok(html.includes('第 1／1 頁'));assert.ok(html.includes('尚無符合條件的配對'));assert.ok(!html.includes('NaN'));
});

test('profitable view excludes conflicting identity and missing demand or usable source even after old confirmation',()=>{
 const base={...row,key:'valid',source_title:'valid-source',release_title:'Album',source_url:'https://example.com/item',release_id:1};
 const variants=[{source_format:'Vinyl'},{source_catalog_no:'ABC-1',catalog_no:'XYZ-2',version_confirmed:true},{want:0},{want:null},{source_price:null},{source_url:''},{gross_margin:-0.1},{excluded:true}];
 const rows=[base,...variants.map((patch,i)=>({...base,...patch,key:'bad-'+i,source_title:'bad-source-'+i}))];
 const html=renderToStaticMarkup(React.createElement(View,{rows,locked:false,send:async()=>true,onReview:()=>{},onDraft:()=>{}}));
 assert.ok(html.includes('符合條件 1 筆'));assert.ok(html.includes('valid-source'));assert.ok(!html.includes('bad-source-'));
});

test('default view hides old or unknown timestamps and unavailable supply while labeling unknown stock honestly',()=>{
 const base={...row,key:'fresh',source_title:'fresh-source',release_title:'Album',source_url:'https://example.com/item',release_id:1};
 const old=new Date(Date.now()-49*3600000).toISOString();
 const variants=[{market_at:old},{source_at:old},{source_at:null},{market_at:null},{availability:'售完'},{availability:'預購'},{price_kind:'current_bid'},{cost_basis:'confirmed_total',cost_at:old},{source_at:old,cost_basis:'confirmed_total',cost_at:new Date().toISOString()}];
 const rows=[base,...variants.map((patch,i)=>({...base,...patch,key:'stale-'+i,source_title:'hidden-source-'+i}))];
 const html=renderToStaticMarkup(React.createElement(View,{rows,locked:false,send:async()=>true,onReview:()=>{},onDraft:()=>{}}));
 assert.ok(html.includes('符合條件 1 筆'));assert.ok(html.includes('fresh-source'));assert.ok(!html.includes('hidden-source-'));assert.ok(html.includes('供貨待確認'));
});

test('listing status is an independent control and unknown rows are not labeled unlisted',()=>{
 const html=renderToStaticMarkup(React.createElement(View,{rows:[{...row,listing_status:undefined,key:'unknown',source_title:'Unknown listing',release_title:'Album',source_url:'https://example.com/item',release_id:1}],locked:false,send:async()=>true,onReview:()=>{},onDraft:()=>{}}));
 assert.ok(html.includes('aria-label="刊登狀態篩選"'));
 const tbody=html.split('<tbody>')[1].split('</tbody>')[0];
 assert.ok(tbody.includes('<b>刊登狀態待確認</b>'));assert.ok(!tbody.includes('<b>未上架</b>'));
 const quality=html.split('aria-label="篩選配對"')[1].split('</select>')[0];assert.ok(!quality.includes('value="unlisted"'));
});

test('by default only catalogue- or barcode-matched or confirmed pairings are listed',()=>{
 const base={...row,key:'k',release_title:'Album',source_url:'https://example.com/item',release_id:1};
 const rows=[{...base,key:'catalog',source_title:'catalog-match'},{...base,key:'name',source_title:'name-only',source_catalog_no:'',catalog_no:'CAT-1'},
  {...base,key:'confirmed',source_title:'confirmed-match',source_catalog_no:'',version_confirmed:true}];
 const html=renderToStaticMarkup(React.createElement(View,{rows,locked:false,send:async()=>true,onReview:()=>{},onDraft:()=>{}}));
 for(const t of ['catalog-match','confirmed-match','只看編號或條碼一致、已核對版本'])assert.ok(html.includes(t),t);
 assert.ok(!html.includes('name-only'));
});
