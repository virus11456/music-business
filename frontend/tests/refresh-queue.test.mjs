import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/refresh-queue.ts',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {createRefreshQueue,nextPollDelay}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
function setup(){const requests=[],values=[];const queue=createRefreshQueue(()=>new Promise((resolve,reject)=>requests.push({resolve,reject})),v=>values.push(v));return {queue,requests,values}}
test('ordinary overlapping polls share one read',async()=>{
 const {queue,requests,values}=setup();const first=queue.refresh();assert.equal(queue.refresh(),first);assert.equal(requests.length,1);
 requests[0].resolve('current');await first;assert.deepEqual(values,['current']);
});
test('save refresh discards old result and waits for fresh state',async()=>{
 const {queue,requests,values}=setup();const first=queue.refresh();const afterSave=queue.refresh(true);queue.refresh(true);
 requests[0].resolve('before save');await Promise.resolve();assert.deepEqual(values,[]);assert.equal(requests.length,2);
 requests[1].resolve('after save');await afterSave;await first;assert.deepEqual(values,['after save']);
});
test('another save during the queued read schedules one more fresh read',async()=>{
 const {queue,requests,values}=setup();const done=queue.refresh();queue.refresh(true);requests[0].resolve('old');await Promise.resolve();
 queue.refresh(true);requests[1].resolve('middle');await Promise.resolve();assert.equal(requests.length,3);assert.deepEqual(values,[]);
 requests[2].resolve('latest');await done;assert.deepEqual(values,['latest']);
});
test('obsolete errors are discarded and final failures release the queue for retry',async()=>{
 const {queue,requests,values}=setup();const done=queue.refresh();queue.refresh(true);requests[0].reject(Error('old failure'));await Promise.resolve();
 requests[1].reject(Error('current failure'));await assert.rejects(done,/current failure/);
 const retry=queue.refresh();requests[2].resolve('recovered');await retry;assert.deepEqual(values,['recovered']);
});

test('next poll waits at least the base interval and backs off for slow or failed reads',()=>{
 assert.equal(nextPollDelay(300),4000);
 assert.equal(nextPollDelay(3000),6000);
 assert.equal(nextPollDelay(60000),20000);
 assert.equal(nextPollDelay(300,true),10000);
 assert.equal(nextPollDelay(NaN),4000);
});
