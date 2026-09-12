import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/draft-selection.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {draftSelection}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
const draft=(id,extra={})=>({id,currency:'USD',export_issues:[],profit_review:{ready:true},...extra});
test('bulk selection requires both currency and profit readiness',()=>{
 const state=draftSelection([draft(1),draft(2,{currency:'JPY'}),draft(3,{profit_review:{ready:false}}),draft(4,{export_issues:['報價過期']})],[],'USD');
 assert.deepEqual(state.eligible,[1]);assert.equal(state.canExport,false);
});
test('newly invalid or deleted selected drafts stay visible and block download',()=>{
 const state=draftSelection([draft(1,{export_issues:['來源更新']})],[1,2],'USD');
 assert.deepEqual(state.selected,[1,2]);assert.equal(state.blocked.length,2);assert.equal(state.canExport,false);
});
test('profit warning is advisory for a manually selected valid draft',()=>{
 const state=draftSelection([draft(1,{profit_review:{ready:false}})],[1],'USD');
 assert.equal(state.canExport,true);assert.deepEqual(state.warnings,[1]);
});
test('currency mismatch and missing review fail closed',()=>{
 assert.equal(draftSelection([draft(1)],[1],'JPY').canExport,false);
 assert.equal(draftSelection([{id:1,currency:'USD'}],[1],'USD').canExport,false);
});
test('enforces batch limit and normalizes duplicate selections',()=>{
 const rows=Array.from({length:501},(_,i)=>draft(i+1));
 assert.equal(draftSelection(rows,rows.map(d=>d.id),'USD').canExport,false);
 assert.equal(draftSelection(rows,rows.slice(0,500).map(d=>d.id),'USD').canExport,true);
 assert.deepEqual(draftSelection(rows,[1,1],'USD').selected,[1]);
});
test('a newly listed draft is blocked even when its old export review says ready',()=>{
 const before=draftSelection([draft(1,{listing_status:'unlisted'})],[1],'USD');
 assert.equal(before.canExport,true);
 const after=draftSelection([draft(1,{listing_status:'listed'})],[1],'USD');
 assert.equal(after.canExport,false);
 assert.deepEqual(after.eligible,[]);
 assert.match(after.blocked[0].issues.join(' '),/已登錄上架/);
});
