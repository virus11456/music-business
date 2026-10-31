'use client';
import {useMemo,useState,type ReactNode} from 'react';
import MediaBadge from '@/components/media-badge';
import RecordSources from '@/components/record-sources';
import type {Comparison} from '@/components/comparison-table';
import {buildRecordIndex,hasPositiveMargin,meetsMinimumUsd,hasFreshComparison,wantHaveRatio,ratioLabel} from '@/lib/comparison-sort';
import {matchConflicts} from '@/lib/match-evidence';
import {meetsSupply} from '@/lib/source-availability';

// Want/Have belong to the Discogs release, so every comparison row of one release carries the same pair.
const demand=(rows:Comparison[])=>{const r=rows.find(x=>x.want!=null)||rows[0];return {want:r?.want??null,have:r?.have??null,ratio:r?wantHaveRatio(r.want,r.have):null}};
type RecordInfo={release_id:number;artist:string;title:string;format:string;country?:string;year?:number|null};
export default function PublicCatalog({records,rows,login,onLogin,error,onRefresh}:{records:RecordInfo[];rows:Comparison[];login:ReactNode;onLogin:()=>void;error:string;onRefresh:()=>void}){
 const [query,setQuery]=useState(''),[format,setFormat]=useState('all'),[sort,setSort]=useState('gross'),[minimum,setMinimum]=useState('0'),[fresh,setFresh]=useState(true);
 // Rows are filtered and ranked only when data or filters change; typing a search reuses them.
 const index=useMemo(()=>buildRecordIndex(rows,r=>hasPositiveMargin(r)&&!matchConflicts(r).length&&meetsMinimumUsd(r,minimum)&&meetsSupply(r,'regular')&&(!fresh||hasFreshComparison(r))&&(format==='all'||r.format===format)),[rows,minimum,fresh,format]);
 const ranked=useMemo(()=>{
  const rank=(id:number)=>{const entry=index.get(id);return sort==='want'?Math.max(...(entry?.rows.map(r=>r.want??0)||[0])):sort==='ratio'?demand(entry?.rows||[]).ratio??-1:sort==='margin'?entry?.bestMargin??0:entry?.bestGross??0};
  return records.filter(r=>index.has(r.release_id)).sort((a,b)=>rank(b.release_id)-rank(a.release_id)||a.release_id-b.release_id);
 },[records,index,sort]);
 const needle=query.toLowerCase();
 const visible=needle?ranked.filter(r=>`${r.artist} ${r.title} ${r.release_id}`.toLowerCase().includes(needle)):ranked;
 return <div className="app-shell"><main style={{marginLeft:0,width:'100%'}}><div className="content"><div className="page-heading"><div><p className="eyebrow">SIMPLES / RECORD BUSINESS</p><h1>唱片與貨源</h1><p>免登入瀏覽 · 只列出已配對、正毛利的版本候選。</p></div><button className="btn secondary" onClick={onLogin}>{login?'收起登入':'管理者登入'}</button></div>{login}{error&&<div className="alert" role="alert">{error}<button onClick={onRefresh}>重試</button></div>}<section className="panel"><div className="record-filter-controls"><label className="field"><span>搜尋唱片</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="歌手、專輯或版本 ID"/></label><label className="field"><span>商品類型</span><select value={format} onChange={e=>setFormat(e.target.value)}><option value="all">全部類型</option><option value="Vinyl">黑膠</option><option value="CD">CD</option><option value="Cassette">卡帶</option></select></label><label className="field"><span>最低 Discogs 參考價</span><select value={minimum} onChange={e=>setMinimum(e.target.value)}><option value="0">不限售價</option><option value="20">US$20 以上</option><option value="30">US$30 以上</option><option value="50">US$50 以上</option></select></label><label className="field"><span>排序</span><select value={sort} onChange={e=>setSort(e.target.value)}><option value="gross">毛利：高到低</option><option value="margin">毛利率：高到低</option><option value="want">Want：多到少</option><option value="ratio">Want／Have 比：高到低（想要的人多、擁有的人少）</option></select></label><label className="check-field"><input type="checkbox" checked={fresh} onChange={e=>setFresh(e.target.checked)}/>只看近 48 小時資料</label></div><div className="panel-foot">{visible.length} 張專輯版本 · Want 為收藏需求數；參考掛牌價不是成交價，預估毛利尚未扣除全部費用。採購與上架資料限管理者查看。</div>{visible.map(r=><article className="record-with-sources" key={r.release_id}><div className="section-title"><div><h2>{r.artist} — {r.title}</h2><p><MediaBadge format={r.format}/> {r.country} · {r.year||'年份未提供'} · Want {Math.max(...index.get(r.release_id)!.rows.map(c=>c.want??0))} 人 · Have {demand(index.get(r.release_id)!.rows).have??'—'} 人 · 比值 {ratioLabel(demand(index.get(r.release_id)!.rows).ratio)}</p></div><a className="text-button" href={`https://www.discogs.com/release/${r.release_id}`} target="_blank" rel="noreferrer">核對 Discogs 版本 ↗</a></div><RecordSources rows={index.get(r.release_id)!.rows} sortBy={sort==='margin'?'margin':'gross'} locked/></article>)}{!visible.length&&<div className="empty"><h2>目前沒有符合條件的唱片</h2><p>可調整格式、最低售價或資料時效篩選。</p></div>}</section></div></main></div>;
}
