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
const render=initialReview=>renderToStaticMarkup(React.createElement(exports.default,{view:'review',initialReview,workflow:{platforms:{candidates:[]},drafts:[],grades:['Mint (M)']},records:[{release_id:1,artist:'Wrong',title:'Other'},{release_id:42,artist:'Artist',title:'Selected CD',format:'CD'}],jobs:[],active:null,locked:false,send:async()=>true}));
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
