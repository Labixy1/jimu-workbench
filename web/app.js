'use strict';
const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state={sources:[],artifacts:[],jobs:[],conversations:[],settings:{mode:'unconfigured'},model_status:{}},view='home',kind='chat',wikiTab='pages',pageId=null,cid=null,sourceIds=new Set(),wikiIds=new Set(),boardRefs=new Map(),targetId=null,editorId=null,messages=[],polling=false,submitting=false,timer,lastSignature='',webResults=[],retrievalItems=[],diagramPage=null,diagramRevision=null,editorRevision=0,lastSourcesRender="",careerNarrative="",careerFormat="experience",careerSelection=null,jdSelection=[],declaredGaps="",reviewSignature="",boardModule=null,boardId=null,boardRevision=0,boardLinked=null,boardDirty=false,sites=[],careerEditId=null,careerEditRevision=0,recentSignature="",outcomeSignature="",progressSignature="",assetTab="files",assetFilter="all",pendingFile=null,readerTarget=null;
let skillRefs=new Map(),documentRefs=new Map();
const demoSpace=false;
if(new URLSearchParams(location.search).has('space')){const realUrl=new URL(location.href);realUrl.searchParams.delete('space');history.replaceState(null,'',realUrl.pathname+realUrl.search);} 
let editorMessageId=null;
function scoped(path){return demoSpace?path+(path.includes('?')?'&':'?')+'space=demo':path;}
async function api(path,data){const r=await fetch(scoped(path),{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const b=await r.json();if(!r.ok)throw new Error(b.error||'请求失败');return b;}
function toast(t){$('#toast').textContent=t;$('#toast').classList.add('show');clearTimeout(timer);timer=setTimeout(()=>$('#toast').classList.remove('show'),4500);}
function pages(){return state.artifacts.filter(a=>a.kind==='wiki');}function map(){return state.artifacts.find(a=>a.id==='map-agent');}function job(){return state.jobs.find(j=>j.conversation_id===cid);}
function md(text){
 const inline=value=>{
  const tokens=/`([^`\n]+)`|\[\[(wiki_[a-z0-9]+)\]\]|\[([^\]\n]+)\]\((https?:\/\/[^\s<>]+)\)|\*\*([^*\n]+)\*\*/g;
  let html='',cursor=0,match;
  while((match=tokens.exec(value))){
   html+=esc(value.slice(cursor,match.index));cursor=tokens.lastIndex;
   if(match[1]!==undefined)html+='<code>'+esc(match[1])+'</code>';
   else if(match[2])html+=`<button class="text-button" data-page="${match[2]}">↗ ${esc(pages().find(p=>p.id===match[2])?.title||match[2])}</button>`;
   else if(match[3]){
    try{const url=new URL(match[4]);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error();html+=`<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(match[3])}</a>`;}
    catch{html+=esc(match[0]);}
   }else html+='<strong>'+esc(match[5])+'</strong>';
  }
  return html+esc(value.slice(cursor));
 };
 const lines=String(text??'').split('\n'),out=[];
 const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(s=>s.trim());
 for(let i=0;i<lines.length;i++){
  const l=lines[i];
  if(/^\s*```/.test(l)){
   const code=[];i++;
   while(i<lines.length&&!/^\s*```/.test(lines[i]))code.push(lines[i++]);
   out.push('<pre><code>'+esc(code.join('\n'))+'</code></pre>');continue;
  }
  if(l.includes('|')&&lines[i+1]&&/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1])){
   const head=cells(l);i+=2;const rows=[];
   while(i<lines.length&&lines[i].includes('|')){rows.push('<tr>'+cells(lines[i]).map(v=>'<td>'+inline(v)+'</td>').join('')+'</tr>');i++;}
   i--;out.push('<div class="table-scroll"><table><thead><tr>'+head.map(v=>'<th>'+inline(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>');continue;
  }
  out.push(/^\s*(?:---+|\*\*\*+)\s*$/.test(l)?'<hr>':l.startsWith('### ')?'<h4>'+inline(l.slice(4))+'</h4>':l.startsWith('## ')?'<h3>'+inline(l.slice(3))+'</h3>':l.startsWith('# ')?'<h3>'+inline(l.slice(2))+'</h3>':l.startsWith('- ')?'<p>• '+inline(l.slice(2))+'</p>':l.startsWith('> ')?'<blockquote>'+inline(l.slice(2))+'</blockquote>':l?'<p>'+inline(l)+'</p>':'');
 }
 return out.join('');
}
async function load(){state=await api('/api/state');sourceIds=new Set([...sourceIds].filter(id=>state.sources.some(s=>s.id===id)));wikiIds=new Set([...wikiIds].filter(id=>pages().some(p=>p.id===id)));boardRefs=new Map([...boardRefs].filter(([id])=>state.artifacts.some(a=>a.id===id&&a.kind==='board')));if(cid){const c=await api('/api/conversations/'+cid);messages=c.messages;}render();if(state.weekly?.runs.some(r=>['collecting','queued','running'].includes(r.status)))weeklyPoll();if(typeof watchReadingUpdates==='function')watchReadingUpdates();}
function render(){
 $('#wiki-count').textContent=pages().filter(p=>!p.body.tags.includes('周刊')).length||'';
 $('#source-count').textContent=state.library?.length||state.sources.length||'';$('#wiki-count').textContent=state.artifacts.filter(a=>['wiki','board','career','career_review'].includes(a.kind)).length||'';
 const status=state.settings.mode==='deepseek'?(state.model_status.test?.passed?'DeepSeek 已验证':state.model_status.key_configured?'DeepSeek 已配置':'DeepSeek 未配置密钥'):state.settings.mode==='fixture'?'测试模式，非真实模型':state.settings.mode==='model'?'自定义模型':'模型未连接';
 $('#connection-label').textContent=status;
 $('#settings-button').title=status;
 $('#composer-model').textContent=state.settings.mode==='deepseek'?'DeepSeek':state.settings.mode==='fixture'?'测试模型':state.settings.mode==='model'?'自定义模型':'未连接模型';
 $('#mode-badge').classList.toggle('connected',state.model_status.test?.passed===true);
 $('#mode-badge').classList.toggle('fixture',state.settings.mode==='fixture');
 $('#test-mode').hidden=state.settings.mode!=='fixture';$('#test-mode').textContent='测试模式 · 非真实模型';$('#demo-link').hidden=true;$('.brand').href='/';
 $('#task-label').hidden=kind==='chat';$('#task-clear').hidden=kind==='chat';$('#task-label').textContent=kind==='experience'&&careerFormat==='resume'?'写简历':{wiki:'整理材料',experience:'梳理经历',tailor:'对照岗位',draft:'修改地图'}[kind]||'';
 const recent=state.conversations.filter(c=>state.jobs.some(j=>j.conversation_id===c.id&&(state.settings.mode==='fixture'||j.payload.mode!=='fixture'&&j.payload.execution_settings?.mode!=='fixture'))).slice(0,8);
 $('#recent-section').hidden=!recent.length;syncKnowledgeDirectory();$('#knowledge-nav-title').textContent=wikiTab==='weekly'?'周刊阅读':'我的文档';$('#wiki-ai').hidden=wikiTab==='weekly';
 const rs=JSON.stringify([recent,cid]);if(rs!==recentSignature){recentSignature=rs;$('#conversations').innerHTML=recent.map(c=>`<button data-conversation="${c.id}" class="${c.id===cid?'active':''}" title="${esc(c.title)}"><span class="conversation-topic">${esc(c.title)}</span></button>`).join('');}
 if(kind==='draft'&&!$('#task-kind option[value="draft"]'))$('#task-kind').insertAdjacentHTML('beforeend','<option value="draft">更新学习图</option>');if(kind!=='draft')$('#task-kind option[value="draft"]')?.remove();$('#task-kind').value=kind;
 renderCareerContext();$('#home-view').classList.toggle('has-conversation',messages.length>0||!!job());
 $('#target-note').textContent=targetId?'更新：'+(pages().find(p=>p.id===targetId)?.title||'知识页'):'';
 $('#source-chips').innerHTML=state.sources.filter(s=>sourceIds.has(s.id)).map(s=>`<button type="button" data-unselect-source="${s.id}" title="移除 ${esc(s.title)}">${esc(s.title)} ×</button>`).join('')+pages().filter(p=>wikiIds.has(p.id)).map(p=>`<button type="button" data-unselect-wiki="${p.id}" title="移除 ${esc(p.title)}">${esc(p.title)} ×</button>`).join('')+[...boardRefs.keys()].map(id=>`<button type="button" data-unselect-board="${id}">画板 · ${esc(state.artifacts.find(a=>a.id===id)?.title)} ×</button>`).join('');
 const conversationTitle=view==='home'&&cid?state.conversations.find(c=>c.id===cid)?.title:'';
 $('#page-name').textContent=conversationTitle||'';$('#page-name').hidden=!conversationTitle;renderMessages();renderProgress();renderReview();if(view==='sources')renderSources();if(view==='wiki')renderWiki();if(view==='outputs')renderOutputLibrary();if(view==='work'&&typeof renderDesk==='function')renderDesk();if(typeof renderFramework==='function')renderFramework();
}
function renderMessages(){const signature=JSON.stringify(messages);if(signature===lastSignature)return;const thread=$('.chat-thread'),follow=thread.scrollHeight-thread.clientHeight-thread.scrollTop<96;lastSignature=signature;$('#messages').innerHTML=messages.map((m,i)=>`<div class="message ${esc(m.role)}">${m.role==='assistant'?'<span class="message-label"><svg class="icon" aria-hidden="true"><use href="#i-cube"/></svg>积木</span>':''}${m.role==='assistant'?'<div class="markdown">'+md(m.text)+'</div>':esc(m.text)}${m.role==='assistant'&&state.jobs.find(j=>j.id===m.job_id)?.payload.kind==='chat'?'<button class="text-button save-answer" data-save-message="'+i+'"><svg class="icon" aria-hidden="true"><use href="#i-book"/></svg>存为文稿</button>':''}</div>`).join('');if(follow)requestAnimationFrame(()=>thread.scrollTop=thread.scrollHeight);}
function renderProgress(){
 const j=job();$('#send-button').disabled=submitting||!!(j&&['queued','running'].includes(j.status));
 const signature=JSON.stringify(j?[j.id,j.status,j.payload.stages,j.payload.error,j.payload.mode,j.payload.context_meta]:null);if(signature===progressSignature)return;progressSignature=signature;
 if(!j){$('#job-progress').innerHTML='';return;}
 const names={queued:'等待执行',running:'正在处理',review:'文稿已生成',approved:'已确认保存',failed:'未完成',interrupted:'已中断',rejected:'未采纳',done:'回答完成'},meta=j.payload.context_meta;
 const context=meta?`<details class="execution-context"><summary>本次依据与分工</summary><p>${meta.source_count} 份资料 · ${meta.knowledge_count} 份文稿 · ${meta.board_count||0} 个画板 · 约 ${Number(meta.characters).toLocaleString('zh-CN')} 字符（不是 Token）。</p><p>历史只带入最近 ${meta.history.messages_included} 条；更早的 ${meta.history.messages_omitted} 条仍保存在对话中，但没有发送给模型。${meta.history.messages_shortened?'其中 '+meta.history.messages_shortened+' 条长消息仅带入前1200字符。':''}</p><p>${j.payload.task_method?'本次方法：'+esc(j.payload.task_method.name)+'。':''}普通问答由主 Agent 回答。整理任务由研究子 Agent 提取证据，主 Agent 编写，核对子 Agent 检查；子 Agent 不继承聊天历史与偏好。后端另做逐字引用与版本校验，生成后可预览修改，由你选择是否加入资产。</p></details>`:'';
 $('#job-progress').innerHTML=`<div class="progress-head"><strong>${names[j.status]}${j.payload.mode==='fixture'?' · 非 AI 测试':''}</strong><div>${['queued','running'].includes(j.status)?`<button class="text-button" data-cancel="${j.id}">中断</button>`:''}${j.status==='review'?'<button class="text-button" data-show-review>打开文稿 ↓</button>':''}<button class="text-button" data-archive="conversation:${j.conversation_id}">归档</button></div></div>${(j.payload.stages||[]).map(s=>`<div class="stage ${esc(s.status)}"><span>${esc(s.name)}<small class="agent-role">${{researcher:'研究子 Agent',reviewer:'核对子 Agent',workbench:'主 Agent'}[s.agent]||''}</small>${s.interface?'<small class="stage-interface">'+esc(s.interface)+'</small>':''}${(s.tools||[]).map(t=>'<small class="stage-interface">工具 · '+esc(t.name)+' · '+esc(t.status)+'</small>').join('')}</span><span>${{done:'完成',running:'执行中',failed:'失败'}[s.status]||s.status}</span></div>`).join('')}${(j.payload.skill_snapshot||[]).length?'<div class="stage-skills">已加载技能：'+j.payload.skill_snapshot.map(s=>esc(s.title)).join('、')+'</div>':''}${context}${j.payload.error?'<p class="error">'+esc(j.payload.error)+'</p>':''}`;
}
function quote(c){const s=state.sources.find(s=>s.id===c.source_id);return `<div class="source-quote"><button data-source="${c.source_id}">原文依据 · ${esc(s?.title||'已归档来源')} ↗</button>“${esc(c.quote)}”</div>`;}
function renderReview(){const j=job();const panel=$('#review-panel');panel.hidden=!j||j.status!=='review';if(j&&['experience','tailor'].includes(j.payload.kind)&&!panel.hidden){renderCareerReview(j);return;}if(j?.payload.kind==='document'&&!panel.hidden){renderDocumentReview(j);return;}reviewSignature='';if(panel.hidden){panel.innerHTML='';return;}let body='';const wiki=j.payload.kind==='wiki';if(wiki){const p=j.payload.proposal.page;const old=j.payload.wiki_target_snapshot;body=`<div class="review-columns"><div><div class="review-label">${old?'原有知识页':'新建知识页'}</div>${old?md(old.body.content):'<p class="hint">不会覆盖原文。</p>'}</div><div><div class="review-label">草稿</div><h3>${esc(p.title)}</h3><p class="hint">${esc(p.summary)}</p><div class="markdown">${md(p.content)}</div>${p.citations.map(quote).join('')}</div></div>`;}else{body=j.payload.proposal.changes.map(c=>{const old=j.payload.artifact_snapshot.body.modules.find(m=>m.id===c.module_id);return `<h3>${esc(old.title)}</h3><div class="review-columns"><div><div class="review-label">修改前</div><div class="markdown">${md(old.summary+'\n'+old.points.join('\n'))}</div></div><div><div class="review-label">建议修改</div><div class="markdown">${md(c.summary+'\n'+c.points.join('\n'))}</div><p class="hint">电商产品：${esc(c.commerce)}</p>${c.citations.map(quote).join('')}</div></div>`;}).join('');}panel.innerHTML=`<div class="review-heading"><div><h2>${wiki?'确认草稿':'确认地图修改'}</h2></div><span class="hint">尚未入库</span></div><p class="review-warning">${j.payload.mode==='fixture'?'这是固定测试输出，不是 AI 分析。':'引用匹配不等于结论正确。请检查理解、依据与适用边界。'}</p>${body}${saveDestinationMarkup(j)}<div class="review-actions"><button class="secondary" data-reject="${j.id}">不采纳</button><button class="primary" data-approve="${j.id}">${wiki?'保存文稿':'保存地图'} ↗</button></div>`;}
function renderWiki(){renderKnowledge();}
function renderSources(){renderAssetCatalog();}
function closeSidebar(){
 const collapsed=document.body.classList.contains('sidebar-collapsed');
 $('#sidebar').hidden=false;
 $('#sidebar').inert=false;
 $('#sidebar-backdrop').hidden=true;
 $('#menu').setAttribute('aria-expanded',String(!collapsed));
 $('#menu').setAttribute('aria-label',collapsed?'展开导航':'收起导航');
 $('#sidebar-toggle').setAttribute('aria-label',collapsed?'展开导航':'收起导航');
 $('#sidebar-toggle').title=collapsed?'展开侧边栏':'收起侧边栏';
}
async function switchView(v){
 if(view==='sources'&&v!=='sources'&&typeof leaveAssetFile==='function'&&!await leaveAssetFile())return false;
 if(v==='wiki'||v==='outputs'){if(pageId){await openDocument(pageId);return true;}v='sources';}
 view=v;['home','wiki','outputs','sources','skills','work'].forEach(k=>$('#'+k+'-view').hidden=k!==v);
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===v));
 $('#page-name').textContent='';$('#new-chat').classList.toggle('active',v==='home');closeSidebar();render();return true;
}
function confirm(title,text){$('#confirm-title').textContent=title;$('#confirm-text').textContent=text;$('#confirm-dialog').showModal();return new Promise(resolve=>{const done=v=>{$('#confirm-dialog').close();resolve(v);};$('#confirm-ok').onclick=()=>done(true);$('#confirm-cancel').onclick=()=>done(false);$('#confirm-dialog').oncancel=()=>done(false);$('#confirm-dialog [data-close]').onclick=()=>done(false);});}
function sourceDialog(mode='file'){
 $('#source-form').reset();pendingFile=null;populateSourceCategories();$('#source-file').value='';$('#file-import-status').textContent='';$('#source-error').textContent='';
 setSourceMode(mode);if(!$('#source-dialog').open)$('#source-dialog').showModal();
}
function updateContextBudget(){
 const chars=[...sourceIds].reduce((n,id)=>n+(state.sources.find(x=>x.id===id)?.content.length||0),0)+[...wikiIds].reduce((n,id)=>n+(pages().find(x=>x.id===id)?.body.content.length||0),0)+[...boardRefs.keys()].reduce((n,id)=>n+(state.artifacts.find(a=>a.id===id)?.body.scene.elements.filter(e=>e.type==='text'&&!e.isDeleted).map(e=>e.text||'').join('\n').length||0),0);
 $('#context-budget').textContent=`已选 ${sourceIds.size} 份资产、${wikiIds.size} 份文稿、${boardRefs.size} 个画板 · 正文约 ${chars.toLocaleString('zh-CN')} 字符。超过36000字符会拒绝，不会偷偷截断材料。`;
 $('#context-error').textContent=sourceIds.size>5||wikiIds.size>5||boardRefs.size>3?'最多5份资产、5份文稿、3个画板。':chars>32000?'材料较长，建议先检索选取片段。':'';
}
function contextDialog(){renderReferencePicker();$('#context-dialog').showModal();}
function settingsDialog(){$('#model-id').value=state.settings.mode==='deepseek'?state.settings.model:'deepseek-flash';$('#model-key').value='';$('#settings-error').textContent='';$('#key-status').textContent=state.model_status.key_configured?'已配置密钥。留空表示不更改。':'尚未配置密钥；填入后才能真正调用。';$('#preferences').value=state.memory?.instructions||'';$('#memory-error').textContent='';$('#memory-status').textContent=state.memory?.instructions?'已保存到本机':'尚未设置';$('#settings-dialog').showModal();selectSettingsTab('model');refreshUsage();}
async function saveSettings(){if($('#model-key').value.trim()){await api('/api/model/key',{key:$('#model-key').value.trim()});$('#model-key').value='';}await api('/api/settings',{mode:'deepseek',model:$('#model-id').value});await load();}
function editWiki(id=null){editorMessageId=null;editorId=id;$('#wiki-category').innerHTML=assetSaveOptions(state.library?.find(a=>a.id===id)?.category_id||(libraryCategory==='all'||libraryCategory==='ai-generated'?'':libraryCategory),libraryOrigin);const p=pages().find(a=>a.id===id);editorRevision=p?.revision||0;$('#editor-title').textContent=p?'编辑文稿':'新建文稿';$('#wiki-title').value=p?.title||'';$('#wiki-summary').value=p?.body.summary||'';$('#wiki-content').value=p?.body.content||'';$('#wiki-tags').value=p?.body.tags.join(', ')||'';$('#wiki-error').textContent='';$('#wiki-link-options').innerHTML='<p class="hint">关联已有文稿（可选）</p>'+pages().filter(a=>a.id!==id).map(a=>`<label class="context-option"><input type="checkbox" data-editor-link="${a.id}" ${p?.body.links.includes(a.id)?'checked':''}><span>${esc(a.title)}</span></label>`).join('');$('#wiki-editor').showModal();}
async function submit(){if(submitting)return;const prompt=$('#prompt').value.trim();if(!prompt)return toast('先描述要解决的问题');if(state.settings.mode==='unconfigured'||state.settings.mode==='deepseek'&&!state.model_status.key_configured){settingsDialog();return;}retrievalItems=[];if(['wiki','draft'].includes(kind)&&!sourceIds.size&&!retrievalItems.some(i=>i.kind==='source')){contextDialog();return toast('请先选择至少一份原始资料');}if(kind==='experience'&&!careerNarrative){experienceDialog();return;}if(kind==='tailor'&&(!careerSelection||!jdSelection.length)){tailorDialog();return;}
 submitting=true;$('#send-button').disabled=true;try{const j=await api('/api/jobs',{conversation_id:cid,artifact_id:'map-agent',source_ids:[...sourceIds],wiki_ids:[...wikiIds],wiki_target_id:kind==='wiki'?targetId:null,prompt,kind,send_to_model:true,board_refs:[...boardRefs].map(([id,revision])=>({id,revision})),retrieval:[],skill_refs:[...skillRefs].map(([id,revision])=>({id,revision})),website_refs:[...websiteRefs.keys()],document_refs:[...documentRefs].map(([id,revision])=>({id,revision})),document_target:kind==='document'&&activeDocument?{id:activeDocument.id,revision:activeDocument.revision}:null,narrative:careerNarrative,output_format:careerFormat,career_id:careerSelection?.id,career_revision:careerSelection?.revision,jd_source_ids:jdSelection,declared_gaps:declaredGaps});cid=j.conversation_id;$('#prompt').value='';await load();poll();}finally{submitting=false;renderProgress();}}
function poll(){if(polling)return;polling=true;const tick=async()=>{try{await load();if(state.jobs.some(j=>j.status==='running'))await checkMcpPermissions();if(state.jobs.some(j=>['running','queued'].includes(j.status))){setTimeout(tick,1400);return;}polling=false;}catch(e){toast(e.message);polling=false;}};setTimeout(tick,900);}
$('#composer').onsubmit=async e=>{e.preventDefault();try{await submit();}catch(e){toast(e.message);}};
$('#source-form').onsubmit=async e=>{e.preventDefault();$('#source-submit').disabled=true;try{let r;if(sourceMode==='file'&&!pendingFile)throw Error('请先选择要上传的文件');if(pendingFile){if(pendingFile.size>67108864)throw Error('文件最多64MB');const bytes=new Uint8Array(await pendingFile.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));r=await api('/api/assets/import',{name:pendingFile.name,base64:btoa(binary),title:$('#source-title').value,category:$('#source-category').value,visibility:$('#source-visibility').value,category_id:$('#source-collection').value});if(r.artifact){$('#source-dialog').close();pendingFile=null;await load();await openBoard(r.artifact.id);return;}}else{if(!$('#source-content').value.trim())throw Error('请先粘贴内容或读取网页正文；链接不会未经预览自动保存');r=await api('/api/sources',{title:$('#source-title').value,content:$('#source-content').value,url:$('#source-url').value,visibility:$('#source-visibility').value});await api('/api/assets/meta',{id:r.source.id,category:$('#source-category').value});}await api('/api/assets/category',{id:r.source.id,category_id:$('#source-collection').value});sourceIds.add(r.source.id);$('#source-dialog').close();$('#source-form').reset();pendingFile=null;$('#file-import-status').textContent='';await load();toast(r.duplicate?'资产已经存在，已选择原资产':'资产已保存到本机');}catch(e){$('#source-error').textContent=e.message;}finally{$('#source-submit').disabled=false;}};
$('#source-file').onchange=async e=>{pendingFile=e.target.files[0]||null;$('#file-import-status').textContent=pendingFile?pendingFile.name+' · 确认保存后在本机解析':'';if(pendingFile&&!$('#source-title').value)$('#source-title').value=pendingFile.name.replace(/\.[^.]+$/,'');if(pendingFile&&!$('#source-dialog').open)$('#source-form').requestSubmit();};
$('#settings-form').onsubmit=async e=>{e.preventDefault();try{await saveSettings();$('#settings-dialog').close();toast('DeepSeek 设置已保存；可测试连接');}catch(e){$('#settings-error').textContent=e.message;}};
$('#model-test').onclick=async()=>{const b=$('#model-test');b.disabled=true;try{if(!await confirm('测试 DeepSeek 连接','会发送一条不含个人资料的短测试消息，产生少量 API 费用。'))return;await saveSettings();await api('/api/model/test',{});await load();$('#key-status').textContent='真实 DeepSeek 测试成功。';toast('DeepSeek 真实调用成功');}catch(e){$('#settings-error').textContent=e.message;}finally{b.disabled=false;}};
$('#wiki-form').onsubmit=async e=>{e.preventDefault();const old=pages().find(p=>p.id===editorId);try{const p=await api('/api/wiki',{id:editorId,revision:editorRevision,category_id:$('#wiki-category').value,message_id:editorMessageId,page:{title:$('#wiki-title').value,summary:$('#wiki-summary').value,content:$('#wiki-content').value,tags:$('#wiki-tags').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),links:[...document.querySelectorAll('[data-editor-link]:checked')].map(e=>e.dataset.editorLink),citations:old?.body.citations||[],diagram:old?.body.diagram||[]}});$('#wiki-editor').close();pageId=p.id;await load();await openDocument(p.id);toast('文稿已保存到资产');}catch(e){$('#wiki-error').textContent=e.message;}};
$('#memory-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/memory',{instructions:$('#preferences').value});await load();$('#memory-status').textContent='已保存 · 下次调用生效';$('#memory-error').textContent='';toast('偏好记忆已保存');}catch(e){$('#memory-error').textContent=e.message;}};
$('#memory-clear').onclick=async()=>{if(!await confirm('清空偏好记忆？','只删除你设置的回答偏好，不删除对话、资产或知识页。'))return;try{await api('/api/memory',{instructions:''});await load();$('#preferences').value='';$('#memory-status').textContent='已清空';}catch(e){$('#memory-error').textContent=e.message;}};
$('#load-archived').onclick=async()=>{try{const a=await api('/api/archived');$('#archived-list').innerHTML=[['source',a.sources],['conversation',a.conversations],['artifact',a.artifacts]].flatMap(([type,list])=>list.map(i=>`<div class="archive-item"><span>${esc(i.title)}</span><button data-restore-archive="${type}:${i.id}">恢复</button></div>`)).join('')||'<p class="hint">没有归档内容。</p>';}catch(e){toast(e.message);}};
function download(data,name){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('#export-button').onclick=async()=>{try{download(await api('/api/export'),'jimu-export.json');toast('已导出；可能包含私人资料，请勿直接公开');}catch(e){toast(e.message);}};
$('#wiki-export').onclick=async()=>{try{download(await api('/api/wiki/export'),'jimu-knowledge.json');toast('Wiki 已导出，Markdown 保存在 data/wiki');}catch(e){toast(e.message);}};
$('#menu').onclick=()=>{
 document.body.classList.toggle('sidebar-collapsed');
 closeSidebar();
};
$('#sidebar-toggle').onclick=$('#menu').onclick;
$('#extensions-nav').addEventListener('click',e=>{if(e.target.closest('summary')&&document.body.classList.contains('sidebar-collapsed')){e.preventDefault();document.body.classList.remove('sidebar-collapsed');$('#extensions-nav').open=true;closeSidebar();}});
$('#sidebar-backdrop').onclick=closeSidebar;

closeSidebar();
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeSidebar();});
$('#task-kind').onchange=e=>{kind=e.target.value;if(kind==='experience'&&!careerNarrative)experienceDialog();if(kind==='tailor')tailorDialog();if(kind!=='wiki')targetId=null;render();};
$('#settings-button').onclick=settingsDialog;$('#attach-source').onclick=contextDialog;$('#source-search').oninput=()=>{lastSourcesRender='';renderSources();};$('#wiki-create').onclick=async()=>{if(!await leaveKnowledge())return;editWiki();if(wikiTab==='weekly')$('#wiki-tags').value='周刊，'+state.weekly.config.title;};$('#wiki-ai').onclick=async()=>{if(!await leaveKnowledge())return;kind='wiki';targetId=null;await switchView('home');render();contextDialog();};$('#context-import').onclick=()=>{$('#context-dialog').close();sourceDialog();};$('#new-chat').onclick=async()=>{if(!await leaveKnowledge()||!await closeDocument())return;kind='chat';$('#prompt').value='';cid=null;messages=[];lastSignature='';targetId=null;sourceIds.clear();wikiIds.clear();boardRefs.clear();skillRefs.clear();documentRefs.clear();websiteRefs.clear();retrievalItems=[];careerNarrative='';careerFormat='experience';careerSelection=null;jdSelection=[];$('#use-retrieval').checked=false;switchView('home');render();};
function openWeb(){renderSiteChoices(); $('#web-error').textContent=''; $('#web-dialog').showModal(); }
async function fetchWeb(url,button){
 if(!await confirm('读取公开网页',`向 DeepSeek 发送此链接：${url}。抓取可能产生 API 费用；不发送本地知识库。请勿使用私人链接或含访问令牌的链接。`))return;
 button.disabled=true;
 try{const page=await api('/api/web/fetch',{url,allow_remote:true});
 if($('#web-dialog').open)$('#web-dialog').close();
 if(!$('#source-dialog').open)sourceDialog('url');else setSourceMode('url');
 $('#source-title').value=page.title;$('#source-url').value=page.url;$('#source-content').value=page.content;$('#source-visibility').value='public';
 toast('正文已读取，确认后保存');
 }finally{button.disabled=false;}
}

$('#web-open').onclick=openWeb;
$('#wiki-search').oninput=renderWiki;
$('#source-fetch').onclick=async()=>{const b=$('#source-fetch');try{const url=$('#source-url').value.trim();if(!url)return toast('请先填写来源链接');b.disabled=true;const result=await api('/api/capture/preview',{url,allow_remote:true});$('#source-dialog').close();await openCaptureDialog();capturePreview=result;showCapturePreview(result);$('#capture-save').disabled=false;$('#capture-error').textContent='已读取，检查后保存。';}catch(e){$('#source-error').textContent=e.message;}finally{b.disabled=false;}};
$('#web-form').onsubmit=async e=>{e.preventDefault();const query=$('#web-query').value.trim();if(!query)return;
 if(!await confirm('搜索公开网页',`向 DeepSeek 发送搜索词「${query}」。可能产生 API 费用；不发送本地知识库。请勿包含敏感信息。`))return;
 const b=$('#web-submit');b.disabled=true;$('#web-error').textContent='';
 try{webResults=[];$('#web-results').textContent='正在搜索…';const response=await api('/api/web/search',{query,allow_remote:true,site_ids:[...document.querySelectorAll('[data-search-site]:checked')].map(e=>e.dataset.searchSite)});webResults=response.results;
 $('#web-results').innerHTML=webResults.map((r,i)=>`<article class="web-result"><h3>${esc(r.title||r.url)}</h3><p>${esc(r.snippet)}</p><small>${esc(r.site_name||r.url)}</small><button class="secondary" data-fetch-result="${i}">读取正文</button></article>`).join('')||'<p class="empty">没有搜索结果</p>';
 }catch(e){$('#web-results').textContent='';$('#web-error').textContent=e.message;}finally{b.disabled=false;}
};
document.addEventListener('change',e=>{const d=e.target.dataset;if(d.contextSource){e.target.checked?sourceIds.add(d.contextSource):sourceIds.delete(d.contextSource);render();updateContextBudget();}if(d.contextWiki){e.target.checked?wikiIds.add(d.contextWiki):wikiIds.delete(d.contextWiki);render();updateContextBudget();}});
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;try{
 if(view==='wiki'&&knowledgeDirty()&&(d.view||d.wikiTab||d.page||d.pageTask||d.edit||d.conversation||d.version||d.linkBoard||d.diagram||d.archive||d.flowBoard)&&!await leaveKnowledge())return;
 if(d.exportCareer){const a=state.artifacts.find(v=>v.id===d.exportCareer),content=a.body[a.kind==='career'?'general':'tailored'];const url=URL.createObjectURL(new Blob([content],{type:'text/markdown;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download=a.title+'.md';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 if(d.clipperHelp!==undefined)$('#clipper-help').showModal();
 if(d.flowBoard){if(!await confirm('保存为可编辑画板？','将本页已保存的流程生成独立画板，不改变知识页正文。'))return;const p=pages().find(v=>v.id===d.flowBoard),board=await api('/api/boards/from-wiki',{id:p.id,revision:p.revision});await load();await openBoard(board.id);}
 if(d.fetchResult!==undefined)await fetchWeb(webResults[Number(d.fetchResult)].url,b);
 if(d.saveMessage!==undefined){const m=messages[Number(d.saveMessage)];editWiki();editorMessageId=m.id;$('#editor-title').textContent='存为文稿';$('#wiki-category').innerHTML=assetSaveOptions('','creations');$('#wiki-title').value=(state.conversations.find(c=>c.id===cid)?.title||'对话笔记').slice(0,100);$('#wiki-summary').value='来自对话的个人笔记，尚未经原文核验。';$('#wiki-content').value=m.text;$('#wiki-tags').value='对话笔记';}
 if(d.diagram)openDiagram(d.diagram);
 if(d.weeklySettings!==undefined)weeklyDialog(d.weeklySettings||undefined);
 if(d.weeklyNew!==undefined)weeklyDialog(null,true);
 if(d.weeklyRun!==undefined)await runWeekly(d.weeklyRun||undefined);
 if(d.startRetrieval!==undefined){$('#use-retrieval').checked=true;$('#prompt').focus();toast('写下问题，发送时会先检索并让你确认依据');}
 if(d.startCareer!==undefined)experienceDialog();if(d.startTailor!==undefined)tailorDialog();if(d.openImport!==undefined)sourceDialog();
 if(d.tailorCareer)tailorDialog(d.tailorCareer);
 if(d.editCareer){const a=state.artifacts.find(a=>a.id===d.editCareer);careerEditId=a.id;careerEditRevision=a.revision;$('#career-edit-content').value=a.body[a.kind==='career'?'general':'tailored'];$('#career-edit-confirmed').checked=false;$('#career-edit-error').textContent='';$('#career-edit-dialog').showModal();}
 if(d.asset)await openDocument(d.asset);
 if(d.newBoard!==undefined){closeAssetMenus();await openBoard();}
 if(d.openBoard)await openBoard(d.openBoard);
 if(d.linkBoard)await openBoard(null,d.linkBoard);
 if(d.backAssets!==undefined){pageId=null;renderOutputLibrary();}
 if(d.backPages!==undefined){pageId=null;renderWiki();}
 if(d.refineCareer!==undefined){const p=job().payload;experienceDialog();$('#experience-narrative').value=p.narrative||'';$('#prompt').value='根据补充说明重新整理，保留仍有效事实，更新通用版。';}
 if(d.startWiki!==undefined){kind='wiki';targetId=null;await switchView('home');render();contextDialog();}
 if(d.openContext!==undefined)contextDialog();
 if(d.openWeb!==undefined)openWeb();
 if(d.close!==undefined&&b.closest('dialog').id!=='confirm-dialog')b.closest('dialog').close();
 if(d.view){if(d.view==='wiki'&&(view!=='wiki'||wikiTab!=='pages')){wikiTab='pages';pageId=null;knowledgeSignature='';$('#wiki-search').value='';}await switchView(d.view);}
 if(d.kind){kind=d.kind;render();}
 if(d.wikiTab){wikiTab=d.wikiTab;pageId=null;knowledgeEditing=false;knowledgeSignature='';renderWiki();}
 if(d.page){$('#wiki-search').value='';pageId=d.page;wikiTab=pages().find(p=>p.id===pageId)?.body.tags.includes('周刊')?'weekly':'pages';await switchView('wiki');}
 if(d.conversation){if(!await closeDocument())return;cid=d.conversation;websiteRefs.clear();skillRefs=new Map((job()?.payload.skill_snapshot||[]).map(s=>[s.id,s.revision]));documentRefs=new Map((job()?.payload.document_snapshot||[]).map(d=>[d.id,d.revision]));sourceIds=new Set((job()?.payload.source_ids||[]).filter(id=>state.sources.some(s=>s.id===id)));wikiIds=new Set((job()?.payload.wiki_snapshot||[]).map(p=>p.id).filter(id=>pages().some(p=>p.id===id)));boardRefs=new Map((job()?.payload.board_snapshot||[]).map(b=>[b.id,b.revision]));kind=job()?.payload.kind||'chat';if(kind==='experience'){careerNarrative=job()?.payload.narrative||'';careerFormat=job()?.payload.output_format||'experience';}if(kind==='tailor'){careerSelection=job()?.payload.career_snapshot;jdSelection=job()?.payload.jd_source_ids||[];sourceIds=new Set(jdSelection);}targetId=kind==='wiki'?job()?.payload.wiki_target_id||null:null;await switchView('home');await load();poll();}
 if(d.unselectSource){sourceIds.delete(d.unselectSource);render();}
 if(d.unselectWiki){wikiIds.delete(d.unselectWiki);render();}if(d.unselectBoard){boardRefs.delete(d.unselectBoard);render();}if(d.useBoard){const b=state.artifacts.find(a=>a.id===d.useBoard);boardRefs.set(b.id,b.revision);kind='chat';await switchView('home');render();$('#prompt').focus();}
 if(d.useSource){sourceIds.add(d.useSource);kind='chat';targetId=null;await switchView('home');render();$('#prompt').focus();}
 if(d.source)await openReader('source',d.source);
 if(d.pageTask){targetId=null;wikiIds.add(d.pageTask);kind='chat';await switchView('home');render();$('#prompt').focus();}
 if(d.edit){if($('#reader-dialog').open)$('#reader-dialog').close();editWiki(d.edit);}
 if(d.showReview!==undefined)$('#review-panel').scrollIntoView({behavior:'smooth',block:'start'});
 if(d.approve&&await confirm('确认保存这份成果？','确认后的草稿会保存为文稿资产。原始资料与历史版本保留。')){const extra=job()?.payload.kind==='experience'?{confirmed_fact_ids:[...document.querySelectorAll('[data-confirm-fact]:checked')].map(e=>e.dataset.confirmFact),general:$('#career-general').value}:job()?.payload.kind==='tailor'?{tailored:$('#career-tailored').value,confirm_no_new_claims:$('#confirm-no-new').checked}:job()?.payload.kind==='document'?{confirmed:true}:{};extra.category_id=$('#review-category')?.value||'';const result=await api('/api/jobs/'+d.approve+'/approve',extra);await load();if(['wiki','career','career_review'].includes(result.kind)){pageId=result.id;await openDocument(result.id);}toast('已确认保存，引用与版本保留');}
 if(d.reject){await api('/api/jobs/'+d.reject+'/reject',{});await load();toast('未采纳，正式知识未修改');}
 if(d.cancel){await api('/api/jobs/'+d.cancel+'/cancel',{});await load();}
 if(d.archive&&await confirm('从日常工作区移出？','归档不删除原文和历史，可在设置中恢复。')){const [k,id]=d.archive.split(':');await api('/api/archive',{kind:k,id});if(k==='conversation'&&id===cid){cid=null;messages=[];lastSignature='';}await load();toast('已归档');}
 if(d.restoreArchive){const [k,id]=d.restoreArchive.split(':');await api('/api/archive',{kind:k,id,archived:false});await load();$('#load-archived').click();toast('已恢复');}
 if(d.versions&&!b.closest('#document-panel')){const list=await api('/api/artifacts/'+d.versions+'/versions');$('#versions').innerHTML=list.map(v=>`<div class="version-row"><span>v${v.revision} · ${esc(v.reason)}<small>${v.created.slice(0,10)}</small></span><button data-version="${v.id}" data-artifact="${d.versions}">恢复为新版本</button></div>`).join('');}
 if(d.version&&await confirm('恢复旧版内容？','将创建新版本，不删除任何已有历史。')){const a=state.artifacts.find(a=>a.id===d.artifact);await api('/api/artifacts/'+a.id+'/restore',{version_id:d.version,revision:a.revision});await load();toast('已创建恢复版本');}
 }catch(e){toast(e.message);}});
Promise.all([load(),api('/api/sites').then(v=>sites=v)]).then(()=>{switchView('home');poll();receiveClip();}).catch(e=>toast('服务连接失败：'+e.message));

async function chooseRetrieval(query){
 const response=await api('/api/retrieve',{query});const found=response.results;
 $('#retrieval-results').innerHTML=found.length?found.map((r,i)=>`<label class="context-option"><input type="checkbox" data-retrieval-index="${i}" checked><span><b>${esc(r.title)}</b><small>${r.kind==='wiki'?'知识页':'原始资料'} · 片段 ${r.chunk_index+1}</small><span class="retrieval-excerpt">${esc(r.excerpt.slice(0,320))}${r.excerpt.length>320?'…':''}</span>${r.excerpt.length>320?'<details><summary>查看完整片段</summary><span class="retrieval-excerpt">'+esc(r.excerpt)+'</span></details>':''}</span></label>`).join(''):'<p class="empty">没有匹配依据。可以改写问题，或不带依据继续。</p>';
 $('#retrieval-dialog').showModal();
 return new Promise(resolve=>{
  const done=value=>{$('#retrieval-dialog').close();resolve(value);};
  $('#retrieval-apply').onclick=()=>done([...document.querySelectorAll('[data-retrieval-index]:checked')].map(e=>found[Number(e.dataset.retrievalIndex)]).map(({kind,id,revision,chunk_index})=>({kind,id,revision,chunk_index})));
  $('#retrieval-skip').onclick=()=>done([]);
  $('#retrieval-dialog').oncancel=()=>done(null);
  $('#retrieval-dialog [data-close]').onclick=()=>done(null);
 });
}
let weeklyEditingId=null,weeklyEditingRevision=null;
function weeklyDialog(id,newSubscription=false){
 const items=readingSubscriptions();
 if(newSubscription&&items.length>=3)return toast('最多创建3个订阅');
 const c=newSubscription?{title:'',urls:[],query:'',frequency:'weekly',weekday:4,time:'19:00',enabled:false}:items.find(c=>c.id===id)||items[0]||{title:'',urls:[],query:'',frequency:'weekly',weekday:4,time:'19:00',enabled:false};
 weeklyEditingId=c.id||null;weeklyEditingRevision=c.revision||null;
 $('#weekly-dialog-title').textContent=weeklyEditingId?'编辑订阅':'新建订阅';
 $('#weekly-title').value=c.title;$('#weekly-urls').value=c.urls.join('\n');$('#weekly-query').value=c.query;$('#weekly-error').textContent='';renderSiteChoices();$('#weekly-dialog').showModal();
}
$('#weekly-form').onsubmit=async e=>{
 e.preventDefault();try{
 const saved=await api('/api/weekly/config',{id:weeklyEditingId,revision:weeklyEditingRevision,new:!weeklyEditingId,title:$('#weekly-title').value,urls:$('#weekly-urls').value.split('\n').map(s=>s.trim()).filter(Boolean),query:$('#weekly-query').value,enabled:false,allow_remote:false});
 readingFilter=saved.id;$('#weekly-dialog').close();await load();toast('订阅已保存，点击「刷新资讯」才会采集');
 }catch(e){$('#weekly-error').textContent=e.message;}
};
async function runWeekly(id){
 const c=readingSubscriptions().find(c=>c.id===id)||readingSubscriptions()[0];if(!c)return toast('请先新建订阅');
 if(!await confirm('更新「'+c.title+'」？','仅按这个订阅的 '+c.urls.length+' 个公开来源搜索或抓取正文，再由 DeepSeek 研究、整理和核对。会产生 API 费用；原文保存在资产，草稿仍需你确认。'))return;
 await api('/api/weekly/run',{id:c.id,allow_remote:true});readingFilter=c.id;await load();toast('开始更新「'+c.title+'」，可查看进度');weeklyPoll();
}
let weeklyPolling=false;
function weeklyPoll(){if(weeklyPolling)return;weeklyPolling=true;const tick=async()=>{try{await load();if(state.weekly.runs.some(r=>['collecting','queued','running'].includes(r.status))){setTimeout(tick,1800);return;}weeklyPolling=false;}catch(e){weeklyPolling=false;toast(e.message);}};setTimeout(tick,1800);}
function diagramSvg(nodes){
 if(!nodes.length)return '';
 const height=nodes.length*82-16;
 return `<svg class="saved-diagram" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 ${height}" role="img" aria-label="顺序流程图"><defs><marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="5" refY="4" orient="auto"><path d="M0 1 L6 4 L0 7" fill="none" stroke="#a39a8d"/></marker></defs>${nodes.map((node,i)=>{const y=i*82;const chars=Array.from(node),lines=[];for(let k=0;k<chars.length;k+=20)lines.push(chars.slice(k,k+20).join(''));return `<rect x="10" y="${y}" width="440" height="66" rx="9" fill="#f5f4f1" stroke="#d8d2c8"/><text x="230" y="${y+34-(lines.length-1)*8}" text-anchor="middle" fill="#45433d" font-size="14" font-family="PingFang SC, sans-serif">${lines.map((line,j)=>`<tspan x="230" dy="${j?16:0}">${esc(line)}</tspan>`).join('')}</text>${i<nodes.length-1?`<path d="M230 ${y+68} V${y+78}" fill="none" stroke="#a39a8d" marker-end="url(#flow-arrow)"/>`:''}`;}).join('')}</svg>`;
}
function diagramNodes(){return $('#diagram-nodes').value.split('\n').map(s=>s.trim()).filter(Boolean);}
function openDiagram(id){const p=pages().find(p=>p.id===id);diagramPage=id;diagramRevision=p.revision;$('#diagram-nodes').value=(p.body.diagram||[]).join('\n');$('#diagram-preview').innerHTML=diagramSvg(p.body.diagram||[]);$('#diagram-error').textContent='';$('#diagram-dialog').showModal();}
$('#diagram-nodes').oninput=()=>$('#diagram-preview').innerHTML=diagramSvg(diagramNodes().slice(0,10));
$('#diagram-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/diagram',{id:diagramPage,revision:diagramRevision,nodes:diagramNodes()});$('#diagram-dialog').close();await load();toast('流程图已保存为新版本');}catch(e){$('#diagram-error').textContent=e.message;}};
$('#diagram-export').onclick=()=>{const nodes=diagramNodes();if(!nodes.length)return toast('先填写流程步骤');const url=URL.createObjectURL(new Blob([diagramSvg(nodes.slice(0,10))],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download='jimu-flow.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};

function careers(){return state.artifacts.filter(a=>a.kind==='career');}
function renderCareerContext(){
 const box=$('#career-task-context');box.hidden=!['experience','tailor'].includes(kind);
 if(box.hidden)return;
 const text=kind==='experience'?(careerNarrative?(careerNarrative.startsWith('请依据所选过程记录')?'按所选记录梳理 · 职责待确认':'已带入本人说明 · '+careerNarrative.length+'字'):'先选择记录或补充本人说明'):(careerSelection?'基于 '+careerSelection.title+' · '+jdSelection.length+'份 JD':'先选择已确认经历与JD');
 const signature=kind+text;if(box.dataset.signature===signature)return;box.dataset.signature=signature;
 box.innerHTML=`<span>${esc(text)}</span><button type="button" class="text-button" id="edit-career-input">修改</button>`;
 $('#edit-career-input').onclick=()=>kind==='experience'?experienceDialog():tailorDialog(careerSelection?.id);
}
function experienceDialog(){$('#experience-format').value=careerFormat;$('#experience-narrative').value=careerNarrative;$('#experience-assets').innerHTML='<h3 class="settings-heading">选择过程记录或相关材料</h3>'+[...state.sources].sort((a,b)=>(state.asset_meta?.[b.id]?.category==='record')-(state.asset_meta?.[a.id]?.category==='record')).map(s=>`<label class="context-option"><input type="checkbox" data-experience-source="${s.id}" ${sourceIds.has(s.id)?'checked':''}><span>${esc(s.title)}</span></label>`).join('');$('#experience-dialog').showModal();}
$('#experience-form').onsubmit=async e=>{e.preventDefault();sourceIds=new Set([...document.querySelectorAll('[data-experience-source]:checked')].map(e=>e.dataset.experienceSource));careerNarrative=$('#experience-narrative').value.trim();if(!careerNarrative&&sourceIds.size)careerNarrative='请依据所选过程记录梳理经历；尚未明确的本人职责与结果必须列为待确认，不能当作已证实贡献。';if(careerNarrative.length<20){toast('请选择一份记录，或补充至少20字说明');return;}careerFormat=$('#experience-format').value;kind='experience';targetId=null;$('#experience-dialog').close();await switchView('home');render();$('#prompt').value=careerFormat==='resume'?'根据所选背景资料和经历记录，整理一份完整简历。仅使用有依据的信息，缺失内容列为待补充，不编造职责、技能和效果。':'请先梳理我的真实贡献和待确认事项，再写一份不针对特定岗位的通用版经历表达。';try{await submit();}catch(error){toast(error.message);}};
function tailorDialog(id){
 if(!careers().length){toast('先确认保存一份经历通用版');return;}
 $('#tailor-career').innerHTML=careers().map(c=>`<option value="${c.id}">${esc(c.title)}</option>`).join('');$('#tailor-career').value=id||careerSelection?.id||careers()[0].id;
 $('#tailor-sources').innerHTML=state.sources.map(s=>`<label class="context-option"><input type="checkbox" data-jd-source="${s.id}" ${jdSelection.includes(s.id)?'checked':''}><span>${esc(s.title)}<small>${s.content.length}字</small></span></label>`).join('')||'<p class="hint">先导入JD正文或文件。</p>';
 $('#tailor-target').innerHTML='<option value="">按所选列表第一份</option>'+state.sources.map(s=>`<option value="${s.id}">${esc(s.title)}</option>`).join('');$('#tailor-target').value=jdSelection[0]||'';
 $('#tailor-gaps').value=declaredGaps;$('#tailor-error').textContent='';$('#tailor-dialog').showModal();
}
$('#tailor-import').onclick=()=>{$('#tailor-dialog').close();sourceDialog();toast('保存JD后，再打开「JD 诊断与改写」选择它');};
$('#tailor-form').onsubmit=async e=>{e.preventDefault();jdSelection=[...document.querySelectorAll('[data-jd-source]:checked')].map(e=>e.dataset.jdSource);if(!jdSelection.length||jdSelection.length>3){$('#tailor-error').textContent='请选择1至3份JD';return;}const target=$('#tailor-target').value;if(target&&!jdSelection.includes(target)){$('#tailor-error').textContent='目标JD必须同时勾选为依据';return;}if(target)jdSelection=[target,...jdSelection.filter(id=>id!==target)];careerSelection=careers().find(c=>c.id===$('#tailor-career').value);declaredGaps=$('#tailor-gaps').value;sourceIds=new Set(jdSelection);wikiIds.clear();boardRefs.clear();kind='tailor';$('#tailor-dialog').close();await switchView('home');render();$('#prompt').value='对照这些JD，区分表达不足、证据不足与已确认能力差距；给出批注，并在不新增贡献的前提下写定向版。';try{await submit();}catch(error){toast(error.message);}};
function renderCareerReview(j){
 const panel=$('#review-panel');if(reviewSignature===j.id)return;reviewSignature=j.id;
 const p=j.payload.proposal,experience=j.payload.kind==='experience';
 panel.innerHTML=`<div class="review-heading"><h2>${experience?(p.output_format==='resume'?'确认简历事实与通用版':'确认经历事实与通用版'):'岗位诊断与改写'}</h2><span class="hint">未保存</span></div>${experience?`<div class="facts-list">${p.facts.map(f=>`<article class="career-fact"><label class="check-row"><input type="checkbox" data-confirm-fact="${f.id}"><b>${esc(f.text)}</b></label><p class="hint">本人职责：${esc(f.ownership)}</p>${f.evidence.map(quote).join('')}</article>`).join('')}</div>${p.questions.length?'<details class="career-questions" open><summary>需要补充或核验的问题</summary>'+p.questions.map(q=>'<p>'+esc(q)+'</p>').join('')+'</details>':''}<label class="asset-edit-label">通用版 · 可编辑<textarea id="career-general" rows="7">${esc(p.general)}</textarea></label><button class="text-button" data-refine-career>补充说明后重新整理</button>`:`<div class="review-columns"><div><div class="review-label">通用版原文 · 高亮为待优化位置</div><div class="annotated-text">${annotate(j.payload.career_snapshot.body.general,p.diagnostics)}</div></div><div><div class="review-label">批注</div>${diagnosticCards(p.diagnostics)}</div></div><label class="asset-edit-label">定向版 · 可编辑<textarea id="career-tailored" rows="7">${esc(p.tailored)}</textarea></label><label class="check-row"><input type="checkbox" id="confirm-no-new">我已检查，没有新增未经证实的职责、能力或数据</label>`}${saveDestinationMarkup(j)}<div class="review-actions"><button class="secondary" data-reject="${j.id}">不采纳</button><button class="primary" data-approve="${j.id}">确认保存</button></div>`;
}
function annotate(original,diagnostics){
 const ranges=[];diagnostics.forEach((d,i)=>{const start=original.indexOf(d.quote),end=start+d.quote.length;if(start<0)return;const same=ranges.find(r=>r.start===start&&r.end===end);if(same){same.indices.push(i+1);return;}if(!ranges.some(r=>start<r.end&&end>r.start))ranges.push({start,end,indices:[i+1]});});ranges.sort((a,b)=>a.start-b.start);let out='',last=0;ranges.forEach(r=>{const numbers=r.indices.join('、');out+=esc(original.slice(last,r.start))+`<mark title="批注 ${numbers}">${esc(original.slice(r.start,r.end))}<sup>${numbers}</sup></mark>`;last=r.end;});return out+esc(original.slice(last));
}
function diagnosticCards(items){return items.map((d,i)=>`<article class="diagnostic"><b>${i+1}. ${{expression:'表达不足',evidence:'证据不足',gap:'用户确认的能力差距'}[d.category]}</b><p>${esc(d.problem)}</p><p class="diagnostic-suggestion">${esc(d.suggestion)}</p><details><summary>对应JD要求</summary>${d.jd_evidence.map(quote).join('')}</details></article>`).join('');}
function renderAssets(){
 const board=assetTab==='boards',query=$('#output-search').value.trim().toLowerCase();
 const list=state.artifacts.filter(a=>board?a.kind==='board':['career','career_review'].includes(a.kind)).filter(a=>!query||(a.title+' '+JSON.stringify(a.body)).toLowerCase().includes(query));
 const p=list.find(a=>a.id===pageId);
 if(board){$('#output-list').innerHTML=`<div class="asset-toolbar"><span class="hint">点击缩略图，打开并继续编辑。</span><button class="secondary" data-new-board>新画板</button></div>`+(list.length?`<div class="board-gallery">${list.map(a=>`<article class="board-card"><button class="board-open" data-open-board="${a.id}"><div class="board-thumbnail">${boardThumbnail(a.body.scene,a.id)}</div><div class="board-card-meta"><h3>${esc(a.title)}</h3><span>v${a.revision} · ${a.body.scene.elements.filter(e=>!e.isDeleted).length}个图形</span></div></button><button class="text-button board-reference" data-use-board="${a.id}">引用文字 ↗</button></article>`).join('')}</div>`:'<div class="empty">还没有画板。新建一张，把想法画出来。</div>');return;}
 if(!p){$('#output-list').innerHTML=`<div class="asset-toolbar"><span class="hint">${board?'可编辑的本地画板':'确认后的经历、通用简历与岗位版本。原始过程记录仍保留在资产。'}</span><button class="secondary" ${board?'data-new-board':'data-start-career'}>${board?'新画板':'整理经历'}</button></div>`+(list.length?`<div class="knowledge-list">${list.map(a=>`<button class="knowledge-row" data-asset="${a.id}"><span>${esc(a.title)}<small class="asset-type">${a.kind==='career'?(a.body.output_format==='resume'?'简历 · 通用版':'经历 · 通用版'):a.kind==='career_review'?(a.body.output_format==='resume'?'简历 · JD定向版':'JD 定向版'):'画板'}</small></span><small>v${a.revision}</small><span>→</span></button>`).join('')}</div>`:'<div class="empty">'+(board?'还没有画板。':'还没有经历文稿。先在对话里整理一段经历。')+'</div>');return;}
 const b=p.body;
 $('#output-list').innerHTML=`<article class="wiki-document asset-document"><button class="text-button" data-back-assets>← 返回列表</button><div class="document-meta">v${p.revision} · ${board?'本地画板':p.kind==='career'?'用户确认的经历':'基于经历 v'+b.career_revision+' 的岗位版'}</div><h2>${esc(p.title)}</h2>${board?`<p class="summary">${b.scene.elements.length}个图形${b.linked_id?' · 关联 '+esc(state.artifacts.find(a=>a.id===b.linked_id)?.title||'已归档资产'):''}</p><button class="primary" data-open-board="${p.id}">打开画板</button>`:p.kind==='career'?`${b.output_format==='resume'?'':'<h3 class="diagram-title">通用版</h3>'}<div class="markdown">${md(b.general.replace(/^#\s+[^\n]+\n/,first=>first.trim().replace(/^#\s+/,'')===p.title?'':first))}</div><details class="career-questions"><summary>已确认事实与出处</summary>${b.facts.map(f=>'<article class="career-fact"><b>'+esc(f.text)+'</b><p class="hint">本人职责：'+esc(f.ownership)+'</p>'+f.evidence.map(quote).join('')+'</article>').join('')}</details>${b.questions.length?'<details class="career-questions"><summary>仍需补充的信息</summary>'+b.questions.map(q=>'<p>'+esc(q)+'</p>').join('')+'</details>':''}<button class="primary" data-tailor-career="${p.id}">对照 JD 改写</button>`:`<div class="review-columns"><div><h3 class="diagram-title">${b.output_format==='resume'?'简历 · 通用版':'通用版'}</h3><div class="annotated-text">${annotate(b.original,b.diagnostics)}</div></div><div><h3 class="diagram-title">诊断与建议</h3>${diagnosticCards(b.diagnostics)}</div></div><h3 class="diagram-title">定向改写版</h3><div class="markdown">${md(b.tailored)}</div>`}<div class="document-actions">${!board?`<button class="text-button" data-edit-career="${p.id}">修订表达</button><button class="text-button" data-link-board="${p.id}">关联画板</button>`:''}<button class="text-button" data-versions="${p.id}">版本</button><button class="text-button" data-download-asset="${p.id}">导出 JSON</button>${!board?`<button class="text-button" data-export-career="${p.id}">导出 Markdown</button>`:''}<button class="text-button" data-archive="artifact:${p.id}">归档</button></div><div id="versions"></div></article>`;
}
let boardSeedNodes=[];
async function openBoard(id=null,linked=null){
 if(typeof boardDraftJob!=='undefined')boardDraftJob=null;
 if(!id&&linked){const existing=state.artifacts.find(a=>a.kind==='board'&&a.body.linked_id===linked);if(existing)id=existing.id;}
 const p=state.artifacts.find(a=>a.id===id);boardId=id;boardRevision=p?.revision||0;boardLinked=p?.body.linked_id||linked;boardDirty=false;
 $('#board-destination').innerHTML=categoryOptions(p?state.library?.find(a=>a.id===p.id)?.category_id||'':'','creations');$('#board-title').value=p?.title||(linked?(state.artifacts.find(a=>a.id===linked)?.title||'')+' · 画板':'未命名画板');$('#board-status').textContent=p?'已保存':'尚未保存';$('#board-error').textContent='';$('#board-save').textContent='保存';$('#board-seed').hidden=!!p?.body.scene.elements?.length;$('#board-dialog').showModal();
 try{if(!boardModule){const link=document.createElement('link');link.rel='stylesheet';link.href='/board-assets/main.css';document.head.append(link);boardModule=await import('/board-assets/main.js');}boardModule.mountBoard($('#board-container'),p?.body.scene||{});boardSeedNodes=state.artifacts.find(a=>a.id===boardLinked)?.body.diagram||[];}catch(e){$('#board-error').textContent='画板加载失败：'+e.message;}
}
window.addEventListener('board-edited',()=>{boardDirty=true;$('#board-status').textContent='有未保存修改';});
$('#board-title').oninput=()=>{boardDirty=true;$('#board-status').textContent='有未保存修改';};
$('#board-save').onclick=async()=>{const button=$('#board-save');button.disabled=true;try{const p=await api('/api/boards',{id:boardId,revision:boardRevision,title:$('#board-title').value,scene:boardModule.boardScene(),category_id:$('#board-destination').value,linked_id:boardLinked});boardId=p.id;boardRevision=p.revision;boardDirty=false;$('#board-status').textContent='已保存';await load();toast('画板已保存，可在资产中找到');}catch(e){$('#board-error').textContent=e.message;}finally{button.disabled=false;}};
async function closeBoard(){if(boardDirty&&!await confirm('退出未保存的画板？','退出会丢弃本次未保存修改。可以取消，先保存画板。'))return;$('#board-dialog').close();}
$('#board-close').onclick=closeBoard;$('#board-dialog').oncancel=e=>{e.preventDefault();closeBoard();};
$('#board-export').onclick=async()=>{try{const svg=await boardModule.boardSvg();const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));const a=document.createElement('a');a.href=url;a.download='jimu-board.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){$('#board-error').textContent=e.message;}};
$('#board-seed').onclick=()=>{try{const nodes=boardSeedNodes.length?boardSeedNodes:['提出任务','整理依据','完成草稿','确认保存'];boardModule.seedFlow(nodes);}catch(e){$('#board-error').textContent=e.message;}};
function renderSiteChoices(){
 $('#web-sites').innerHTML=sites.map(s=>`<label class="site-choice"><input type="checkbox" data-search-site="${s.id}">${esc(s.name)}</label>`).join('');
 renderSubscriptionPresets();
}
function subscriptionSiteKey(value){try{return new URL(value.trim()).href.replace(/\/$/,'');}catch{return value.trim();}}
function subscriptionUrls(){return [...new Set($('#weekly-urls').value.split('\n').map(s=>s.trim()).filter(Boolean))];}
function renderSubscriptionPresets(){
 const selected=new Set(subscriptionUrls().map(subscriptionSiteKey));
 $('#weekly-presets').innerHTML='<span class="hint">快捷订阅源 · 点击添加，再点移除</span>'+[...sites.filter(s=>s.feed_url).map(s=>({...s,url:s.feed_url})),{name:'Codex 发布',url:'https://github.com/openai/codex/releases.atom'},{name:'OpenCode 发布',url:'https://github.com/anomalyco/opencode/releases.atom'}].map(s=>{const added=selected.has(subscriptionSiteKey(s.url));return `<button type="button" class="site-chip" data-add-site="${esc(s.url)}" aria-pressed="${added}" title="${esc(s.note||s.url)}">${added?'✓':'+'} ${esc(s.name)}</button>`;}).join('');
}
function toggleSubscriptionSite(url){
 const lines=subscriptionUrls(),key=subscriptionSiteKey(url),added=lines.some(s=>subscriptionSiteKey(s)===key);
 if(!added&&lines.length>=8){$('#weekly-error').textContent='最多关注8个网站，请先移除一个链接。';return;}
 $('#weekly-urls').value=(added?lines.filter(s=>subscriptionSiteKey(s)!==key):[...lines,url]).join('\n');
 $('#weekly-error').textContent='';renderSubscriptionPresets();
 $('#weekly-presets').querySelectorAll('[data-add-site]').forEach(b=>{if(b.dataset.addSite===url)b.focus();});
}
$('#weekly-urls').addEventListener('input',renderSubscriptionPresets);
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.addSite)toggleSubscriptionSite(b.dataset.addSite);if(b.dataset.downloadAsset){const a=state.artifacts.find(a=>a.id===b.dataset.downloadAsset);download(a,'jimu-'+a.kind+'.json');}});

$('#career-edit-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/career/edit',{id:careerEditId,revision:careerEditRevision,content:$('#career-edit-content').value,confirmed:$('#career-edit-confirmed').checked});$('#career-edit-dialog').close();await load();toast('已保存经历新版本');}catch(e){$('#career-edit-error').textContent=e.message;}};
$('#task-clear').onclick=()=>{kind='chat';targetId=null;careerNarrative='';careerSelection=null;render();};
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;try{
 if(b.closest('.task-menu')&&!['attach-skill','attach-website'].includes(b.id))b.closest('details').open=false;
 if(d.outputTab){if(d.outputTab==='wiki'){wikiTab='pages';pageId=null;knowledgeSignature='';await switchView('wiki');}else{assetTab=d.outputTab;pageId=null;await switchView('outputs');}}
 if(d.filter){assetFilter=d.filter;lastSourcesRender='';renderSources();}
 if(d.readWiki)await openReader('wiki',d.readWiki);
 if(d.likeSource){const m=state.asset_meta?.[d.likeSource]||{};await api('/api/assets/meta',{id:d.likeSource,category:m.category||'reference',favorite:!m.favorite});await load();await openReader('source',d.likeSource);}
 if(d.readerUse){sourceIds.add(d.readerUse);kind='chat';$('#reader-dialog').close();await switchView('home');render();$('#prompt').focus();}
 if(d.pdfPage&&readerTarget)showPdfPage(Number(d.pdfPage));
 }catch(err){toast(err.message);}});
