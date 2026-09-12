import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const exports={};new Function('exports',ts.transpileModule(await readFile(new URL('../lib/listing-status.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports);
test('unknown or future listing states are never presented or filtered as unlisted',()=>{
 for(const value of [undefined,null,'','sold','unexpected']){
  assert.equal(exports.listingLabel(value),'刊登狀態待確認');
  assert.equal(exports.matchesListing(value,'unlisted'),false);
  assert.equal(exports.matchesListing(value,'listed'),false);
  assert.equal(exports.matchesListing(value,'unknown'),true);
  assert.equal(exports.matchesListing(value,'all'),true);
 }
 assert.equal(exports.listingLabel('listed'),'已上架');assert.equal(exports.listingLabel('unlisted'),'未上架');
 assert.equal(exports.matchesListing('listed','unlisted'),false);assert.equal(exports.matchesListing('unlisted','unlisted'),true);
});
