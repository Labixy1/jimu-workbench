'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const nodes=new Map();
function node(selector){if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',value:'',style:{},scrollHeight:1000,clientHeight:500,scrollTop:500,addEventListener(){},remove(){}});return nodes.get(selector);}
const ctx=vm.createContext({
 $:node,document:{addEventListener(){}},requestAnimationFrame:f=>f(),
 esc:v=>String(v??'').replaceAll('<','&lt;').replaceAll('>','&gt;'),md:v=>String(v),
 state:{jobs:[],sources:[]},messages:[],cid:'conversation',lastSignature:'',progressSignature:'',submitting:false,
 job:()=>ctx.state.jobs[0],render(){},renderReview(){},proposalFile:j=>j.payload.user_draft,kind:'chat',
});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../web/chat-polish.js'),'utf8'),ctx);
const j={id:'local_ui_fixture',conversation_id:'conversation',status:'done',payload:{kind:'chat',stages:[]}};
ctx.state.jobs=[j];
ctx.renderProgress();
assert(node('#job-progress').innerHTML.includes('已完成'));
ctx.messages=[{role:'assistant',job_id:j.id,text:'Test fixture only'}];
ctx.renderProgress();
assert.equal(node('#job-progress').innerHTML,'','response arrival removes the redundant progress block');
ctx.renderMessages();
assert(node('#messages').innerHTML.includes('存为文稿'));
j.status='review';j.payload.user_draft={title:'Local fixture draft',content:'not a model result'};
ctx.renderMessages();assert(node('#messages').innerHTML.includes('data-open-job-file'));
ctx.renderReview();assert(node('#review-panel').hidden,'file card is attached to its turn, not duplicated below');
j.status='approved';j.payload.published_id='saved-fixture';ctx.state.artifacts=[{id:'saved-fixture',title:'Current saved title'}];
assert(ctx.turnFileMarkup(j).includes('Current saved title'),'saved file cards follow the current asset title');
j.status='failed';j.payload.error='<script>API rejected the request</script>';
ctx.renderMessages();
assert(node('#messages').innerHTML.includes('role="alert"'));
assert(!node('#messages').innerHTML.includes('存为文稿'));
assert(!node('#messages').innerHTML.includes('<script>'));
ctx.renderProgress();assert.equal(node('#job-progress').innerHTML,'','failure is not duplicated');
j.status='running';ctx.renderProgress();
assert(node('#job-progress').innerHTML.includes('停止'));
assert(node('#send-button').disabled);
ctx.render();assert(node('#prompt').placeholder.includes('问一个问题'));
ctx.kind='document';ctx.render();assert(node('#prompt').placeholder.includes('修改'));
ctx.kind='chat';ctx.render();assert(node('#prompt').placeholder.includes('问一个问题'));
console.log('PASS polished chat: errors, escaping, duplicate progress, stop, send lock and prompt reset');
