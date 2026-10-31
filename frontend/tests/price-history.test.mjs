import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=(await readFile(new URL('../components/price-history.tsx',import.meta.url),'utf8')).replace(/^import .*$/gm,'');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.Preserve}}).outputText.replace(/export default function[\s\S]*$/,'');
const {historyRows}=await import('data:text/javascript;base64,'+Buffer.from(output).toString('base64'));
test('history rows only accepted for the requested release',()=>{
 const body={release_id:5,history:[{captured_at:'2026-10-01T00:00:00Z',lowest_price:'10',currency:'USD'},{bad:1},null]};
 assert.deepEqual(historyRows(body,5),[body.history[0]]);
 assert.equal(historyRows(body,6),null);assert.equal(historyRows({release_id:5},5),null);assert.equal(historyRows(null,5),null);
});
