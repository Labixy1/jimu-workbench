'use strict';
let referenceFolder='',draftJobId=null,draftBuffer=null,draftEditing=false;
function renderReferencePicker(){
 const cats=state.categories||[],items=catalogItems();
 const selected=a=>a.type==='original'?sourceIds.has(a.id):a.type==='board'?boardRefs.has(a.id):documentRefs.has(a.id);
 const descendants=id=>{const ids=new Set([id]);let changed=true;while(changed){changed=false;cats.forEach(c=>{if(ids.has(c.parent_id)&&!ids.has(c.id)){ids.add(c.id);changed=true;}});}return ids;};
 const folderFiles=id=>{const ids=descendants(id);return items.filter(a=>ids.has(a.category_id));};
 const tree=(parent,scope,depth=0)=>cats.filter(c=>c.parent_id===parent&&c.scope===scope).map(c=>`<button class="${referenceFolder===c.id?'active':''}" style="padding-left:${12+depth*14}px" data-ref-folder="${esc(c.id)}">${assetIcon('folder')}<span>${esc(c.name)}</span></button>${tree(c.id,scope,depth+1)}`).join('');
 const visible=referenceFolder?items.filter(a=>a.category_id===referenceFolder):items;
 const selection=referenceFolder?folderFiles(referenceFolder):items;
 $('#context-options').innerHTML=`<div class="reference-tree"><button data-ref-folder="" class="${!referenceFolder?'active':''}">${assetIcon('folder')}<span>所有资产</span></button><h4>资料库</h4>${tree('','materials')}<h4>创作成果</h4>${tree('','creations')}</div><div class="reference-files"><div class="reference-selection-toolbar"><label><input type="checkbox" data-ref-select-all ${selection.length&&selection.every(selected)?'checked':''} ${!selection.length?'disabled':''}><span>${referenceFolder?'全选此文件夹':'全选所有文件'}</span></label><small>${selection.length} 个文件${referenceFolder?' · 含子文件夹':''}</small></div><div class="reference-file-list">${cats.filter(c=>c.parent_id===referenceFolder&&referenceFolder).map(c=>{const list=folderFiles(c.id);return `<label class="context-option"><input type="checkbox" data-ref-select-folder="${esc(c.id)}" ${list.length&&list.every(selected)?'checked':''}>${assetIcon('folder')}<span>${esc(c.name)}<small>${list.length} 个文件 · 包含子文件夹</small></span></label>`;}).join('')}${visible.map(a=>`<label class="context-option"><input type="checkbox" data-ref-asset="${esc(a.id)}" ${selected(a)?'checked':''}>${assetIcon(assetExtension(a))}<span>${esc(a.title)}<small>${esc(assetExtension(a).toUpperCase())}</small></span></label>`).join('')||'<p class="empty">此文件夹没有文件</p>'}</div></div>`;
 const check=$('[data-ref-select-all]');
 check.indeterminate=selection.some(selected)&&!selection.every(selected);
 check.onchange=()=>{selection.forEach(a=>setReference(a,check.checked));render();renderReferencePicker();};
 updateContextBudget();
}
function setReference(a,on){if(a.type==='original'){on?sourceIds.add(a.id):sourceIds.delete(a.id);}else{const map=a.type==='board'?boardRefs:documentRefs;on?map.set(a.id,a.revision):map.delete(a.id);}}
document.addEventListener('change',e=>{const d=e.target.dataset;if(d.refAsset)setReference(catalogItems().find(a=>a.id===d.refAsset),e.target.checked);if(d.refSelectFolder){const ids=new Set([d.refSelectFolder]);let changed=true;while(changed){changed=false;(state.categories||[]).forEach(c=>{if(ids.has(c.parent_id)&&!ids.has(c.id)){ids.add(c.id);changed=true;}});}catalogItems().filter(a=>ids.has(a.category_id)).forEach(a=>setReference(a,e.target.checked));}if(d.refAsset||d.refSelectFolder){render();renderReferencePicker();}});
document.addEventListener('click',e=>{const b=e.target.closest('[data-ref-folder]');if(b){referenceFolder=b.dataset.refFolder;renderReferencePicker();}});
const composerMenu=$('.task-menu'),composerDetails=$('.composer-menu');
async function showFlyout(type){
 if(type==='website'&&!connectionData){await loadConnections();if(!composerDetails.open)return;}
 let panel=$('#reference-flyout');if(!panel){panel=document.createElement('div');panel.id='reference-flyout';composerMenu.append(panel);}
 panel.hidden=false;panel.dataset.type=type;
 const rows=type==='skill'?(state.skills||[]):(connectionData?.links||[]);
 panel.innerHTML=rows.map(r=>`<button type="button" data-flyout-${type}="${esc(r.id)}"><strong>${esc(type==='skill'?r.title:r.name)}</strong><small>${esc(r.description||r.url||'')}</small></button>`).join('')||'<p>暂无内容</p>';
}
for(const [id,type] of [['attach-skill','skill'],['attach-website','website']]){
 const button=$('#'+id);button.onclick=()=>showFlyout(type);button.onmouseenter=()=>showFlyout(type);button.onfocus=()=>showFlyout(type);
}
for(const id of ['chat-local-file','attach-source'])$('#'+id).onmouseenter=()=>{if($('#reference-flyout'))$('#reference-flyout').hidden=true;};
composerDetails.addEventListener('toggle',()=>{if(!composerDetails.open&&$('#reference-flyout'))$('#reference-flyout').hidden=true;});
document.addEventListener('click',e=>{const b=e.target.closest('[data-flyout-skill],[data-flyout-website]');if(!b)return;
 if(b.dataset.flyoutSkill){const s=state.skills.find(s=>s.id===b.dataset.flyoutSkill);skillRefs.set(s.id,s.revision);if(['knowledge-compilation','board-generation'].includes(s.id))kind='wiki';}
 else{const l=connectionData.links.find(l=>l.id===b.dataset.flyoutWebsite);if(websiteRefs.size>=5&&!websiteRefs.has(l.id))return toast('本次最多引用5个网站');websiteRefs.set(l.id,l);}
 composerDetails.open=false;render();$('#prompt').focus();
});
function proposalFile(j){const p=j.payload,proposal=p.proposal;if(!proposal)return null;if(p.user_draft)return p.user_draft;if(p.kind==='wiki')return proposal.page;if(p.kind==='document')return proposal.document;if(['experience','tailor'].includes(p.kind))return {title:proposal.title,content:proposal.general||proposal.tailored};return null;}
function renderReview(){if(draftJobId&&state.jobs.find(j=>j.id===draftJobId)?.conversation_id!==cid){if(!draftBuffer?.dirty){draftJobId=null;draftBuffer=null;}}if($('#draft-file-panel'))$('#draft-file-panel').hidden=view!=='home'||!draftJobId;const j=job(),panel=$('#review-panel');panel.hidden=!j||!['review','approved'].includes(j.status);if(panel.hidden){panel.innerHTML='';return;}const f=proposalFile(j);panel.innerHTML=f?`<button class="chat-file-card" data-open-job-file="${esc(j.id)}"><svg class="icon"><use href="#i-book"/></svg><span><strong>${esc(f.title)}${j.payload.output_board?'.excalidraw':'.md'}</strong><small>${j.payload.output_board?'画板':'Markdown'} · ${j.status==='approved'?'已加入资产':'打开查看'}</small></span><span>↗</span></button>`:'';}
function openJobFile(id){const j=state.jobs.find(j=>j.id===id);if(!j)return;if(j.payload.output_board){openJobBoard(id);return;}if(j.status==='approved'){openDocument(j.payload.published_id);return;}if(draftJobId===id&&draftBuffer){renderDraftPanel();return;}if(draftJobId!==id&&draftBuffer?.dirty&&!window.confirm('放弃未保存的文稿修改？'))return;draftJobId=id;draftBuffer={...proposalFile(j),updated:j.updated,revision:j.payload.draft_revision||0,dirty:false};draftEditing=false;renderDraftPanel();}
function renderDraftPanel(){let panel=$('#draft-file-panel');if(!panel){panel=document.createElement('aside');panel.id='draft-file-panel';panel.className='draft-file-panel';$('#home-view').append(panel);}const j=state.jobs.find(j=>j.id===draftJobId);panel.hidden=!j||!draftBuffer;if(panel.hidden)return;
 panel.innerHTML=`<header><strong>${esc(draftBuffer.title)}</strong><button data-draft-close aria-label="关闭文稿">×</button></header><nav><div><button data-draft-tab="preview" class="${!draftEditing?'active':''}">预览</button><button data-draft-tab="edit" class="${draftEditing?'active':''}">编辑</button></div>${draftEditing?'<button data-draft-save>保存修改</button>':''}</nav>${draftEditing?`<div class="draft-fields"><input id="draft-file-title" value="${esc(draftBuffer.title)}" maxlength="100" aria-label="标题"><textarea id="draft-file-content" spellcheck="false" aria-label="Markdown正文">${esc(draftBuffer.content)}</textarea></div>`:`<div class="markdown draft-body">${md(draftBuffer.content)}</div>`}<footer><select id="draft-destination" aria-label="保存文件夹">${categoryOptions('','creations')}</select><button class="primary" data-draft-add>加入资产</button></footer><p id="draft-file-error" class="error"></p>`;
}
async function saveDraft(){if(!draftBuffer.dirty)return;const saved=await api('/api/jobs/'+draftJobId+'/draft',{title:draftBuffer.title,content:draftBuffer.content,expected_updated:draftBuffer.updated,expected_revision:draftBuffer.revision});draftBuffer={...saved.payload.user_draft,updated:saved.updated,revision:saved.payload.draft_revision||0,dirty:false};await load();}
document.addEventListener('input',e=>{if(e.target.id==='draft-file-title'||e.target.id==='draft-file-content'){draftBuffer[e.target.id==='draft-file-title'?'title':'content']=e.target.value;draftBuffer.dirty=true;}});
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;try{
 if(d.openJobFile)openJobFile(d.openJobFile);if(Object.hasOwn(d,'showReview')&&job())openJobFile(job().id);
 if(Object.hasOwn(d,'draftClose')){if(draftBuffer?.dirty&&!window.confirm('放弃未保存的文稿修改？'))return;draftJobId=null;draftBuffer=null;$('#draft-file-panel').hidden=true;}
 if(d.draftTab){draftEditing=d.draftTab==='edit';renderDraftPanel();}
 if(Object.hasOwn(d,'draftSave')){await saveDraft();toast('修改已保存，尚未加入资产');}
 if(Object.hasOwn(d,'draftAdd')){const category=$('#draft-destination').value;await saveDraft();const j=state.jobs.find(j=>j.id===draftJobId);let extra={category_id:category};if(['experience','tailor'].includes(j.payload.kind)){if(!await confirm('确认经历事实？','加入资产前，请确认文稿中的本人职责、数据和贡献均真实，改写没有新增未经证实的贡献。'))return;if(j.payload.kind==='experience')extra.confirmed_fact_ids=j.payload.proposal.facts.map(f=>f.id);else extra.confirm_no_new_claims=true;}if(j.payload.kind==='document')extra.confirmed=true;const a=await api('/api/jobs/'+draftJobId+'/approve',extra);draftJobId=null;draftBuffer=null;$('#draft-file-panel').hidden=true;await load();await openDocument(a.id);toast('已加入资产');}
 }catch(err){if($('#draft-file-error'))$('#draft-file-error').textContent=err.message;else toast(err.message);}});
