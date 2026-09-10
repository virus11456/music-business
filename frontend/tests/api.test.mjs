import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/api.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const api=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));

test('authentication stays in headers and is removed on logout',async()=>{
 const original=globalThis.fetch;const calls=[];
 try{
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return new Response('{}');};
  api.setAccessCode('test-admin-code');await api.apiFetch('/api/state');
  assert.equal(calls[0].url,'/api/state');assert.equal(calls[0].options.headers.get('Authorization'),'Bearer test-admin-code');
  assert.equal(calls[0].options.credentials,'omit');assert.equal(calls[0].options.redirect,'error');
  api.setAccessCode('');await api.apiFetch('/api/state');assert.equal(calls[1].options.headers.get('Authorization'),null);
 }finally{globalThis.fetch=original;api.setAccessCode('');}
});

test('logout cancels in-flight requests and changes session revision',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=(_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
  const before=api.accessRevision();const request=api.apiFetch('/api/state');
  const rejected=assert.rejects(request,{name:'AbortError'});
  api.setAccessCode('');await rejected;assert.ok(api.accessRevision()>before);
 }finally{globalThis.fetch=original;}
});
