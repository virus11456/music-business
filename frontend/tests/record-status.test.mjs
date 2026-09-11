import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {createRequire} from 'node:module';import ts from 'typescript';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const exports={};new Function('require','exports',ts.transpileModule(await readFile(new URL('../components/record-status.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(createRequire(import.meta.url),exports);
test('decisions never replace actual listing status',()=>{
 for(const listed of [false,true])for(const [decision,label] of [['want','要進貨'],['watch','觀察中'],['skip','已跳過']]){
  const html=renderToStaticMarkup(React.createElement(exports.default,{listed,decision}));
  assert.ok(html.includes(listed?'已上架':'未上架'));assert.ok(html.includes(label));
 }
});
test('listing aggregation uses recorded listings even when offer is excluded or unavailable',()=>{
 const ids=exports.listedReleaseIds([{release_id:1,listing_status:'listed',excluded:true,availability:'缺貨'},{release_id:1,listing_status:'unlisted'},{release_id:2,listing_status:'unlisted'},{release_id:3}]);
 assert.deepEqual([...ids],[1]);
});