window.addEventListener('beforeunload',e=>{if(draftBuffer?.dirty){e.preventDefault();e.returnValue='';}});
let boardDraftJob=null;
async function openJobBoard(id){const j=state.jobs.find(j=>j.id===id);if(j.status==='approved'){await openBoard(j.payload.published_id);return;}await openBoard();boardDraftJob=id;$('#board-title').value=j.payload.proposal.page.title;$('#board-status').textContent='尚未加入资产';boardModule.mountBoard($('#board-container'),j.payload.board_draft_scene);$('#board-save').textContent='加入资产';}
const normalBoardSave=$('#board-save').onclick;
$('#board-save').onclick=async()=>{if(!boardDraftJob)return normalBoardSave();const b=$('#board-save');b.disabled=true;try{let j=state.jobs.find(j=>j.id===boardDraftJob);j=await api('/api/jobs/'+j.id+'/draft',{scene:boardModule.boardScene(),title:$('#board-title').value,expected_updated:j.updated,expected_revision:j.payload.draft_revision||0});const a=await api('/api/jobs/'+j.id+'/approve',{category_id:$('#board-destination').value});boardDraftJob=null;boardId=a.id;boardRevision=a.revision;boardDirty=false;$('#board-save').textContent='保存';$('#board-status').textContent='已加入资产';await load();toast('画板已加入创作成果');}catch(err){$('#board-error').textContent=err.message;}finally{b.disabled=false;}};
$('#board-dialog').addEventListener('close',()=>{boardDraftJob=null;$('#board-save').textContent='保存';});
document.addEventListener('click',e=>{if(e.target.closest('[data-built-in-board]'))openBoard();});
