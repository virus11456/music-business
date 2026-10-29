/** Coalesce polling; a forced refresh supersedes the in-flight read. */
export function createRefreshQueue<T>(read:()=>Promise<T>,apply:(value:T)=>void){
 let running:Promise<void>|null=null,queued=false;
 function refresh(force=false):Promise<void>{
  if(running){if(force)queued=true;return running}
  const drain=async()=>{
   do{
    queued=false;
    try{const value=await read();if(!queued)apply(value)}
    catch(error){if(!queued)throw error}
   }while(queued);
  };
  running=drain().finally(()=>{running=null});
  return running;
 }
 return {refresh};
}

/** Poll again only after the previous read finished; slow or failing backends get more breathing room. */
export function nextPollDelay(lastDurationMs:number,failed=false,base=4000,max=20000){
 const duration=Number.isFinite(lastDurationMs)&&lastDurationMs>0?lastDurationMs:0;
 return Math.min(max,Math.max(base,failed?base*2.5:duration*2));
}
