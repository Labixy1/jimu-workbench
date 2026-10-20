'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),output={innerHTML:''},indicator={textContent:''};
const subscriptions=[1,2,3].map(n=>({id:'sub_'+n,title:'主题'+n,urls:['https://example.com/'+n],enabled:false,frequency:n===2?'daily':'weekly',weekday:4,time:'19:00',revision:1}));
const wiki=[{id:'page_one',title:'第一页',updated:'2026-10-19',body:{tags:['周刊','旧名称'],summary:'正文'}}];
const ctx=vm.createContext({URL,document:{addEventListener(){},querySelectorAll(){return[]}},
 $:s=>s==='#work-content'?output:s==='#schedule-indicator'?indicator:{},esc:s=>String(s),view:'work',pages:()=>wiki,
 state:{conversations:[],weekly:{subscriptions,page_subscriptions:{page_one:'sub_2'},runs:[]}}});
vm.runInContext(fs.readFileSync(path.join(root,'web/desk.js'),'utf8'),ctx);
ctx.renderDesk();assert(output.innerHTML.includes('3 / 3'));assert(output.innerHTML.includes('data-weekly-new disabled'));
assert.equal((output.innerHTML.match(/class="reading-subscription-card/g)||[]).length,3);
assert(output.innerHTML.includes('第一页'));assert(output.innerHTML.includes('手动更新'));
assert(!output.innerHTML.includes('data-subscription-toggle'));assert(!output.innerHTML.includes('每天 19:00'));
vm.runInContext("readingFilter='sub_1'",ctx);ctx.renderDesk();assert(!output.innerHTML.includes('第一页'));
vm.runInContext("readingFilter='sub_2'",ctx);ctx.renderDesk();assert(output.innerHTML.includes('第一页'));
subscriptions[1].title='改名后的主题';ctx.renderDesk();assert(output.innerHTML.includes('第一页'),'persistent association does not depend on titles');
subscriptions.splice(1,1);ctx.renderDesk();assert.equal(vm.runInContext('readingFilter',ctx),'all');assert(output.innerHTML.includes('第一页'));
ctx.state.weekly.runs=[{id:'issue',subscription_id:'sub_1',status:'collecting',created:'2026-10-19',config:subscriptions[0]}];
ctx.renderDesk();assert(output.innerHTML.includes('data-news-refresh="sub_3" disabled'));
console.log('PASS three-card limit, independent filters, rename/remove preserve reading and serial update state');
