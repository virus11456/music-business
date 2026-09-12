import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import ts from 'typescript';
const source=await readFile(new URL('../components/workflow.tsx',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const realRequire=createRequire(import.meta.url);
function harness(send){
 const slots=[];let cursor=0,closed=0;
 const hooks={useEffect:()=>{},useRef:value=>{const i=cursor++;return slots[i]??= {current:value}},useState:value=>{const i=cursor++;if(!(i in slots))slots[i]=typeof value==='function'?value():value;return [slots[i],next=>{slots[i]=typeof next==='function'?next(slots[i]):next}]}};
 const exports={};
 new Function('require','exports',js)(id=>{
  if(id==='react')return hooks;
  if(id==='@/lib/draft-filter')return {filterDrafts:()=>[]};
  if(id==='@/lib/draft-selection')return {draftSelection:()=>({}),exportIssues:()=>[]};
  if(id.startsWith('@/'))return {default:()=>null,Button:()=>null};
  return realRequire(id);
 },exports);
 const props={view:'review',initialReview:{key:'source-17',release_id:42,ready:false,offer:{id:17,amount:'350',currency:'TWD'}},workflow:{platforms:{candidates:[]},drafts:[],grades:[]},records:[],jobs:[],locked:false,onClose:()=>closed++,send};
 const render=()=>{cursor=0;return exports.default(props)};
 return {render,get closed(){return closed}};
}
function find(node,type){
 if(!node)return;
 if(Array.isArray(node)){for(const child of node){const hit=find(child,type);if(hit)return hit}return}
 if(node.type===type)return node;
 return find(node.props?.children,type);
}
const event=()=>({preventDefault(){},currentTarget:undefined});
test('pending save blocks duplicate submission and closing, failure retains the form for retry',async()=>{
 let resolve,calls=0;
 const h=harness(()=>{calls++;return new Promise(r=>resolve=r)});
 let tree=h.render();const submit=find(tree,'form').props.onSubmit;
 const first=submit(event());await submit(event());
 assert.equal(calls,1);
 tree=h.render();assert.equal(find(tree,'fieldset').props.disabled,true);
 find(tree,'dialog').props.onCancel(event());assert.equal(h.closed,0);
 resolve(false);await first;tree=h.render();
 assert.equal(find(tree,'fieldset').props.disabled,false);
 assert.ok(find(tree,'form'));assert.equal(h.closed,0);
 const children=find(tree,'form').props.children;
 assert.equal(children[0].props.role,'alert');
 assert.match(children[0].props.children,/已保留輸入內容/);
 const retry=find(tree,'form').props.onSubmit(event());assert.equal(calls,2);resolve(true);await retry;
 assert.equal(h.closed,1);assert.equal(find(h.render(),'form'),undefined);
});
test('unexpected send failure unlocks the form without dismissing it',async()=>{
 const h=harness(async()=>{throw Error('network')});
 await find(h.render(),'form').props.onSubmit(event());
 const tree=h.render();assert.equal(h.closed,0);assert.equal(find(tree,'fieldset').props.disabled,false);
 assert.equal(find(tree,'form').props.children[0].props.role,'alert');
});

test('server validation reason is shown inside the still-open form',async()=>{
 const h=harness(async(path,data,onError)=>{onError('草稿與來源報價版本不一致');return false});
 await find(h.render(),'form').props.onSubmit(event());
 assert.equal(find(h.render(),'form').props.children[0].props.children,'草稿與來源報價版本不一致');
 assert.equal(h.closed,0);
});
