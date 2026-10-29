import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const code=ts.transpileModule(await readFile(new URL('../lib/state-pack.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const pack=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const fixture=JSON.parse(await readFile(new URL('./fixtures/state-pack.json',import.meta.url),'utf8'));
test('rows packed by the server are restored exactly, including nulls and missing keys',()=>{
 const rows=pack.unpackRows(fixture.packed);
 assert.deepEqual(rows,fixture.rows);
 assert.equal('evidence' in rows[6],false);assert.equal(rows[3].gross_margin,null);assert.equal('excluded' in rows[0],false);
});
test('unknown or inconsistent formats fail loudly instead of showing partial data',()=>{
 assert.throws(()=>pack.unpackRows({...fixture.packed,version:2}));
 assert.throws(()=>pack.unpackRows({...fixture.packed,n:fixture.packed.n+1}));
 const broken=structuredClone(fixture.packed);delete broken.c[broken.f[0]];assert.throws(()=>pack.unpackRows(broken));
});
test('original-shape states pass through untouched',()=>{
 const state={workflow:{comparisons:[{a:1}]}};assert.equal(pack.normalizeState(state),state);
 const packed=pack.normalizeState({x:1,workflow:{drafts:[],comparisons_packed:fixture.packed}});
 assert.deepEqual(packed,{x:1,workflow:{drafts:[],comparisons:fixture.rows}});
});
