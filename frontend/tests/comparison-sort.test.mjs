import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/comparison-sort.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {sortComparisons}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
const rows=[{key:'a',want:100,gross_twd:'20',gross_margin:.2},{key:'b',want:200,gross_twd:'10',gross_margin:.3},{key:'c',want:null,gross_twd:null,gross_margin:null},{key:'d',want:0,gross_twd:'-10',gross_margin:-.1}];
test('want, gross and margin sort numerically, with missing values last',()=>{
 assert.deepEqual(sortComparisons(rows,'want').map(r=>r.key),['b','a','d','c']);
 assert.deepEqual(sortComparisons(rows,'gross').map(r=>r.key),['a','b','d','c']);
 assert.deepEqual(sortComparisons(rows,'margin').map(r=>r.key),['b','a','d','c']);
 assert.equal(rows[0].key,'a');
});
