import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const source=await readFile(new URL('../components/record-sources.tsx',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const exports={};new Function('require','exports',js)(createRequire(import.meta.url),exports);
const row={source_url:'https://www.ruten.com.tw/item/show?123',vendor:'ruten',source_title:'Album A',source_price:'350',source_currency:'TWD',price_kind:'listed',gross_twd:'120',availability:'來源標示有庫存'};
const render=rows=>renderToStaticMarkup(React.createElement(exports.default,{rows}));
test('record source cards show actual quote, destination and candidate status',()=>{
 const html=render([row]);for(const text of ['露天市集','Album A','TWD 350','NT$ 120','開啟商品賣場','可能配對','href="'+row.source_url+'"'])assert.ok(html.includes(text));
 assert.ok(!html.includes('<button'));
});
test('excluded and duplicate sources do not inflate listings and invalid links cannot execute',()=>{
 const html=render([row,row,{...row,source_url:'https://example.com/excluded',excluded:true}]);assert.ok(html.includes('對應進貨賣場 · 1 件'));
 const invalid=render([{...row,source_url:'javascript:alert(1)'}]);assert.ok(!invalid.includes('href='));
 assert.ok(render([]).includes('尚未找到對應貨源'));
});
