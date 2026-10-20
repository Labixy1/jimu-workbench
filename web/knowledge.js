'use strict';
let knowledgeDraft=null,knowledgeEditing=false,knowledgeSide='notes',knowledgeSignature='',knowledgeNotesToken=0;
const knowledgeNoteDrafts=new Map();
let knowledgeDirectoryOpen=null;
let knowledgeInspectorOpen=true;

function syncKnowledgeInspector(){
 const open=view==='wiki'&&knowledgeInspectorOpen,panel=$('#knowledge-inspector'),toggle=$('#knowledge-inspector-toggle');
 if(!open&&panel.contains(document.activeElement))toggle.focus();
 panel.hidden=!open;
 $('#wiki-body').classList.toggle('inspector-collapsed',!open);
 toggle.setAttribute('aria-expanded',String(open));
 toggle.setAttribute('aria-label',open?'收起批注栏':'展开批注栏');
}
function setKnowledgeInspector(open){knowledgeInspectorOpen=open;syncKnowledgeInspector();}

function syncKnowledgeDirectory(){
 const mobile=false;
 if(knowledgeDirectoryOpen===null)knowledgeDirectoryOpen=!mobile;
 const open=view==='wiki'&&knowledgeDirectoryOpen,panel=$('#knowledge-sidebar'),toggle=$('#knowledge-directory-toggle');
 // Collapsing the directory changes layout only, never the document draft.
 if(!open&&panel.contains(document.activeElement))toggle.focus();
 panel.hidden=!open;
 $('#wiki-body').classList.toggle('directory-collapsed',!open);
 toggle.setAttribute('aria-expanded',String(open));
 toggle.setAttribute('aria-label',open?'收起文档目录':'展开文档目录');
 $('#knowledge-directory-backdrop').hidden=!(mobile&&open);
 syncKnowledgeInspector();
}
function setKnowledgeDirectory(open){knowledgeDirectoryOpen=open;syncKnowledgeDirectory();}

