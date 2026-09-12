import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createRequire} from 'node:module';import ts from 'typescript';import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';
const out={};new Function('require','exports',ts.transpileModule(readFileSync(new URL('../components/collection-progress.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText)(createRequire(import.meta.url),out);
const render=queue=>renderToStaticMarkup(React.createElement(out.default,{queue}));
test('first-pass progress separates unmatched and failed records from actual opportunities',()=>{
 const html=render({total:100,unchecked:20,statuses:{matched:10,unmatched:65,failed:5}});
 for(const text of ['80%','尚未首次反查 20','有候選匹配 10','暫未匹配 65','查詢失敗 5','不等於版本已確認或有正毛利'])assert.ok(html.includes(text),text);
 assert.ok(html.includes('value="80"'));
});
test('empty, unavailable and malformed progress never display NaN or false completion',()=>{
 assert.ok(render(undefined).includes('尚未取得'));
 const html=render({total:0,unchecked:0,statuses:{}});assert.ok(html.includes('0%'));assert.ok(!html.includes('NaN'));
 for(const queue of [{total:1,unchecked:2},{total:-1,unchecked:0},{total:NaN,unchecked:0}])assert.ok(render(queue).includes('待重新讀取'));
});
