import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {createRequire} from 'node:module';import ts from 'typescript';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const exports={};new Function('require','exports',ts.transpileModule(await readFile(new URL('../components/source-collection-form.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(createRequire(import.meta.url),exports);
const catalog=[{id:'ruten',name:'露天',supported:true},{id:'tower',name:'Tower',supported:true},{id:'other',name:'未接通',supported:false}];
test('saved topic restores only its supported platforms, never silently broadens scope',()=>{
 assert.deepEqual(exports.topicPlatforms({query:'CD',platforms:'["tower","tower","other","unknown"]'},catalog),['tower']);
 for(const platforms of [undefined,'not-json','{}','null'])assert.deepEqual(exports.topicPlatforms({query:'CD',platforms},catalog),[]);
});
test('requests require a real query and platform rather than triggering backend defaults',()=>{
 assert.deepEqual(exports.collectionRequest('  CD  ',['tower','tower','other'],catalog),{query:'CD',platforms:['tower']});
 for(const query of ['','   ','a'.repeat(121)])assert.equal(exports.collectionRequest(query,['tower'],catalog),null);
 assert.equal(exports.collectionRequest('CD',[],catalog),null);
 assert.equal(exports.collectionRequest('CD',['other'],catalog),null);
});
test('saved topics and scheduling consequence are visible without sending requests',()=>{
 let sent=0;const html=renderToStaticMarkup(React.createElement(exports.default,{topics:[{query:'Rubber Soul',platforms:'["tower"]'}],catalog,locked:false,send:async()=>{sent++;return true}}));
 for(const text of ['Rubber Soul','新增搜尋主題','納入定時更新','10:00','16:00','22:00','只處理已存商品'])assert.ok(html.includes(text));
 assert.ok(!html.includes('未接通'));assert.equal(sent,0);
});
