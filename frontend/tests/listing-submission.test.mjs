import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const exports={};new Function('exports',ts.transpileModule(await readFile(new URL('../lib/listing-submission.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports);
test('unknown states are never shown as created and open attempts need review',()=>{
 for(const value of [undefined,null,'','sold','queued'])assert.equal(exports.submissionLabel(value),'狀態待確認');
 assert.equal(exports.submissionLabel('listed'),'Discogs 已建立');
 const now=Date.parse('2026-09-18T00:20:00Z');
 assert.equal(exports.needsReview({status:'uncertain'},now),true);
 assert.equal(exports.needsReview({status:'listed'},now),false);
 assert.equal(exports.needsReview({status:'submitting',started_at:'2026-09-18T00:15:00Z'},now),false);
 assert.equal(exports.needsReview({status:'submitting',started_at:'2026-09-18T00:05:00Z'},now),true);
 assert.equal(exports.needsReview({status:'submitting',started_at:'broken'},now),true);
});
test('submission is only possible when the backend flag is on and nothing is blocked or unresolved',()=>{
 const base={enabled:true,selected:3,blocked:0,hidden:0,locked:false,open:0};
 assert.equal(exports.canSubmit(base),true);
 for(const change of [{enabled:false},{selected:0},{selected:51},{blocked:1},{hidden:1},{locked:true},{open:1}])assert.equal(exports.canSubmit({...base,...change}),false,JSON.stringify(change));
 assert.equal(exports.openCount([{status:'listed'},{status:'uncertain'},{status:'submitting'},{status:'failed'}]),2);
 assert.equal(exports.openCount(undefined),0);
});
test('listing links come only from positive integer ids',()=>{
 assert.equal(exports.listingUrl(42),'https://www.discogs.com/sell/item/42');
 for(const value of [null,0,-1,1.5,'42'])assert.equal(exports.listingUrl(value),null);
});
