import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const toUrl=code=>'data:text/javascript;base64,'+Buffer.from(ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText).toString('base64');
const packUrl=toUrl(await readFile(new URL('../lib/state-pack.ts',import.meta.url),'utf8'));
const source=(await readFile(new URL('../lib/api.ts',import.meta.url),'utf8')).replace("'./state-pack'","'"+packUrl+"'");
const api=await import(toUrl(source));

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


test('logout after response headers prevents a delayed CSV body from downloading',async()=>{
 const original=globalThis.fetch;let resolveBody;
 try{
  api.setAccessCode('test-session');
  globalThis.fetch=async()=>({ok:true,blob:()=>new Promise(resolve=>{resolveBody=resolve})});
  const downloading=api.downloadCsv('/api/drafts/export','review.csv');
  await new Promise(resolve=>setImmediate(resolve));
  api.setAccessCode('');resolveBody(new Blob(['private,csv']));
  await assert.rejects(downloading,/登入狀態已變更/);
 }finally{globalThis.fetch=original;api.setAccessCode('');}
});

test('state reads send the last validator and treat 304 as unchanged without parsing a body',async()=>{
 const original=globalThis.fetch;const calls=[];
 try{
  globalThis.fetch=async(url,options)=>{calls.push(options.headers.get('If-None-Match'));
   if(calls.length===1)return new Response('{"records":[]}',{status:200,headers:{ETag:'W/"abc"'}});
   if(calls.length===2)return new Response(null,{status:304,headers:{ETag:'W/"abc"'}});
   return new Response('{"records":[1]}',{status:200,headers:{ETag:'W/"def"'}});};
  const first=await api.fetchState();assert.deepEqual([first.unchanged,first.body],[false,{records:[]}]);assert.equal(calls[0],null);
  const second=await api.fetchState();assert.equal(second.unchanged,true);assert.equal(calls[1],'W/"abc"');
  api.setAccessCode('x');const third=await api.fetchState();assert.equal(calls[2],null);assert.deepEqual(third.body,{records:[1]});
 }finally{globalThis.fetch=original;api.setAccessCode('');}
});
test('an unexpected 304 without a stored validator is an error, never silently empty',async()=>{
 const original=globalThis.fetch;
 try{globalThis.fetch=async()=>new Response(null,{status:304});await assert.rejects(api.fetchState());}
 finally{globalThis.fetch=original;}
});

test('state reads ask for the compact format and restore the original comparison rows',async()=>{
 const fixture=JSON.parse(await readFile(new URL('./fixtures/state-pack.json',import.meta.url),'utf8'));
 const original=globalThis.fetch;let accept='';
 try{
  globalThis.fetch=async(url,options)=>{accept=options.headers.get('Accept');return new Response(JSON.stringify({records:[],workflow:{drafts:[1],comparisons_packed:fixture.packed}}),{status:200,headers:{ETag:'W/"p"'}});};
  const result=await api.fetchState();
  assert.match(accept,/application\/vnd\.simples\.packed\+json/);
  assert.deepEqual(result.body,{records:[],workflow:{drafts:[1],comparisons:fixture.rows}});
  globalThis.fetch=async()=>new Response(JSON.stringify({workflow:{comparisons:fixture.rows}}),{status:200});
  assert.deepEqual((await api.fetchState()).body,{workflow:{comparisons:fixture.rows}});
 }finally{globalThis.fetch=original;api.setAccessCode('');}
});
