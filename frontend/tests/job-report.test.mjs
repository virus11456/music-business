import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/job-report.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {jobReport,refreshFailures}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
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

test('saved quote refresh reports all supported platforms and retains legacy Ruten jobs',()=>{
 const text=jobReport(JSON.stringify({flow:'source_first',source_refresh:{platform:'all',platforms:[{platform:'tower',attempted:2,updated:1,failed:1,missing:0},{platform:'yahoo_tw',attempted:2,updated:2,failed:0,missing:0}]}})).join('\n');
 assert.ok(text.includes('Tower已存報價：檢查 2 件 · 更新 1 件'));assert.ok(text.includes('Yahoo 台灣已存報價'));
 const old=jobReport(JSON.stringify({flow:'source_first',source_refresh:{platform:'ruten',attempted:20,updated:20}})).join('\n');assert.ok(old.includes('露天已存報價：檢查 20 件'));
});

test('refresh failures expose safe reasons and construct trusted product links',()=>{
 const result=refreshFailures(JSON.stringify({batches:[{source_refresh:{platforms:[{platform:'tower',failures:[{external_id:'123',reason:'title_changed',url:'javascript:SECRET'},{external_id:'456',reason:'http_403'},{external_id:'../SECRET',reason:'SECRET'},{external_id:'789',reason:'SECRET'}]}]}}]}));
 assert.equal(result.length,3);assert.equal(result[0].url,'https://tower.jp/item/123');
 assert.ok(result[0].label.includes('版本標記'));assert.ok(result[1].label.includes('403'));
 assert.ok(!JSON.stringify(result).includes('SECRET'));assert.deepEqual(refreshFailures('bad'),[]);
});
