import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const exports={};new Function('exports',ts.transpileModule(await readFile(new URL('../lib/collection-job.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(exports);
const old={id:1,name:'先找貨 → 反查需求 → 比價同步',detail:'{"flow":"source_first"}',status:'success'};
test('latest failed and running collection cannot be hidden by an older success',()=>{
 for(const detail of [null,'APIError','invalid JSON']){
  const failed={id:3,name:'定時更新：09/12 10:00',detail,status:'failed'};
  assert.equal(exports.latestCollectionJob([old,failed,{id:4,name:'匯出',detail:null}]),failed);
 }
 const running={id:5,name:old.name,detail:null,status:'running'};
 assert.equal(exports.latestCollectionJob([old,running]),running);
});
test('detail-based recognition remains compatible and unrelated jobs are ignored',()=>{
 const renamed={id:7,name:'舊名稱',detail:'{"scheduled_slot":"slot"}'};
 assert.equal(exports.latestCollectionJob([renamed,old]),renamed);
 assert.equal(exports.latestCollectionJob([{id:9,name:'同步',detail:'null'},{id:10,name:'其他',detail:'oops'}]),undefined);
});
