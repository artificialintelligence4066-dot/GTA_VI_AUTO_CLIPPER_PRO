const API=(import.meta.env.VITE_API_BASE||'').replace(/\/$/,'');let apiKey='';
export const setApiKey=(v)=>{apiKey=v.trim()};
export const wsUrl=()=>{const base=API||window.location.origin;const u=new URL(base.replace(/^http/,'ws')+'/ws');if(apiKey)u.searchParams.set('key',apiKey);return u.toString()};
export async function api(path,options={}){const headers={...(options.body?{'Content-Type':'application/json'}:{}),...(apiKey?{'X-API-Key':apiKey}:{}),...(options.headers||{})};const r=await fetch(API+path,{...options,headers});let data={};try{data=await r.json()}catch{}if(!r.ok)throw new Error(data.detail||`HTTP ${r.status}`);return data}
