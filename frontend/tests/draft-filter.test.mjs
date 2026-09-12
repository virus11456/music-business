import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/draft-filter.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {filterDrafts,formatMatches}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
const filters={query:'',format:'all',status:'all',sort:'newest'};
const row=(id,extra={})=>({id,release_id:100+id,artist:'Test Artist',title:'Album',format:'Vinyl, LP',currency:'USD',export_issues:[],profit_review:{ready:true,net_twd:'10'},...extra});
test('formats include mixed releases and keep unknown formats separate',()=>{
 assert.equal(formatMatches('Vinyl, LP, CD','CD'),true);
 assert.equal(formatMatches('Cassette','Cassette'),true);
 assert.equal(formatMatches('CDr','CD'),false);
 assert.equal(formatMatches('Unknown','other'),true);
 assert.equal(formatMatches('CD','other'),false);
});
test('search normalizes width and case and supports release ID',()=>{
 assert.equal(filterDrafts([row(1)],{...filters,query:'ＴＥＳＴ'},'USD').length,1);
 assert.equal(filterDrafts([row(1)],{...filters,query:'101'},'USD').length,1);
 assert.equal(filterDrafts([row(1)],{...filters,query:'missing'},'USD').length,0);
});
test('readiness combines seller currency with profit and export review',()=>{
 const rows=[row(1),row(2,{currency:'JPY'}),row(3,{export_issues:['stale']}),row(4,{profit_review:{ready:false,net_twd:null}})];
 assert.deepEqual(filterDrafts(rows,{...filters,status:'ready'},'USD').map(d=>d.id),[1]);
 assert.deepEqual(filterDrafts(rows,{...filters,status:'attention'},'USD').map(d=>d.id),[4,3,2]);
});
test('profit ordering keeps losses above missing values and does not mutate input',()=>{
 const rows=[row(1,{profit_review:{ready:false,net_twd:null}}),row(2,{profit_review:{ready:false,net_twd:'-20'}}),row(3)];
 assert.deepEqual(filterDrafts(rows,{...filters,sort:'profit'},'USD').map(d=>d.id),[3,2,1]);
 assert.deepEqual(rows.map(d=>d.id),[1,2,3]);
});
test('listing filter separates registered listings from unlisted and unknown records',()=>{
 const rows=[row(1,{listing_status:'listed'}),row(2,{listing_status:'unlisted'}),row(3)];
 assert.deepEqual(filterDrafts(rows,{...filters,listing:'unlisted'},'USD').map(d=>d.id),[2]);
 assert.deepEqual(filterDrafts(rows,{...filters,listing:'listed'},'USD').map(d=>d.id),[1]);
 assert.deepEqual(filterDrafts(rows,{...filters,listing:'all'},'USD').map(d=>d.id),[3,2,1]);
 assert.deepEqual(filterDrafts(rows,{...filters,listing:'listed',status:'ready'},'USD'),[]);
});
