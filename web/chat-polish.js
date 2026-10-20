'use strict';
const executionExpanded=new Set();
function executionMarkup(j){
 if(!j)return '';
 const busy=['queued','running'].includes(j.status),bad=['failed','interrupted'].includes(j.status);
 const labels={queued:'等待执行',running:'正在处理',review:j.payload.output_board?'画板已生成':'文稿已生成',approved:'成果已保存',done:'已完成',failed:'执行失败',interrupted:'已中断',rejected:'未保存'};
 const stages=j.payload.stages||[],current=stages.find(s=>s.status==='running');
 const agents={workbench:'主 Agent',researcher:'研究子 Agent',reviewer:'核对子 Agent'};
 return `<details class="turn-execution ${bad?'execution-failed':''} ${busy?'execution-running':''}" data-execution-id="${esc(j.id)}" ${executionExpanded.has(j.id)?'open':''}><summary><span class="execution-indicator">${busy?'◌':bad?'!':'✓'}</span><span>${esc(current?current.name:labels[j.status]||j.status)}</span><span class="execution-count">${stages.length?stages.length+' 个步骤':''}</span><span class="execution-chevron">⌄</span></summary><div class="execution-body">${(j.payload.skill_snapshot||[]).length?`<div class="execution-skill-list">${j.payload.skill_snapshot.map(s=>`<span>技能 · ${esc(s.title)}</span>`).join('')}</div>`:''}${stages.map(s=>`<div class="execution-step"><span class="step-dot ${esc(s.status)}"></span><div><strong>${esc(agents[s.agent]||s.agent||'积木')}</strong><p>${esc(s.name)}</p>${s.interface?`<small>${esc(s.interface)}</small>`:''}${(s.tools||[]).map(t=>`<small>工具 · ${esc(t.name)} · ${esc(t.status)}</small>`).join('')}</div><span>${{done:'完成',running:'执行中',failed:'失败'}[s.status]||esc(s.status)}</span></div>`).join('')}${j.payload.context_meta?`<div class="execution-meta">本次引用 ${j.payload.context_meta.source_count||0} 份材料、${j.payload.context_meta.knowledge_count||0} 份文稿、${j.payload.context_meta.board_count||0} 个画板；近期对话按上下文预算带入。</div>`:''}</div></details>`;
}
function renderMessages(){
 const signature=JSON.stringify([messages,state.jobs.filter(j=>j.conversation_id===cid).map(j=>[j.id,j.status,j.payload.stages,j.payload.error,j.payload.user_draft,j.payload.proposal]),[...executionExpanded]]);
 if(signature===lastSignature)return;
 const thread=$('.chat-thread'),follow=thread.scrollHeight-thread.clientHeight-thread.scrollTop<120;lastSignature=signature;
 $('#messages').innerHTML=messages.map((m,i)=>{
 const j=state.jobs.find(j=>j.id===m.job_id),bad=m.role==='assistant'&&['failed','interrupted'].includes(j?.status);
  if(m.role==='user'){
   const p=j?.payload||{},refs=[...(p.source_ids||[]).map(id=>({name:p.source_snapshot?.[id]?.title||state.sources.find(s=>s.id===id)?.title||'材料',type:'文件'})),...(p.document_snapshot||[]).map(a=>({name:a.title,type:'文稿'})),...(p.board_snapshot||[]).map(a=>({name:a.title,type:'画板'})),...(p.skill_snapshot||[]).map(a=>({name:a.title,type:'技能'}))];
   return `<article class="message user"><div class="user-message-text">${esc(m.text)}</div>${refs.length?`<div class="message-references">${refs.map(r=>`<span title="${esc(r.type+' · '+r.name)}">${esc(r.name)}</span>`).join('')}</div>`:''}</article>`;
  }
  return `<article class="message assistant ${bad?'message-error':''}">${executionMarkup(j)}${bad?`<div class="chat-error" role="alert"><strong>这次请求未完成</strong><p>${esc(j.payload.error||m.text)}</p></div>`:`<div class="markdown">${md(m.text)}</div>`}<div class="message-actions">${!bad?`<button class="text-button" data-copy-response="${i}" aria-label="复制回答" title="复制回答">复制</button>${j?.payload.kind==='chat'?`<button class="text-button save-answer" data-save-message="${i}">存为文稿</button>`:''}`:''}</div>${turnFileMarkup(j)}</article>`;
 }).join('');
 if(follow)requestAnimationFrame(()=>thread.scrollTop=thread.scrollHeight);
}
function turnFileMarkup(j){
 if(!j||!['review','approved'].includes(j.status))return '';
 const f=proposalFile(j);if(!f)return '';
 return `<button class="chat-file-card" data-open-job-file="${esc(j.id)}"><svg class="icon"><use href="#i-book"/></svg><span><strong>${esc(f.title)}${j.payload.output_board?'.excalidraw':'.md'}</strong><small>${j.payload.output_board?'画板':'Markdown'} · ${j.status==='approved'?'已加入资产':'打开查看'}</small></span><span>↗</span></button>`;
}
const originalChatReview=renderReview;
renderReview=function(){
 originalChatReview();
 const j=job();
 if(j&&messages.some(m=>m.role==='assistant'&&m.job_id===j.id)){
  $('#review-panel').hidden=true;$('#review-panel').innerHTML='';
 }
};
function renderProgress(){
 const j=job(),busy=j&&['queued','running'].includes(j.status);$('#send-button').disabled=submitting||!!busy;
 const hasResponse=messages.some(m=>m.role==='assistant'&&m.job_id===j?.id);
 const sig=JSON.stringify(j?[j.id,j.status,j.payload.stages,j.payload.error,hasResponse]:null);if(sig===progressSignature)return;progressSignature=sig;
 $('#job-progress').innerHTML=busy?`<div class="live-execution">${executionMarkup(j)}<button class="text-button stop-generation" data-cancel="${esc(j.id)}">停止</button></div>`:j&&!hasResponse?executionMarkup(j)+(j.payload.error?`<div class="chat-error" role="alert"><strong>这次请求未完成</strong><p>${esc(j.payload.error)}</p></div>`:''):'';
}
document.addEventListener('toggle',e=>{const id=e.target.dataset?.executionId;if(!id)return;e.target.open?executionExpanded.add(id):executionExpanded.delete(id);},true);
document.addEventListener('click',async e=>{const b=e.target.closest('[data-copy-response]');if(!b)return;try{await navigator.clipboard.writeText(messages[Number(b.dataset.copyResponse)].text);b.textContent='已复制';setTimeout(()=>{if(b.isConnected)b.textContent='复制';},1500);}catch{toast('复制失败，请选择正文复制');}});
$('#prompt').addEventListener('input',e=>{e.target.style.height='auto';e.target.style.height=Math.min(190,Math.max(64,e.target.scrollHeight))+'px';});
$('#prompt').addEventListener('keydown',e=>{
 if(e.key!=='Enter'||e.shiftKey||e.isComposing)return;
 e.preventDefault();
 if(!$('#send-button').disabled)$('#composer').requestSubmit();
});
$('#composer').onsubmit=async e=>{
 e.preventDefault();
 $('#chat-send-error')?.remove();
 try{await submit();}catch(err){
  const box=document.createElement('div');box.id='chat-send-error';box.className='chat-error';box.setAttribute('role','alert');
  box.textContent=err.message;$('#composer').before(box);
 }
};
const originalNewChat=$('#new-chat').onclick;
$('#new-chat').onclick=async e=>{
 await originalNewChat(e);
 if(!cid)$('#chat-send-error')?.remove();
};
const originalChatRender=render;
render=function(){
 originalChatRender();
 if(cid)$('#chat-send-error')?.remove();
 $('#prompt').placeholder=kind==='document'?'描述这份文稿要怎么修改…':'问一个问题，或带上你的资料…';
 if(!$('#prompt').value)$('#prompt').style.height='64px';
};
