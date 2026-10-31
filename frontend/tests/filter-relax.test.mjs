import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/filter-relax.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {relaxedCounts}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
const items=[{fresh:true,strong:false},{fresh:false,strong:true},{fresh:false,strong:false},{fresh:true,strong:true}];
const count=f=>items.filter(i=>(!f.fresh||i.fresh)&&(!f.strong||i.strong)).length;

test('counts what each active filter hides and all of them together',()=>{
 const result=relaxedCounts({fresh:true,strong:true},[
  {label:'fresh',active:true,relax:f=>({...f,fresh:false})},
  {label:'strong',active:true,relax:f=>({...f,strong:false})},
  {label:'inactive',active:false,relax:f=>f},
 ],count);
 assert.deepEqual(result,{each:[{label:'fresh',count:2},{label:'strong',count:2}],all:4});
});

test('no active filter reports the unfiltered count',()=>{
 assert.deepEqual(relaxedCounts({fresh:false,strong:false},[{label:'fresh',active:false,relax:f=>f}],count),{each:[],all:4});
});
