import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import ts from 'typescript';
const source=await readFile(new URL('../app/page.tsx',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const realRequire=createRequire(import.meta.url);
const queueSource=await readFile(new URL('../lib/refresh-queue.ts',import.meta.url),'utf8');
const queueExports={};new Function('exports',ts.transpileModule(queueSource,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(queueExports);
function harness(post){
 const record={release_id:42,artist:'Artist',title:'Album',format:'CD',history:[],analysis:null,cost:null,snapshot:{currency:'USD',lowest_price:'30'},decision:{decision:'watch',target_price:'3000',target_currency:'JPY'}};
 const state={csrf:'test',records:[record],workflow:{comparisons:[],drafts:[],offers:[]},configured:{discogs:true},jobs:[],targets:[],fx:[],active:null,schedule:{times:[]}};
 const slots=[];let cursor=0;
 const hooks={useEffect:()=>{},useCallback:fn=>fn,useRef:value=>{const i=cursor++;return slots[i]??={current:value}},useState:value=>{const i=cursor++;if(!(i in slots))slots[i]=i===0?state:typeof value==='function'?value():value;return [slots[i],next=>{slots[i]=typeof next==='function'?next(slots[i]):next}]}};
 const exports={};new Function('require','exports',js)(id=>{
  if(id==='react')return hooks;
  if(id==='@/lib/refresh-queue')return queueExports;
  if(id==='@/lib/api')return {accessRevision:()=>0,hosted:false,apiOrigin:'',apiFetch:(path,opts)=>opts?.method==='POST'?post(path,opts):Promise.resolve({ok:true,status:200,json:async()=>state})};
  if(id==='@/lib/use-price-filter')return {usePriceFilter:()=>({minimum:0})};
  if(id==='@/lib/comparison-sort')return {buildRecordIndex:()=>new Map([[42,{rows:[{format:'CD'}],bestGross:1,bestMargin:.1}]])};
  if(id==='@/components/record-status')return {default:()=>null,listedReleaseIds:()=>new Set(),matchesListingStatus:()=>true};
  if(id.startsWith('@/'))return {default:()=>null,Button:()=>null};
  return realRequire(id);
 },exports);
 return {render:()=>{cursor=0;return exports.default()}};
}
function find(node,predicate){
 if(!node)return;
 if(Array.isArray(node)){for(const child of node){const hit=find(child,predicate);if(hit)return hit}return}
 if(predicate(node))return node;
 return find(node.props?.children,predicate);
}
const byType=type=>node=>node.type===type;
const text=value=>node=>node.props?.children===value||(Array.isArray(node.props?.children)&&node.props.children.includes(value));
const event=()=>({preventDefault(){},currentTarget:undefined});
test('add form sends once, blocks closing while pending and displays backend validation errors',async()=>{
 let resolve,calls=0;
 const h=harness(()=>{calls++;return new Promise(r=>resolve=r)});
 find(h.render(),text('加入唱片')).props.onClick();
 let tree=h.render();const first=find(tree,byType('form')).props.onSubmit(event());
 await find(tree,byType('form')).props.onSubmit(event());assert.equal(calls,1);
 tree=h.render();assert.equal(find(tree,byType('fieldset')).props.disabled,true);
 find(tree,n=>n.type==='dialog'&&n.props.className==='modal').props.onCancel(event());
 assert.ok(find(h.render(),byType('form')));
 resolve({ok:false,status:400,json:async()=>({error:'版本連結無效'})});await first;
 tree=h.render();assert.equal(find(tree,byType('fieldset')).props.disabled,false);
 assert.equal(find(tree,byType('form')).props.children[0].props.children,'版本連結無效');
});
test('editing an existing watch preserves target currency rather than market currency',()=>{
 const h=harness(()=>{throw Error('no request expected')});
 find(h.render(),n=>n.type==='button'&&n.props.className==='record-row').props.onClick();
 find(h.render(),text('觀察')).props.onClick();
 const form=find(h.render(),byType('form'));
 assert.equal(find(form,n=>n.type==='select'&&n.props.name==='currency').props.defaultValue,'JPY');
 assert.equal(find(form,n=>n.type==='input'&&n.props.name==='target').props.defaultValue,'3000');
});
