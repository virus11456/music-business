import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import {createRequire} from 'node:module';import ts from 'typescript';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const exports={};new Function('require','exports',ts.transpileModule(await readFile(new URL('../components/record-status.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(createRequire(import.meta.url),exports);
test('decisions never replace actual listing status',()=>{
 for(const status of ["listed","unlisted","unknown"])for(const [decision,label] of [['want','要進貨'],['watch','觀察中'],['skip','已跳過']]){
  const html=renderToStaticMarkup(React.createElement(exports.default,{status,decision}));
  assert.ok(html.includes({listed:'已上架',unlisted:'未上架',unknown:'刊登狀態待確認'}[status]));assert.ok(html.includes(label));
 }
});
test('listing aggregation uses recorded listings even when offer is excluded or unavailable',()=>{
 const ids=exports.recordListingStates([{release_id:1,listing_status:'listed',excluded:true,availability:'缺貨'},{release_id:1,listing_status:'unlisted'},{release_id:2,listing_status:'unlisted'},{release_id:3}]);
 assert.equal(ids.get(1),'listed');assert.equal(ids.get(2),'unlisted');assert.equal(ids.get(3),'unknown');
});

test('unlisted filter excludes a release even if another supplier is unlisted',()=>{
 const ids=exports.recordListingStates([{release_id:1,listing_status:'listed',excluded:true},{release_id:1,listing_status:'unlisted'},{release_id:2,listing_status:'unlisted'}]);
 const releases=[1,2];
 assert.deepEqual(releases.filter(id=>exports.matchesListingStatus(id,ids,'unlisted')),[2]);
 assert.deepEqual(releases.filter(id=>exports.matchesListingStatus(id,ids,'listed')),[1]);
 assert.deepEqual(releases.filter(id=>exports.matchesListingStatus(id,ids,'all')),[1,2]);
});

test('unknown suppliers and missing releases stay out of unlisted filter in either order',()=>{
 for(const rows of [[{release_id:1,listing_status:'unlisted'},{release_id:1}], [{release_id:1},{release_id:1,listing_status:'unlisted'}]]){
  const states=exports.recordListingStates(rows);
  for(const id of [1,99]){
   assert.equal(exports.matchesListingStatus(id,states,'unlisted'),false);
   assert.equal(exports.matchesListingStatus(id,states,'unknown'),true);
  }
 }
});
test('a recorded listing takes precedence over unknown suppliers in either order',()=>{
 for(const rows of [[{release_id:1},{release_id:1,listing_status:'listed'}],[{release_id:1,listing_status:'listed'},{release_id:1}]]){
  assert.equal(exports.recordListingStates(rows).get(1),'listed');
 }
 const html=renderToStaticMarkup(React.createElement(exports.default,{}));
 assert.ok(html.includes('刊登狀態待確認'));
});
