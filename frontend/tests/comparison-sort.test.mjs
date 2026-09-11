import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/comparison-sort.ts',import.meta.url),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {buildRecordIndex,meetsProfit,sortComparisons,referenceUsd,meetsMinimumUsd,marketFreshness,sourceFreshness,hasDemandAndSource,hasFreshComparison}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
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

test('48-hour comparison requires both quoted prices and confirmed cost when used',()=>{
 const now=Date.parse('2026-09-11T06:00:00Z'),fresh='2026-09-11T05:00:00Z',old='2026-09-01T05:00:00Z';
 const row={has_market:true,market_at:fresh,source_at:fresh,cost_basis:'source_price'};
 assert.ok(hasFreshComparison(row,now));
 assert.ok(!hasFreshComparison({...row,market_at:old},now));
 assert.ok(!hasFreshComparison({...row,source_at:null},now));
 assert.ok(!hasFreshComparison({...row,source_at:old,cost_basis:'confirmed_total',cost_at:fresh},now));
 assert.ok(!hasFreshComparison({...row,cost_basis:'confirmed_total',cost_at:old},now));
 assert.ok(hasFreshComparison({...row,cost_basis:'confirmed_total',cost_at:fresh},now));
});

test('positive gross does not pass the after-cost profit filter when fees erase the profit',()=>{
 const row={gross_twd:'800',net_twd:'-50'};
 assert.equal(meetsProfit(row,'gross'),true);
 assert.equal(meetsProfit(row,'net'),false);
 assert.equal(meetsProfit(row,'all'),true);
 assert.equal(meetsProfit({...row,net_twd:'0.01'},'net'),true);
});
test('profit filters reject break-even and missing or invalid values without mutating rows',()=>{
 for(const filter of ['gross','net'])for(const value of ['0','-1',null,undefined,'',' ','NaN',Infinity]){
  const row={gross_twd:value,net_twd:value};
  assert.equal(meetsProfit(row,filter),false);
  assert.equal(meetsProfit(row,'all'),true);
  assert.equal(row.gross_twd,value);
 }
});

test('record index shares one filtering pass and preserves release-specific matches and profit',()=>{
 const base={format:'CD',source_format:'CD',has_market:true,want:20,market_price:'30',source_price:'10',market_currency:'USD',source_currency:'USD',source_url:'https://example.com/one',gross_twd:'100',gross_margin:0.3};
 const items=Array.from({length:10000},(_,i)=>({...base,release_id:i%100,gross_twd:String(i),gross_margin:i/10000}));
 let checks=0;
 const index=buildRecordIndex(items,r=>{checks++;return r.release_id%2===0});
 assert.equal(checks,10000);assert.equal(index.size,50);
 for(let i=0;i<100;i++){
  const expected=items.filter(r=>r.release_id===i&&r.release_id%2===0);
  assert.deepEqual(index.get(i)?.rows||[],expected);
  if(expected.length){assert.equal(index.get(i).bestGross,Math.max(...expected.map(r=>Number(r.gross_twd))));assert.equal(index.get(i).bestMargin,Math.max(...expected.map(r=>r.gross_margin)))}
 }
 assert.equal(checks,10000);assert.equal(items.length,10000);
 const mixed=buildRecordIndex([{...base,release_id:1,gross_twd:null,gross_margin:null},{...base,release_id:1,gross_twd:'-10',gross_margin:-0.1},{...base,release_id:2,source_format:'Vinyl'},{...base,release_id:3,excluded:true}],()=>true);
 assert.equal(mixed.size,1);assert.equal(mixed.get(1).bestGross,-10);assert.equal(mixed.get(1).bestMargin,-0.1);
});
