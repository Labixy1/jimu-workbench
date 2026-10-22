'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const raw=fs.readFileSync(path.join(root,'web/showcase-data.json'),'utf8');
const data=JSON.parse(raw);
assert(!/sk-[a-zA-Z0-9_-]{16,}|Bearer [a-zA-Z0-9_-]{16,}|\.runtime\/|\/Users\/yangleduo/.test(raw),'public bundle must not expose credentials or local runtime paths');
assert.equal(data.provenance.kind,'real-model-replay');
assert.equal(data.provenance.captured_on,'2026-10-21');
assert.equal(data.state.sources.length,data.provenance.source_ids.length);
assert(data.state.sources.length>=5);
assert.equal(data.state.artifacts.length,4);
assert.equal(data.state.conversations.length,4);
assert(data.state.sources.every(s=>s.visibility==='public'));
assert(!raw.includes('src_7b423f4f0df64802'));
assert(!raw.includes('参照虚构演示JD'));
assert.equal(data.state.artifacts.filter(a=>a.kind==='board').length,2);
assert(data.state.artifacts.filter(a=>a.kind==='board').every(a=>a.body.generated_graph&&a.body.edited_graph));
assert(data.state.reading.favorites.includes('board_1e9dcf42a0484e8b'));
assert(data.state.reading.favorites.includes('board_9be85468d7ee4598'));
assert(data.state.reading.issues.length>=1);
assert(data.state.jobs.some(j=>j.status==='failed'),'genuine errors stay in the replay');
const correctedChat=data.messages.conv_034dd09284ed4bb6.filter(m=>m.role==='assistant');
assert(correctedChat.length>=2,'keep the initial answer and follow-up correction');
assert.equal(data.state.model_status.key_configured,false);
assert.equal(data.state.weekly.config.enabled,false);
assert.equal(data.sites.length,5);
for(const job of data.state.jobs){
 assert(!job.payload.packet&&!job.payload.history);
 assert(!job.payload.history_snapshot&&!job.payload.preferences_snapshot&&!job.payload.artifact_snapshot);
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
 assert.equal((await (await ctx.window.fetch('/api/reading/items')).json()).length,0);
 assert.equal(network,1,'no API request reaches the backend');
 console.log('PASS whitelist public bundle, read-only Request/string writes, no API calls');
})().catch(error=>{console.error(error);process.exitCode=1;});
