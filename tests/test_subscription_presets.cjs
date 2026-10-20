'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const data=JSON.parse(fs.readFileSync(path.join(root,'web/showcase-data.json'),'utf8'));
const nodes=new Map([
 ['#weekly-urls',{value:''}],['#weekly-error',{textContent:''}],
 ['#weekly-presets',{innerHTML:'',querySelectorAll(){return [];}}],
]);
const ctx=vm.createContext({URL,sites:data.sites.map(s=>({...s,feed_url:s.id==='openai'?'https://openai.com/news/rss.xml':undefined})),$:s=>nodes.get(s),esc:s=>String(s),state:{weekly:{config:{enabled:false}}}});
vm.runInContext(source.slice(source.indexOf('function subscriptionSiteKey('),source.indexOf("$('#weekly-urls').addEventListener")),ctx);
ctx.renderSubscriptionPresets();
for(const name of ['OpenAI','Codex 发布','OpenCode 发布'])assert(nodes.get('#weekly-presets').innerHTML.includes(name));
const url='https://openai.com/news/rss.xml';
ctx.toggleSubscriptionSite(url);assert.equal(nodes.get('#weekly-urls').value,url);
assert(nodes.get('#weekly-presets').innerHTML.includes('aria-pressed="true"'));
ctx.toggleSubscriptionSite(url);assert.equal(nodes.get('#weekly-urls').value,'');
nodes.get('#weekly-urls').value='  '+url.replace(/\/$/,'')+' \n';
ctx.toggleSubscriptionSite(url);assert.equal(nodes.get('#weekly-urls').value,'','same site with a missing trailing slash is removed, not duplicated');
nodes.get('#weekly-urls').value=Array.from({length:8},(_,i)=>`https://example.com/${i}`).join('\n');
const original=nodes.get('#weekly-urls').value;
ctx.toggleSubscriptionSite(url);assert.equal(nodes.get('#weekly-urls').value,original);
assert(nodes.get('#weekly-error').textContent.includes('最多关注8个'));
ctx.toggleSubscriptionSite('https://example.com/0');assert.equal(nodes.get('#weekly-urls').value.split('\n').length,7);
ctx.toggleSubscriptionSite(url);assert.equal(nodes.get('#weekly-urls').value.split('\n').length,8);
assert.equal(ctx.state.weekly.config.enabled,false,'adding presets does not enable or persist subscriptions');
console.log('PASS preset names, add/remove, normalized duplicates, source limit and no auto-enable');
