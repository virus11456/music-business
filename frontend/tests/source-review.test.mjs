import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const source=await readFile(new URL('../components/workflow.tsx',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const realRequire=createRequire(import.meta.url), exports={};
const require=id=>{
 if(id==='@/lib/draft-filter')return {filterDrafts:()=>[]};
 if(id==='@/lib/draft-selection')return {draftSelection:()=>({}),exportIssues:()=>[]};
 if(id==='@/components/ui/button')return {Button:props=>React.createElement('button',props)};
 if(id.startsWith('@/'))return {default:()=>null};
 return realRequire(id);
};
new Function('require','exports',js)(require,exports);
const row={key:'selected',release_id:42,candidate_id:999,source_title:'Selected CD',source_currency:'TWD',source_price:'350',source_url:'https://example.com/product',vendor:'ruten',availability:'有庫存',ready:false,offer:null};
const render=(initialReview,drafts=[])=>renderToStaticMarkup(React.createElement(exports.default,{view:'review',initialReview,workflow:{platforms:{candidates:[]},drafts,grades:['Mint (M)']},records:[{release_id:1,artist:'Wrong',title:'Other'},{release_id:42,artist:'Artist',title:'Selected CD',format:'CD'}],jobs:[],active:null,locked:false,send:async()=>true}));
test('direct review retains selected source and currency even outside the 200-candidate preview',()=>{
 const html=render(row);
 assert.ok(html.includes('value="42" selected=""'));
 assert.ok(html.includes('https://example.com/product'));
 assert.ok(html.includes('來源標價 TWD 350'));
 assert.ok(html.includes('<option selected="">TWD</option>'));
 assert.ok(!html.includes('先找貨，再查需求'));
 assert.ok(!html.includes('上架前商品整理'));
});
test('ready source opens draft with saved offer fields, never an empty unrelated record',()=>{
 const html=render({...row,ready:true,offer:{id:17,sale_price:'40',sale_currency:'USD',media_cond:'Mint (M)',sleeve_cond:'Mint (M)',version_confirmed:1,supply_confirmed:1,dispatch_days:7}});
 for(const value of ['新增商品草稿','name="price"','value="40"','name="source_offer_id" value="17"','https://example.com/product'])assert.ok(html.includes(value),value);
});

test('returning to the same offer preserves edited draft price, note and identity',()=>{
 const offer={id:17,sale_price:'40',sale_currency:'USD',media_cond:'Mint (M)',sleeve_cond:'Mint (M)',version_confirmed:1,supply_confirmed:1,dispatch_days:7};
 const draft={id:8,release_id:42,source_offer_id:17,source_url:row.source_url,price:'55',currency:'EUR',media_cond:'Very Good (VG)',sleeve_cond:'Generic',note:'Original OBI included.',dispatch_days:3,version_confirmed:1,supply_confirmed:1,owned_confirmed:0};
 const html=render({...row,ready:true,offer},[draft]);
 for(const value of ['編輯／重新確認草稿','name="draft_id" value="8"','value="55"','Original OBI included.','正在編輯既有草稿 #8','<option selected="">EUR</option>'])assert.ok(html.includes(value),value);
 assert.ok(!html.includes('name="price" type="number" min="0.01" step="0.01" required="" value="40"'));
});
test('a draft from a different offer of the same release is not reused',()=>{
 const html=render({...row,ready:true,offer:{id:17,sale_price:'40',sale_currency:'USD'}},[{id:8,release_id:42,source_offer_id:18,price:'55',note:'Other copy note'}]);
 assert.ok(html.includes('新增商品草稿'));
 assert.ok(html.includes('name="draft_id" value=""'));
 assert.ok(!html.includes('Other copy note'));
});
test('a source requiring review still opens its offer form rather than the saved draft',()=>{
 const html=render({...row,ready:false,offer:{id:17,amount:'350',currency:'TWD'}},[{id:8,source_offer_id:17,price:'55',note:'Keep note'}]);
 assert.ok(html.includes('核對貨源與上架資料'));
 assert.ok(html.includes('name="offer_id" value="17"'));
 assert.ok(!html.includes('正在編輯既有草稿'));
});
