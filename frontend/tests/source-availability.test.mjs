import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/source-availability.ts',import.meta.url),'utf8');
const exports={};new Function('exports',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports);
const {sourceAvailability,meetsSupply}=exports;
test('supply status avoids treating auction or unavailable text as stock',()=>{
 for(const availability of ['來源標示有庫存','在庫あり','在庫わずか'])assert.equal(sourceAvailability({availability}), 'stock');
 for(const availability of ['現在オンラインショップ取扱なし','お取り寄せ','予約受付中','缺貨','預購','out of stock','sold out'])assert.equal(sourceAvailability({availability}), 'unavailable');
 assert.equal(sourceAvailability({availability:'來源標示有庫存',price_kind:'current_bid'}),'auction');
 assert.equal(sourceAvailability({availability:'庫存未確認'}),'unknown');
 assert.equal(sourceAvailability({availability:'無現貨',price_kind:'current_bid'}),'unavailable');
});
test('default scope hides unavailable and auctions without declaring unknown supply in stock',()=>{
 for(const availability of ['來源標示有庫存','未確認'])assert.ok(meetsSupply({availability},'regular'));
 assert.ok(!meetsSupply({availability:'未確認'},'stock'));
 assert.ok(!meetsSupply({availability:'預購'},'regular'));
 assert.ok(!meetsSupply({price_kind:'current_bid'},'regular'));
 assert.ok(meetsSupply({availability:'預購'},'all'));
 assert.ok(meetsSupply({price_kind:'current_bid'},'auction'));
});

test('explicit ordering restrictions in real source titles override unknown or reported stock',()=>{
 for(const source_title of ['[ 沐耳 ] 披頭四 The Beatles （待補貨，勿下標） 65 年經典第六張專輯 Rubber Soul 黑膠唱片','CD 已售出','預購商品 卡帶']){
  assert.equal(sourceAvailability({source_title,availability:'來源標示有庫存'}),'unavailable');
  assert.equal(meetsSupply({source_title,availability:'未確認'},'regular'),false);
 }
 assert.equal(sourceAvailability({source_title:'Album Sold Out CD',availability:'未確認'}),'unknown');
 assert.equal(sourceAvailability({source_title:'現貨 CD',availability:'未確認'}),'unknown');
});