async function openReader(kind,id){
 if(kind==='wiki'){if(!await leaveKnowledge())return;const p=pages().find(p=>p.id===id);if(!p)throw Error('文档不存在');wikiTab=p.body.tags.includes('周刊')?'weekly':'pages';pageId=id;knowledgeEditing=false;knowledgeSignature='';await switchView('wiki');return;}
 readerTarget={kind,id};const s=kind==='source'?state.sources.find(s=>s.id===id):pages().find(p=>p.id===id);if(!s)throw Error('内容不可用');const m=state.asset_meta?.[id]||{};let content=kind==='source'?s.content:s.body.content;const first=content.split('\n')[0];if(kind==='wiki'&&first.replace(/^#{1,3}\s*/, '').trim()===s.title)content=content.slice(first.length).trimStart();
 $('#reader-title').textContent=s.title;$('#reader-type').textContent=kind==='source'?(m.extension?.slice(1).toUpperCase()||'原始记录'):(s.body.tags.includes('周刊')?'周刊 · 阅读与笔记':'知识 · 阅读与笔记');
 $('#reader-content').innerHTML=(kind==='source'&&m.extension==='.pdf'?`<div class="pdf-tools"><button data-pdf-page="1" disabled>上一页</button><span>第 <b id="pdf-page-number">1</b> 页<span id="pdf-page-total"></span></span><button data-pdf-page="2" disabled>下一页</button></div><p id="pdf-preview-error" class="error" hidden></p><img id="pdf-preview" alt="PDF页面预览"><details><summary>查看提取文字</summary><div class="markdown">${md(content)}</div></details>`:`<div class="markdown">${md(content)}</div>`)+(kind==='source'&&m.extension==='.docx'?'<p class="reader-footnote">正文预览保留段落和表格文字；不等同于Word原版排版。</p>':'')+(kind==='source'&&['.html','.htm'].includes(m.extension)?'<p class="reader-footnote">HTML安全阅读视图，脚本、外部资源与表单不会运行。</p>':'');
 $('#reader-actions').innerHTML=kind==='source'?`<button class="secondary" data-reader-use="${id}">带入对话</button><button class="text-button" data-like-source="${id}">${m.favorite?'♥ 已喜欢':'♡ 喜欢这篇'}</button>${m.extension?`<a class="text-button" href="${scoped('/api/assets/'+id+'/file')}">下载原件</a>`:''}`:`<button class="text-button" data-edit="${id}">编辑知识页</button><details><summary>本页原文</summary>${[...new Set(s.body.citations.map(c=>c.source_id))].map(sid=>`<button class="reader-source-link" data-source="${sid}">${esc(state.sources.find(v=>v.id===sid)?.title||'来源已归档')}</button>`).join('')}</details>`;
 $('#note-quote').value='';$('#note-text').value='';$('#note-error').textContent='';await loadNotes();if(!$('#reader-dialog').open)$('#reader-dialog').showModal();
 if(kind==='source'&&m.extension==='.pdf'){try{const info=await api('/api/assets/'+id+'/info');if(readerTarget?.id!==id)return;readerTarget.pages=info.pages;$('#pdf-page-total').textContent=' / '+info.pages;showPdfPage(1);}catch(err){$('#pdf-preview').hidden=true;$('#pdf-preview-error').hidden=false;$('#pdf-preview-error').textContent=err.message;}}
}
function showPdfPage(page){
 if(!readerTarget?.pages||page<1||page>readerTarget.pages)return;
 const image=$('#pdf-preview');$('#pdf-preview-error').hidden=true;image.hidden=false;
 image.onerror=()=>{image.hidden=true;$('#pdf-preview-error').hidden=false;$('#pdf-preview-error').textContent='此页暂不可预览，请展开下方提取文字或下载原件。';};
 image.src=scoped('/api/assets/'+readerTarget.id+'/page/'+page);$('#pdf-page-number').textContent=page;
 const buttons=document.querySelectorAll('[data-pdf-page]');buttons[0].dataset.pdfPage=page-1;buttons[0].disabled=page===1;buttons[1].dataset.pdfPage=page+1;buttons[1].disabled=page===readerTarget.pages;
}
async function loadNotes(){const list=await api('/api/notes?kind='+readerTarget.kind+'&id='+readerTarget.id);$('#reader-notes').innerHTML=list.map(n=>`<article class="reading-note">${n.quote?'<blockquote>'+esc(n.quote)+'</blockquote>':''}<p>${esc(n.text)}</p><small>${new Date(n.created).toLocaleDateString('zh-CN')}</small></article>`).join('')||'<p class="hint">阅读时留下自己的理解。</p>';}
$('#note-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/notes',{kind:readerTarget.kind,id:readerTarget.id,quote:$('#note-quote').value,text:$('#note-text').value});$('#note-quote').value='';$('#note-text').value='';await loadNotes();}catch(err){$('#note-error').textContent=err.message;}};

