/** Restores rows sent in the compact column format (state_pack.py). Unknown versions are rejected, never guessed.
 * Repeated values (e.g. evidence arrays) are shared between rows: treat restored rows as read-only. */
export const PACKED_MEDIA_TYPE='application/vnd.simples.packed+json';
type Column={d?:unknown[];i?:number[];v?:unknown[];m?:number[]};
export type Packed={version:number;n:number;f:string[];c:Record<string,Column>};

export function unpackRows(packed:Packed):Record<string,unknown>[]{
 if(!packed||packed.version!==1||!Number.isInteger(packed.n)||packed.n<0||!Array.isArray(packed.f))throw Error('資料格式不相容，請重新整理頁面');
 const columns=packed.f.map(field=>{
  const column=packed.c[field];
  if(!column)throw Error('資料格式不完整，請重新整理頁面');
  const values=column.d?column.i!.map(i=>column.d![i]):column.v!;
  if(!Array.isArray(values)||values.length!==packed.n)throw Error('資料格式不完整，請重新整理頁面');
  return {field,values,missing:column.m?.length?new Set(column.m):null};
 });
 // Build each row in one fixed key order so rows share a shape and stay fast to read.
 const rows:Record<string,unknown>[]=new Array(packed.n);
 for(let i=0;i<packed.n;i++){
  const row:Record<string,unknown>={};
  for(const {field,values,missing} of columns)if(!missing||!missing.has(i))row[field]=values[i];
  rows[i]=row;
 }
 return rows;
}

/** Accepts either the packed or the original state shape and returns the original shape. */
export function normalizeState<T>(body:T):T{
 const workflow=(body as {workflow?:Record<string,unknown>})?.workflow;
 if(!workflow||!('comparisons_packed' in workflow))return body;
 const {comparisons_packed,...rest}=workflow;
 return {...body,workflow:{...rest,comparisons:unpackRows(comparisons_packed as Packed)}} as T;
}
