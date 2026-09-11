'use client';
import {useEffect,useState} from 'react';
const key='simples.comparison-preferences.v1',event='simples-price-filter';
export function usePriceFilter(){
 const [pricePreset,setPreset]=useState('all'),[customMinimum,setCustom]=useState('');
 useEffect(()=>{
  const read=()=>{try{const saved=JSON.parse(localStorage.getItem(key)||'{}');if(['all','20','30','50','custom'].includes(saved.pricePreset))setPreset(saved.pricePreset);if(typeof saved.customMinimum==='string'&&/^\d{0,8}(\.\d{0,2})?$/.test(saved.customMinimum))setCustom(saved.customMinimum)}catch{}};
  read();window.addEventListener(event,read);window.addEventListener('storage',read);
  return()=>{window.removeEventListener(event,read);window.removeEventListener('storage',read)};
 },[]);
 const save=(patch:Record<string,string>)=>{try{const previous=JSON.parse(localStorage.getItem(key)||'{}');localStorage.setItem(key,JSON.stringify({...previous,...patch}));window.dispatchEvent(new Event(event))}catch{}};
 return {pricePreset,customMinimum,minimum:pricePreset==='custom'?customMinimum:pricePreset==='all'?'':pricePreset,
  setPricePreset:(value:string)=>{setPreset(value);save({pricePreset:value})},
  setCustomMinimum:(value:string)=>{setCustom(value);save({customMinimum:value})}};
}