const memoryPresets={concise:'先说结论，使用简洁、直接的中文；需要操作时列出明确步骤。',study:'作为学习搭档，先解释核心概念，再用一个例子讲清楚；不要一开始堆术语。',evidence:'区分事实、推测和建议；没有材料支持的结论说明待核验，不编造经历或效果。'};
document.addEventListener('click',e=>{const b=e.target.closest('[data-memory-preset]');if(!b)return;const text=memoryPresets[b.dataset.memoryPreset];if(!$('#preferences').value.includes(text))$('#preferences').value=[$('#preferences').value.trim(),text].filter(Boolean).join('\n');$('#memory-status').textContent='尚未保存';});

function syncOutputTabs(){document.querySelectorAll('[data-output-tab]').forEach(b=>b.classList.toggle('active',b.dataset.outputTab===(view==='wiki'?'wiki':assetTab)));}
function renderOutputLibrary(){
 syncOutputTabs();$('#output-heading').textContent=assetTab==='boards'?'画板':'经历文稿';$('#output-description').textContent=assetTab==='boards'?'可编辑的流程和图示，可引用已保存的文字继续讨论。':'从个人记录整理的经历、通用简历和岗位改写。原件留在资产。';renderAssets();
}
$('#output-search').oninput=renderOutputLibrary;
document.addEventListener('change',e=>{const id=e.target.dataset.contextBoard;if(!id)return;const board=state.artifacts.find(a=>a.id===id);if(e.target.checked){if(boardRefs.size>=3){e.target.checked=false;toast('最多引用3个画板');return;}boardRefs.set(id,board.revision);}else boardRefs.delete(id);updateContextBudget();render();});

document.querySelector('.task-menu').addEventListener('click',e=>{if(!['attach-skill','attach-website'].includes(e.target.closest('button')?.id)&&e.target.closest('button')){document.querySelector('.composer-menu').removeAttribute('open');$('#composer-skill-options').hidden=true;}});
