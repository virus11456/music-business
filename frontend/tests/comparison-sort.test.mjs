import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/comparison-sort.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {sortComparisons,referenceUsd,meetsMinimumUsd,marketFreshness,sourceFreshness,hasDemandAndSource}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
const rows=[{key:'a',want:100,gross_twd:'20',gross_margin:.2},{key:'b',want:200,gross_twd:'10',gross_margin:.3},{key:'c',want:null,gross_twd:null,gross_margin:null},{key:'d',want:0,gross_twd:'-10',gross_margin:-.1}];
test('want, gross and margin sort numerically, with missing values last',()=>{
 assert.deepEqual(sortComparisons(rows,'want').map(r=>r.key),['b','a','d','c']);
 assert.deepEqual(sortComparisons(rows,'gross').map(r=>r.key),['a','b','d','c']);
 assert.deepEqual(sortComparisons(rows,'margin').map(r=>r.key),['b','a','d','c']);
 assert.equal(rows[0].key,'a');
});

test('USD minimum is inclusive, excludes missing prices and respects sale currency',()=>{
 for(const [price,expected] of [['19.99',false],['20',true],['30',true],[null,false],['',false],['NaN',false]]){
  assert.equal(meetsMinimumUsd({sale_usd:price},'20'),expected);
 }
 assert.equal(meetsMinimumUsd({sale_usd:null},''),true);
 assert.equal(meetsMinimumUsd({sale_usd:'29.99'},'30'),false);
 assert.equal(meetsMinimumUsd({sale_usd:'25.50'},'25.50'),true);
 assert.equal(referenceUsd({market_price:'3000',market_currency:'JPY'}),null);
 assert.equal(referenceUsd({offer:{sale_price:'10',sale_currency:'USD'},market_price:'50',market_currency:'USD'}),10);
 assert.equal(referenceUsd({offer:{sale_price:'3000',sale_currency:'JPY'},market_price:'50',market_currency:'USD'}),null);
});

test('market freshness handles boundary, missing, invalid and future timestamps',()=>{
 const now=Date.parse('2026-09-11T10:00:00+08:00');
 const row={has_market:true,market_at:new Date(now-48*3600000).toISOString()};
 assert.equal(marketFreshness(row,now),'fresh');
 assert.equal(marketFreshness({...row,market_at:new Date(now-48*3600000-1).toISOString()},now),'stale');
 for(const market_at of [null,'','invalid',new Date(now+1).toISOString()])assert.equal(marketFreshness({...row,market_at},now),'unknown');
 assert.equal(marketFreshness({...row,has_market:false},now),'unknown');
});

test('source freshness never borrows Discogs or unrelated source timestamps',()=>{
 const now=Date.parse('2026-09-11T10:00:00+08:00'),fresh=new Date(now).toISOString(),old='2020-01-01T00:00:00Z';
 assert.equal(sourceFreshness({source_at:old,market_at:fresh},now),'stale');
 assert.equal(sourceFreshness({source_at:fresh,cost_at:old,cost_basis:'confirmed_total'},now),'stale');
 assert.equal(sourceFreshness({source_at:old,cost_at:fresh,cost_basis:'confirmed_total'},now),'fresh');
 for(const source_at of [undefined,'bad',new Date(now+1).toISOString()])assert.equal(sourceFreshness({source_at},now),'unknown');
 assert.equal(sourceFreshness({source_at:new Date(now-48*3600000).toISOString()},now),'fresh');
});

test('main list requires demand, both prices and a source link',()=>{
 const row={format:"CD",source_format:"CD",want:20,has_market:true,market_price:'30',market_currency:'USD',source_price:'500',source_currency:'TWD',source_url:'https://www.ruten.com.tw/item/show?123',gross_twd:'-5'};
 assert.equal(hasDemandAndSource(row),true);
 for(const change of [{want:0},{want:null},{has_market:false},{market_price:null},{source_price:null},{source_price:'NaN'},{excluded:true},{source_url:'javascript:alert(1)'}])assert.equal(hasDemandAndSource({...row,...change}),false);
});
