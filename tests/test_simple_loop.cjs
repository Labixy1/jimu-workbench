'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('web/index.html','utf8'),app=fs.readFileSync('web/app.js','utf8');
const assets=html.slice(html.indexOf('id="sources-view"'),html.indexOf('</main>'));
assert(!assets.includes('data-asset-tab'));
assert(html.includes('data-output-tab="boards"'));
assert(html.includes('data-output-tab="career"'));
assert(!html.includes('id="send-disclosure"'), 'chat stays free of persistent API explanations');
assert(!html.includes('class="settings-footnote"'), 'settings do not repeat the removed API explanation');
assert(!html.includes('id="weekly-enabled"'));
assert(!html.includes('id="weekly-frequency"'));
const block=app.slice(app.indexOf('async function submit()'),app.indexOf('function poll()'));
assert(!block.includes('confirm('),'ordinary send has no confirmation dialog');
assert(block.includes('send_to_model:true'));
assert(block.includes('board_refs:'));
assert(app.includes('conversation-kind'));
const nodes=new Map([['#prompt',{value:'hello'}],['#use-retrieval',{checked:false}],['#send-button',{disabled:false}]]);
let sent=0,lastBody;
const ctx=vm.createContext({$:s=>nodes.get(s),state:{settings:{mode:'model'},model_status:{}},
 sourceIds:new Set(),wikiIds:new Set(),boardRefs:new Map(),skillRefs:new Map(),documentRefs:new Map(),websiteRefs:new Map(),kind:'chat',cid:null,targetId:null,submitting:false,renderProgress(){},
 careerNarrative:'',careerFormat:'experience',careerSelection:null,jdSelection:[],declaredGaps:'',
 retrievalItems:[],toast(){throw Error('unexpected toast')},settingsDialog(){throw Error('unexpected settings')},
 api:async (path,body)=>{sent++;lastBody=body;return{conversation_id:'test'}},load:async()=>{},poll(){}});
vm.runInContext(block,ctx);
(async()=>{await ctx.submit();assert.equal(sent,1);assert.equal(lastBody.send_to_model,true);
 assert.equal(nodes.get('#prompt').value,'');
 let resolve;ctx.api=async()=>{sent++;return new Promise(r=>resolve=r)};
 nodes.get('#prompt').value='second request';const pending=ctx.submit();await ctx.submit();assert.equal(sent,2,'double click does not submit another job');
 resolve({conversation_id:'test'});await pending;assert.equal(ctx.submitting,false);
 console.log('PASS source/output boundary, manual-only UI, direct send, double-click guard and reference payload');
})().catch(e=>{console.error(e);process.exitCode=1});
