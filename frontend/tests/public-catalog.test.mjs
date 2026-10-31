import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),cache={};
function load(name){if(cache[name])return cache[name];const out=cache[name]={};new Function('require','exports',ts.transpileModule(readFileSync(new URL('../'+name,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(id=>id.startsWith('@/')?load(id.slice(2)+(id.startsWith('@/components/')?'.tsx':'.ts')):require(id),out);return out;}
const View=load('components/public-catalog.tsx').default;
const stamp=new Date().toISOString();
const row={key:'candidate-1',release_id:1,format:'CD',source_format:'CD',source_url:'https://example.com/item',source_title:'Source Album',source_price:'500',source_currency:'TWD',market_price:'30',market_currency:'USD',market_at:stamp,source_at:stamp,want:12,has_market:true,gross_twd:'400',gross_margin:.44,cost_basis:'source_price',availability:'來源標示有庫存',offer:null};
const render=rows=>renderToStaticMarkup(React.createElement(View,{records:[{release_id:1,artist:'Artist',title:'Album',format:'CD'}],rows,login:null,onLogin:()=>{},error:'',onRefresh:()=>{}}));
test('anonymous catalogue shows approved pricing and format without login fields or write controls',()=>{
 const html=render([row]);for(const text of ['免登入瀏覽','Artist','Source Album','Want 12','毛利率','CD','https://example.com/item'])assert.ok(html.includes(text),text);
 for(const text of ['type="password"','加入採購','新增商品草稿','加入唱片'])assert.ok(!html.includes(text),text);
});
test('public catalogue hides losses and conflicting formats while preserving the input rows',()=>{
 const rows=[{...row,source_format:'Vinyl'},{...row,key:'negative',gross_twd:'-1',gross_margin:-.1}];
 const before=JSON.stringify(rows),html=render(rows);assert.ok(html.includes('目前沒有符合條件的唱片'));assert.equal(JSON.stringify(rows),before);
});

test('public catalogue can rank by Want/Have and shows Have with the ratio',()=>{
 const View2=load('components/public-catalog.tsx').default;
 const records=[{release_id:1,artist:'Common',title:'Owned',format:'CD'},{release_id:2,artist:'Scarce',title:'Wanted',format:'CD'}];
 const rows=[{...row,want:300,have:600},{...row,key:'candidate-2',release_id:2,want:90,have:2,source_url:'https://example.com/item2'}];
 const html=renderToStaticMarkup(React.createElement(View2,{records,rows,login:null,onLogin:()=>{},error:'',onRefresh:()=>{}}));
 for(const text of ['Have 600 人','比值 0.5','Have 2 人','比值 45','Want／Have 比'])assert.ok(html.includes(text),text);
});
