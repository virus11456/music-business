import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const out={};new Function('require','exports',ts.transpileModule(readFileSync(new URL('../components/media-badge.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText)(createRequire(import.meta.url),out);
test('explicit formats translate and mixed media retain all types',()=>{
 for(const [raw,expected] of [['Vinyl, LP, Album',['黑膠']],['CD, Album',['CD']],['Cassette',['卡帶']],['Vinyl, LP; CD',['黑膠','CD']],['CD + Cassette',['CD','卡帶']],[null,['格式待確認']],['DVD',['格式待確認']],['CDr',['格式待確認']]])assert.deepEqual(out.mediaLabels(raw),expected);
});
test('badges retain visible text and distinct classes',()=>{
 const html=renderToStaticMarkup(React.createElement(out.default,{format:'Vinyl, CD, Cassette'}));
 for(const text of ['商品格式','media-vinyl','media-cd','media-cassette','黑膠','CD','卡帶'])assert.ok(html.includes(text));
});