function knowledgeGroups(items,weekly){
 const groups=new Map();
 for(const p of items){const tags=p.body.tags||[];const label=weekly?(tags.find(t=>t!=='周刊')||'阅读周刊'):(tags.find(t=>t!=='周刊')||'未分类');if(!groups.has(label))groups.set(label,[]);groups.get(label).push(p);}
 return [...groups];
}
function knowledgeDirty(){return !!knowledgeDraft?.dirty;}
async function leaveKnowledge(){
 if(!knowledgeDirty())return true;
 if(!await confirm('离开未保存的文档？','本次修改尚未保存。取消可继续编辑；离开不会改变已保存版本。'))return false;
 knowledgeDraft=null;knowledgeEditing=false;knowledgeSignature='';return true;
}
function renderKnowledge(){
 const weekly=wikiTab==='weekly',query=$('#wiki-search').value.trim().toLowerCase();
 const items=pages().filter(p=>p.body.tags.includes('周刊')===weekly).filter(p=>!query||(p.title+' '+p.body.tags.join(' ')+' '+p.body.content).toLowerCase().includes(query));
 if(!items.some(p=>p.id===pageId)&&!knowledgeDirty())pageId=items[0]?.id||null;
 const p=pages().find(p=>p.id===pageId),signature=JSON.stringify([items,p?.revision,wikiTab,query,knowledgeEditing,knowledgeSide,state.weekly,state.sources]);
 if(signature===knowledgeSignature)return;knowledgeSignature=signature;
 const groupOpen=new Map([...document.querySelectorAll('.knowledge-group')].map(g=>[g.dataset.group,g.open]));
 const sameDocument=$('#knowledge-document').dataset.documentId===p?.id,paperScroll=$('.knowledge-paper')?.scrollTop||0;
 $('#knowledge-document').dataset.documentId=p?.id||'';
 document.querySelectorAll('[data-wiki-tab]').forEach(b=>b.classList.toggle('active',b.dataset.wikiTab===wikiTab));
 $('#wiki-create').setAttribute('aria-label',weekly?'新建一期':'新建文档');$('#wiki-search').hidden=false;$('#wiki-search').style.visibility='visible';
 $('#knowledge-tree').innerHTML=knowledgeGroups(items,weekly).map(([name,list])=>`<details class="knowledge-group" data-group="${esc(name)}" ${groupOpen.get(name)===false?'':'open'}><summary><span>${esc(name)}</span><small>${list.length}</small></summary>${list.map(v=>`<button class="knowledge-child ${v.id===pageId?'active':''}" data-knowledge-page="${v.id}" ${v.id===pageId?'aria-current="page"':''} title="${esc(v.title)}"><svg class="icon"><use href="#i-book"/></svg><span>${esc(v.title)}</span></button>`).join('')}</details>`).join('')||'<p class="knowledge-empty">还没有文档</p>';
 $('#knowledge-nav-footer').innerHTML=weekly?`<div class="knowledge-subscription"><span>${state.weekly.config?.enabled?'定时更新已启用':'定时更新未启用'}</span><button data-weekly-settings>栏目设置</button><button data-weekly-run ${state.weekly.config?.urls?.length?'':'disabled'}>采集新一期</button></div>`:`<span class="knowledge-nav-count">${items.length} 份文档</span>`;
 if(!p){knowledgeDraft=null;$('#knowledge-document').innerHTML=`<div class="knowledge-blank"><span class="eyebrow">${weekly?'阅读周刊':'知识页'}</span><h2>${query?'没有匹配的文档':'把资料整理成自己的理解。'}</h2><p>${weekly?'设置关注的网站，或从资产选择文章开始整理。':'新建一页，或在对话里整理材料后确认保存。'}</p></div>`;$('#knowledge-inspector').innerHTML='<h2>批注与修改</h2><p class="hint">选择左侧文档后，在这里记录想法或保存修改。</p>';return;}
 if(!knowledgeDraft||knowledgeDraft.id!==p.id||(!knowledgeDirty()&&knowledgeDraft.revision!==p.revision))knowledgeDraft={id:p.id,revision:p.revision,title:p.title,summary:p.body.summary,content:p.body.content,tags:p.body.tags.join('，'),links:[...p.body.links],dirty:false};
 const d=knowledgeDraft,stale=d.revision!==p.revision;
 $('#knowledge-document').innerHTML=`<div class="knowledge-doc-bar"><span>${weekly?'<button class="text-button" data-back-reading>← 周刊阅读</button>':'知识库'} / ${esc(p.body.tags.find(t=>t!=='周刊')||'未分类')}</span><div><button class="${!knowledgeEditing?'active':''}" data-knowledge-mode="read">阅读</button><button class="${knowledgeEditing?'active':''}" data-knowledge-mode="edit">编辑</button>${knowledgeEditing?'<button class="knowledge-toolbar-save" data-knowledge-save>保存</button>':''}</div></div><div class="knowledge-paper">${knowledgeEditing?`<input class="knowledge-title-input" id="knowledge-title" aria-label="文档标题" maxlength="100" value="${esc(d.title)}"><textarea class="knowledge-markdown" id="knowledge-markdown" aria-label="Markdown正文" spellcheck="false">${esc(d.content)}</textarea>`:`<div class="document-meta"><span class="document-kind">${weekly?'阅读周刊':'知识笔记'}</span><span>约 ${Math.max(1,Math.ceil(d.content.length/450))} 分钟 · v${p.revision}</span></div><h1>${esc(d.title)}</h1><p class="knowledge-summary">${esc(d.summary)}</p><div class="markdown knowledge-prose" id="knowledge-prose">${md(d.content.replace(/^#{1,3}\s+[^\n]+\n/,first=>first.trim().replace(/^#{1,3}\s+/,'')===d.title?'':first))}${p.body.links.length?'<div class="knowledge-related"><h3>关联知识</h3>'+p.body.links.map(id=>`<button class="text-button" data-page="${id}">${esc(pages().find(v=>v.id===id)?.title||id)}</button>`).join('')+'</div>':''}${p.body.diagram?.length?'<details class="knowledge-inline-diagram"><summary>本页流程图</summary>'+diagramSvg(p.body.diagram)+'</details>':''}</div>`}</div>`;
 $('#knowledge-inspector').innerHTML=`<div class="knowledge-side-tabs"><button data-knowledge-side="notes" class="${knowledgeSide==='notes'?'active':''}">批注</button><button data-knowledge-side="changes" class="${knowledgeSide==='changes'?'active':''}">修改</button></div><div id="knowledge-stale" class="error" ${stale?'':'hidden'}>已保存版本发生变化。你的修改仍保留，保存时不会覆盖新版本。</div><div id="knowledge-dirty-status" class="knowledge-save-status">${d.dirty?'有未保存修改':knowledgeEditing?'已保存 · v'+p.revision:''}</div>${knowledgeSide==='notes'?`<button class="text-button knowledge-excerpt" data-knowledge-excerpt>摘录选中的文字</button><form id="knowledge-note-form"><label class="knowledge-note-label">写下你的想法<textarea id="knowledge-note-text" rows="4" required maxlength="2000" placeholder="记下理解、疑问或下一步…"></textarea></label><details id="knowledge-quote-details" class="knowledge-quote-details"><summary>关联原文摘录</summary><textarea id="knowledge-note-quote" aria-label="原文摘录" rows="3" maxlength="1200" placeholder="粘贴原文，或选中正文后摘录"></textarea></details><button class="secondary">保存批注</button><p id="knowledge-note-error" class="error"></p></form><div id="knowledge-notes"></div>`:`<h3 class="knowledge-section-title">文档信息</h3><label>摘要<textarea id="knowledge-summary" rows="4" maxlength="400">${esc(d.summary)}</textarea></label><label>栏目 / 标签<input id="knowledge-tags" maxlength="240" value="${esc(d.tags)}" placeholder="第一个标签作为栏目"></label><p class="knowledge-nav-hint">多个标签用逗号分隔。周刊保留“周刊”标签。</p><details class="knowledge-link-options"><summary>关联知识</summary>${pages().filter(v=>v.id!==p.id).map(v=>`<label class="knowledge-link-option"><input type="checkbox" data-knowledge-link="${v.id}" ${d.links.includes(v.id)?'checked':''}><span>${esc(v.title)}</span></label>`).join('')||'<p class="hint">还没有其他知识页。</p>'}</details><button class="primary knowledge-save" data-knowledge-save>保存新版本</button><button class="text-button" data-knowledge-discard>放弃本次修改</button>`}<p id="knowledge-save-error" class="error" role="alert"></p><details class="knowledge-sources"><summary>原文依据 · ${p.body.citations.length}</summary>${[...new Set(p.body.citations.map(c=>c.source_id))].map(id=>`<button data-source="${id}">${esc(state.sources.find(s=>s.id===id)?.title||'来源已归档')}</button>`).join('')||'<p class="hint">这是个人记录，未关联原文。</p>'}${p.body.citations.map(c=>'<blockquote>'+esc(c.quote)+'</blockquote>').join('')}</details><div class="knowledge-extra"><button class="text-button" data-versions="${p.id}">版本记录</button><button class="text-button knowledge-continue" data-page-task="${p.id}"><svg class="icon" aria-hidden="true"><use href="#i-chat"/></svg>在对话中继续</button></div><details class="knowledge-more"><summary>更多操作</summary>${p.body.diagram?.length?`<button class="text-button" data-flow-board="${p.id}">生成可编辑画板</button>`:''}<button class="text-button" data-link-board="${p.id}">关联画板</button><button class="text-button" data-diagram="${p.id}">${p.body.diagram?.length?'编辑本页流程图':'添加本页流程图'}</button><button class="text-button" data-archive="artifact:${p.id}">归档文档</button></details><div id="versions"></div>`;
 if(knowledgeEditing){$('#knowledge-title').oninput=()=>changeKnowledge('title',$('#knowledge-title').value);$('#knowledge-markdown').oninput=()=>changeKnowledge('content',$('#knowledge-markdown').value);}
 if(knowledgeSide==='changes'){$('#knowledge-summary').oninput=()=>changeKnowledge('summary',$('#knowledge-summary').value);$('#knowledge-tags').oninput=()=>changeKnowledge('tags',$('#knowledge-tags').value);}
 else {const note=knowledgeNoteDrafts.get(p.id)||{quote:'',text:''};$('#knowledge-note-quote').value=note.quote;$('#knowledge-quote-details').open=!!note.quote;$('#knowledge-note-text').value=note.text;$('#knowledge-note-form').onsubmit=saveKnowledgeNote;$('#knowledge-note-quote').oninput=$('#knowledge-note-text').oninput=()=>rememberKnowledgeNote(p.id);loadKnowledgeNotes(p.id);}
 document.querySelectorAll('[data-knowledge-link]').forEach(b=>b.onchange=()=>changeKnowledge('links',[...document.querySelectorAll('[data-knowledge-link]:checked')].map(v=>v.dataset.knowledgeLink)));
 if(sameDocument&&$('.knowledge-paper'))$('.knowledge-paper').scrollTop=paperScroll;
}
function rememberKnowledgeNote(id){knowledgeNoteDrafts.set(id,{quote:$('#knowledge-note-quote').value,text:$('#knowledge-note-text').value});}
function changeKnowledge(key,value){knowledgeDraft[key]=value;knowledgeDraft.dirty=true;$('#knowledge-dirty-status').textContent='有未保存修改';}
async function loadKnowledgeNotes(id){
 const token=++knowledgeNotesToken;try{const notes=await api('/api/notes?kind=wiki&id='+id);if(token!==knowledgeNotesToken||pageId!==id||!$('#knowledge-notes'))return;$('#knowledge-notes').innerHTML=notes.map(n=>`<article class="reading-note">${n.quote?'<blockquote>'+esc(n.quote)+'</blockquote>':''}<p>${esc(n.text)}</p><small>${new Date(n.created).toLocaleDateString('zh-CN')}</small></article>`).join('')||'<div class="knowledge-notes-empty"><svg class="icon" aria-hidden="true"><use href="#i-chat"/></svg><p>你的批注会留在这里</p></div>';}catch(e){if(token===knowledgeNotesToken&&pageId===id&&$('#knowledge-note-error'))$('#knowledge-note-error').textContent=e.message;}
}
async function saveKnowledgeNote(e){e.preventDefault();const id=pageId,note={quote:$('#knowledge-note-quote').value,text:$('#knowledge-note-text').value};try{await api('/api/notes',{kind:'wiki',id,...note});const draft=knowledgeNoteDrafts.get(id);if(!draft||draft.quote===note.quote&&draft.text===note.text)knowledgeNoteDrafts.delete(id);if(pageId!==id)return;if(!knowledgeNoteDrafts.has(id)&&$('#knowledge-note-quote')){$('#knowledge-note-quote').value='';$('#knowledge-note-text').value='';}await loadKnowledgeNotes(id);toast('批注已保存');}catch(err){if(pageId===id&&$('#knowledge-note-error'))$('#knowledge-note-error').textContent=err.message;}}
async function saveKnowledge(){
 const d=knowledgeDraft,p=pages().find(p=>p.id===d?.id);if(!p)return;
 try{let tags=[...new Set(d.tags.split(/[,，]/).map(t=>t.trim()).filter(Boolean))];if(p.body.tags.includes('周刊')&&!tags.includes('周刊'))tags.unshift('周刊');
 const saved=await api('/api/wiki',{id:d.id,revision:d.revision,page:{...p.body,title:d.title,summary:d.summary,content:d.content,tags,links:d.links}});knowledgeDraft=null;knowledgeEditing=false;pageId=saved.id;knowledgeSignature='';await load();toast('已保存为 v'+saved.revision);
 }catch(e){$('#knowledge-save-error').textContent=e.message;}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;const d=b.dataset;
 if(d.knowledgeDirectoryToggle!==undefined)setKnowledgeDirectory(!knowledgeDirectoryOpen);
 if(d.knowledgeDirectoryClose!==undefined)setKnowledgeDirectory(false);
 if(d.knowledgeInspectorToggle!==undefined)setKnowledgeInspector(!knowledgeInspectorOpen);
 if(d.knowledgePage){if(pageId!==d.knowledgePage&&!await leaveKnowledge())return;pageId=d.knowledgePage;knowledgeEditing=false;knowledgeSignature='';renderKnowledge();if(false)setKnowledgeDirectory(false);}
 if(d.knowledgeMode){knowledgeEditing=d.knowledgeMode==='edit';if(knowledgeEditing)knowledgeSide='changes';knowledgeSignature='';renderKnowledge();}
 if(d.knowledgeSide){knowledgeSide=d.knowledgeSide;knowledgeSignature='';renderKnowledge();}
 if(d.knowledgeSave!==undefined)await saveKnowledge();
 if(d.knowledgeDiscard!==undefined&&await leaveKnowledge()){knowledgeSignature='';renderKnowledge();}
 if(d.knowledgeExcerpt!==undefined){const selection=window.getSelection(),text=selection?.toString().trim(),prose=$('#knowledge-prose');if(!text||!prose?.contains(selection.anchorNode)||!prose.contains(selection.focusNode))return toast('先选中阅读区域里的原文');$('#knowledge-quote-details').open=true;$('#knowledge-note-quote').value=text.slice(0,1200);rememberKnowledgeNote(pageId);$('#knowledge-note-text').focus();}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&view==='wiki'&&knowledgeDirectoryOpen&&!document.querySelector('dialog[open]'))setKnowledgeDirectory(false);});
window.addEventListener('beforeunload',e=>{if(knowledgeDirty()){e.preventDefault();e.returnValue='';}});
