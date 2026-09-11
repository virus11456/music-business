import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';import ts from 'typescript';
const exports={};new Function('exports',ts.transpileModule(await readFile(new URL('../lib/match-evidence.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(exports);
const {matchLevel,hasStrongMatch,matchLabel}=exports;
const row={format:'CD',source_format:'CD',source_catalog_no:'TOCP-1234',catalog_no:'TOCP 1234, ABC-5678',version_confirmed:false};
test('catalog normalization supports exact identifiers without confirming a pressing',()=>{
 assert.equal(matchLevel(row),'catalog');assert.ok(hasStrongMatch(row));assert.ok(matchLabel(row).includes('壓片待核對'));
 assert.equal(matchLevel({...row,source_catalog_no:'ＴＯＣＰ－１２３４'}),'catalog');
 assert.equal(matchLevel({...row,version_confirmed:true}),'confirmed');
});
test('missing, conflicting, partial identifiers and cross-format candidates are never stronger evidence',()=>{
 for(const source_catalog_no of ['', 'N/A','None','未確認','unknown','TOCP-123','TOCP-12345'])assert.equal(matchLevel({...row,source_catalog_no}),'candidate');
 assert.equal(matchLevel({...row,format:'Vinyl'}),'candidate');
 assert.equal(matchLevel({...row,catalog_no:''}),'candidate');
 assert.ok(!hasStrongMatch({...row,source_catalog_no:''}));
});
