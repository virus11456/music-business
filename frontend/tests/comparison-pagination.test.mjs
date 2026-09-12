import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createRequire} from 'node:module';import ts from 'typescript';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),cache={};
function load(name){if(cache[name])return cache[name];const out=cache[name]={};new Function('require','exports',ts.transpileModule(readFileSync(new URL('../'+name,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(id=>id==='@/components/ui/button'?{Button:props=>React.createElement('button',props)}:id.startsWith('@/')?load(id.slice(2)+'.ts'):require(id),out);return out;}
const View=load('components/comparison-table.tsx').default;
const row={format:'CD',source_format:'CD',gross_twd:'100',gross_margin:0.2,source_price:'500',source_currency:'TWD',market_price:'20',market_currency:'USD',issues:[],version_confirmed:false,has_market:true,offer:null,listing_status:'unlisted'};
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
