import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/job-report.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {jobReport}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
test('scheduled batches show market, platform outcomes, matches and Sheets',()=>{
 const text=jobReport(JSON.stringify({versions:1,batches:[{releases:[{release_id:123,market:'完成',sourcing:{platforms:[{platform:'tower',status:'success',count:4},{platform:'ruten',status:'failed',count:0},{platform:'yahoo_jp',status:'empty',count:0}],possible_matches:2}}],sheet_sync:{synced:true}}]})).join('\n');
 for(const expected of ['1 個版本','版本 #123','取得 4 件候選','露天：未完成','沒有搜尋結果','可能配對 2 件','同步完成'])assert.ok(text.includes(expected),expected);
});
test('unknown errors and payloads are not printed',()=>{
 const secret='PRIVATE_PAYLOAD';
 const text=jobReport(JSON.stringify({errors:[{step:'sheets',error:secret}],platforms:[{platform:secret,status:secret}],other:secret})).join('\n');
 assert.ok(text.includes('Google Sheets 同步未完成'));assert.ok(!text.includes(secret));
 assert.ok(!jobReport(secret).join('').includes(secret));
});
test('older and malformed records remain readable',()=>{
 assert.ok(jobReport('{}')[0].includes('未保存'));
 assert.ok(jobReport(JSON.stringify({failed_platforms:2}))[0].includes('舊紀錄'));
 assert.ok(jobReport(JSON.stringify({synced:true,market_rows:3,source_rows:0}))[0].includes('報價 0 列'));
});
