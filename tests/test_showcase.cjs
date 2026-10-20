'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const raw=fs.readFileSync(path.join(root,'web/showcase-data.json'),'utf8');
const data=JSON.parse(raw);
assert(!/sk-|Bearer |\.runtime\//.test(raw),'public bundle must not expose credentials or runtime paths');
assert.equal(data.state.sources.length,2);
assert.equal(data.state.artifacts.length,4);
assert.equal(data.state.model_status.key_configured,false);
assert.equal(data.state.weekly.config.enabled,false);
assert.equal(data.sites.length,5);
for(const job of data.state.jobs){
 assert(!job.payload.packet&&!job.payload.history);
 for(const stage of job.payload.stages||[])assert(!stage.session_id&&!stage.parent_id);
}
let network=0;
const ctx=vm.createContext({URL,URLSearchParams,Response,
 location:{search:'?showcase=1',href:'http://127.0.0.1:8768/?showcase=1'},
 window:{fetch:async()=>{network++;return new Response(raw);}},
 document:{addEventListener(){}},
});
vm.runInContext(fs.readFileSync(path.join(root,'web/showcase.js'),'utf8'),ctx);
(async()=>{
 assert.equal((await ctx.window.fetch('/api/state')).status,200);
 assert.equal((await (await ctx.window.fetch('/api/sites')).json()).length,5);
 assert.equal((await ctx.window.fetch('/api/jobs',{method:'POST'})).status,400);
 assert.equal((await ctx.window.fetch(new Request('http://127.0.0.1:8768/api/jobs',{method:'POST'}))).status,400);
 assert.equal((await ctx.window.fetch('/api/memory',{method:'delete'})).status,400);
 assert.equal(network,1,'no API request reaches the backend');
 console.log('PASS whitelist public bundle, read-only Request/string writes, no API calls');
})().catch(error=>{console.error(error);process.exitCode=1;});
