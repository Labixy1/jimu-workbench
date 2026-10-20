'use strict';
const reviewDestinations=new Map();
const openFolders=new Set();
let libraryOrigin='materials',libraryType='all',libraryCategory='all',skillEditing=null,categoryEditing=null,categoryManaging=false;
let activeDocument=null,documentDraft=null,documentEditing=false,documentCollapsed=false;
function renderFramework(){
 $('#new-chat').classList.toggle('active',view==='home');
 if(view==='skills'){renderSkills();renderResources();}
 const chips=$('#source-chips');chips.querySelectorAll('[data-remove-skill],[data-remove-document],[data-remove-website]').forEach(b=>b.remove());
 chips.insertAdjacentHTML('beforeend',[...websiteRefs].map(([id,l])=>`<button type="button" data-remove-website="${esc(id)}">网站 · ${esc(l.name)} ×</button>`).join('')+[...skillRefs].map(([id])=>`<button type="button" data-remove-skill="${esc(id)}">技能 · ${esc(state.skills?.find(s=>s.id===id)?.title||id)} ×</button>`).join('')+[...documentRefs].map(([id])=>`<button type="button" data-remove-document="${esc(id)}">文稿 · ${esc(state.artifacts.find(a=>a.id===id)?.title||id)} ×</button>`).join(''));
 if(kind==='document'){$('#task-label').hidden=false;$('#task-label').textContent='修改当前文稿';}
 $('#document-reopen').hidden=!activeDocument||!documentCollapsed;
 $('#document-reopen').textContent=activeDocument?'打开 · '+activeDocument.title:'打开文稿';
 if(activeDocument){const current=state.artifacts.find(a=>a.id===activeDocument.id);if(!current||current.revision!==activeDocument.revision)$('#document-status').textContent='版本已变化 · 重新打开后再编辑';}
}
function saveDestinationMarkup(j){const category=reviewDestinations.has(j.id)?reviewDestinations.get(j.id):state.library?.find(a=>a.id===j.payload.document_target?.id)?.category_id||(['experience','tailor'].includes(j.payload.kind)?'career':j.payload.weekly_run_id?'learning':'');return `<label class="save-destination">保存到资产分类<select id="review-category" data-destination-job="${esc(j.id)}">${categoryOptions(category,'creations')}</select><small>AI生成是来源标记，保存后仍是普通资产，可移动和引用。</small></label>`;}
function categoryOptions(selected,scope='materials'){
 const cats=(state.categories||[]).filter(c=>(c.scope||'materials')===scope);
 const path=c=>{const parent=cats.find(p=>p.id===c.parent_id);return parent?path(parent)+' / '+c.name:c.name;};
 return '<option value="">根目录</option>'+cats.map(c=>`<option value="${esc(c.id)}" ${c.id===selected?'selected':''}>${esc(path(c))}</option>`).join('');
}
function populateSourceCategories(){$('#source-collection').innerHTML=categoryOptions(libraryCategory!=='all'?libraryCategory:'',libraryOrigin);}
function catalogItems(){return state.library||[...state.sources.map(s=>({id:s.id,title:s.title,type:'original',category_id:''})),...state.artifacts.filter(a=>['wiki','career','career_review','board'].includes(a.kind)).map(a=>({id:a.id,title:a.title,type:a.kind==='board'?'board':'document',category_id:'',revision:a.revision}))];}
function renderAssetCatalog(){renderAssetBrowser();}

function renderSkills(){
 $('#skill-list').innerHTML='<article class="extension-card"><div class="extension-card-head"><span class="extension-avatar">▱</span><button class="extension-title" data-built-in-board>画板</button><button class="extension-add" data-built-in-board title="新建画板">+</button></div><p>内置工具 · Excalidraw<br>本地编辑流程图，不是 MCP 连接器。引用“生成画板”技能可从材料生成图形。</p></article>'+(state.skills||[]).map(s=>`<article class="extension-card"><div class="extension-card-head"><span class="extension-avatar">${esc(s.title.slice(0,1))}</span><button class="extension-title" data-edit-skill="${esc(s.id)}" title="编辑技能">${esc(s.title)}</button><button class="extension-add" data-use-skill="${esc(s.id)}" aria-label="使用${esc(s.title)}" title="使用技能">+</button></div><p>${esc(s.description)}</p><div class="resource-delete-actions"><button data-delete-skill="${esc(s.id)}">删除</button></div></article>`).join('')||'<div class="empty">暂无技能。</div>';
}
function editSkill(id=null){
 skillEditing=state.skills?.find(s=>s.id===id)||null;
 $('#skill-editor-heading').textContent=skillEditing?'编辑技能':'新建技能';
 for(const key of ['title','description','instructions'])$('#skill-'+key).value=skillEditing?.[key]||(key==='instructions'?'## 使用场景\n在什么任务中引用这个技能？\n\n## 输入\n需要哪些文件、说明或参考资料？\n\n## 执行方法\n1. 先核对输入与目标，缺少必要信息时提出问题。\n2. 按你的方法处理材料，区分事实和建议。\n3. 检查结果与输入是否一致。\n\n## 输出\n规定结构、格式和篇幅，例如结论、证据、待确认事项。\n\n## 边界\n不编造来源、个人职责或业务效果；保存正式产物前等待用户确认。':'');
 $('#skill-error').textContent='';$('#skill-editor').showModal();
}
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-delete-skill]');if(!button)return;
 const skill=state.skills.find(s=>s.id===button.dataset.deleteSkill);if(!skill)return;
 if(!await confirm('删除「'+skill.title+'」？','从技能列表和引用选项中移除，不影响历史对话与已生成的资产。'))return;
 try{
  await api('/api/skills/remove',{id:skill.id,revision:skill.revision});
  skillRefs.delete(skill.id);await load();toast('技能已删除');
 }catch(err){toast(err.message);}
});
function skillPicker(){
 $('#skill-options').innerHTML=(state.skills||[]).filter(s=>s.id!=='weekly-reading').map(s=>`<label class="context-option"><input type="checkbox" data-context-skill="${esc(s.id)}" ${skillRefs.has(s.id)?'checked':''}><span><b>${esc(s.title)}</b><small>${esc(s.description)}</small></span></label>`).join('');$('#skill-picker').showModal();
}
async function useSkill(id){
 const s=state.skills.find(s=>s.id===id);if(!s)throw Error('技能不存在');
 if(id==='board-generation'){skillRefs.set(id,s.revision);kind='wiki';await switchView('home');render();$('#prompt').focus();return;}
 if(id==='weekly-reading'){await switchView('work');return;}
 skillRefs.set(id,s.revision);await switchView('home');render();
 if(id==='experience-writing')experienceDialog();
 else if(id==='jd-review')tailorDialog();
 else if(id==='knowledge-compilation'){kind='wiki';render();contextDialog();}
 $('#prompt').focus();
}
function renderReferencePicker(){
 const originals=state.sources.map(s=>`<label class="context-option"><input type="checkbox" data-context-source="${s.id}" ${sourceIds.has(s.id)?'checked':''}><span>${esc(s.title)}<small>原始材料 · ${s.content.length}字 · ${s.visibility==='public'?'公开':'私人'}</small></span></label>`).join('');
 const docs=state.artifacts.filter(a=>['wiki','career','career_review'].includes(a.kind)).map(a=>`<label class="context-option"><input type="checkbox" data-context-document="${a.id}" ${documentRefs.has(a.id)?'checked':''}><span>${esc(a.title)}<small>文稿 · v${a.revision}</small></span></label>`).join('');
 const boards=state.artifacts.filter(a=>a.kind==='board').map(a=>`<label class="context-option"><input type="checkbox" data-context-board="${a.id}" ${boardRefs.has(a.id)?'checked':''}><span>${esc(a.title)}<small>画板 · v${a.revision} · 只引用文字</small></span></label>`).join('');
 $('#context-options').innerHTML=originals+docs+boards||'<p class="empty">还没有材料，先添加一份资产。</p>';updateContextBudget();
}
function categoryManager(){categoryManaging=!categoryManaging;renderAssetCatalog();}
function isDocumentDirty(){return !!activeDocument&&!!documentDraft&&(documentDraft.title!==activeDocument.title||documentDraft.content!==activeDocument.content);}
async function leaveDocument(){if(isDocumentDirty()&&!await confirm('放弃未保存的修改？','修改还没有保存。取消后可继续编辑并保存版本。'))return false;return true;}
async function openDocument(id){
 const a=state.artifacts.find(a=>a.id===id);if(a?.kind==='board'){await openBoard(id);return;}
 if(!await leaveDocument())return false;
 let doc;
 if(new URLSearchParams(location.search).get('showcase')==='1'){if(!a)return;doc={id:a.id,title:a.title,kind:a.kind,revision:a.revision,content:a.body.content||a.body.general||a.body.tailored,citations:a.body.citations||[]};}
 else doc=await api('/api/documents/'+id);
 activeDocument=doc;documentDraft={title:doc.title,content:doc.content};documentEditing=false;documentCollapsed=false;
 $('#document-error').textContent='';$('#document-version-list').hidden=true;renderDocument();renderFramework();return true;
}
function renderDocument(){
 $('#document-panel').hidden=!activeDocument||documentCollapsed;
 if(!activeDocument)return;
 $('#document-name').textContent=activeDocument.title;
 $('#document-status').textContent='文稿资产 · v'+activeDocument.revision+(isDocumentDirty()?' · 未保存':'');
 $('#document-preview').innerHTML=md(documentDraft.content);$('#document-preview').hidden=documentEditing;
 $('#document-editor').hidden=!documentEditing;$('#document-save').hidden=!documentEditing;$('#document-save').disabled=!isDocumentDirty();
 $('#document-title').value=documentDraft.title;$('#document-content').value=documentDraft.content;
 $('#document-preview-tab').classList.toggle('active',!documentEditing);$('#document-edit-tab').classList.toggle('active',documentEditing);
 $('#document-ai').disabled=isDocumentDirty();$('#document-ai').title=isDocumentDirty()?'请先保存手动修改，再交给积木修改':'';
}
async function closeDocument(){if(!await leaveDocument())return false;activeDocument=null;documentDraft=null;documentEditing=false;documentCollapsed=false;$('#document-panel').hidden=true;renderFramework();return true;}
function renderDocumentReview(j){
 const old=j.payload.document_target,next=j.payload.proposal.document,panel=$('#review-panel');
 panel.innerHTML=`<div class="review-heading"><h2>文稿修改建议</h2><span class="hint">原文尚未修改</span></div><details><summary>原文 · v${old.revision}</summary><div class="markdown">${md(old.content)}</div></details><h3>${esc(next.title)}</h3><div class="markdown">${md(next.content)}</div><p class="review-warning">请检查是否保留有效事实、是否新增未经证实的职责或数据；确认后保存新版本。</p>${saveDestinationMarkup(j)}<div class="review-actions"><button class="secondary" data-reject="${j.id}">不采纳</button><button class="primary" data-approve="${j.id}">确认保存版本</button></div>`;
}
function selectSettingsTab(tab){for(const t of ['model','preferences','data'])$('#settings-'+t).hidden=t!==tab;document.querySelectorAll('[data-settings-tab]').forEach(b=>b.classList.toggle('active',b.dataset.settingsTab===tab));$('#settings-dialog .settings-content').scrollTop=0;}
$('#asset-new-document').onclick=()=>{editWiki();$('#editor-title').textContent='新建文稿';$('#wiki-summary').value='个人整理文稿';};
$('#skill-new').onclick=()=>editSkill();$('#attach-skill').onclick=skillPicker;
$('#category-add').onclick=()=>categoryManager();
$('#skill-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const saved=await api('/api/skills',{id:skillEditing?.id,revision:skillEditing?.revision,title:$('#skill-title').value,description:$('#skill-description').value,instructions:$('#skill-instructions').value});if(skillRefs.has(saved.id))skillRefs.set(saved.id,saved.revision);$('#skill-editor').close();await load();toast('技能已保存，下次请求使用新规则');}catch(err){$('#skill-error').textContent=err.message;}finally{b.disabled=false;}};
$('#category-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter,destination=categoryEditing&&{...categoryEditing},name=$('#category-name').value;if(!destination)return;button.disabled=true;try{const saved=await api('/api/categories',{name,scope:destination.scope,parent_id:destination.parent_id});libraryOrigin=destination.scope;libraryCategory=saved.id;if(destination.parent_id)openFolders.add(destination.parent_id);categoryEditing=null;$('#category-name').value='';await load();}catch(err){$('#category-error').textContent=err.message;}finally{button.disabled=false;}};
$('#document-preview-tab').onclick=()=>{documentEditing=false;renderDocument();};$('#document-edit-tab').onclick=()=>{documentEditing=true;renderDocument();};
$('#document-close').onclick=()=>{documentCollapsed=true;$('#document-panel').hidden=true;renderFramework();};$('#document-reopen').onclick=()=>{documentCollapsed=false;renderDocument();renderFramework();};
for(const [id,key] of [['document-title','title'],['document-content','content']])$('#'+id).oninput=e=>{documentDraft[key]=e.target.value;$('#document-status').textContent='文稿资产 · v'+activeDocument.revision+(isDocumentDirty()?' · 未保存':'');$('#document-save').disabled=!isDocumentDirty();$('#document-ai').disabled=isDocumentDirty();};
$('#document-save').onclick=async()=>{const b=$('#document-save');b.disabled=true;try{let confirmed=false;if(['career','career_review'].includes(activeDocument.kind)){confirmed=await confirm('确认经历修订？','请确认没有新增未经证实的职责、能力或结果。');if(!confirmed)return;}const saved=await api('/api/documents/save',{id:activeDocument.id,revision:activeDocument.revision,...documentDraft,confirmed});activeDocument={...activeDocument,title:saved.title,content:documentDraft.content,revision:saved.revision};documentDraft={title:activeDocument.title,content:activeDocument.content};await load();renderDocument();toast('已保存新版本，原件与旧版本保留');}catch(err){$('#document-error').textContent=err.message;}finally{b.disabled=!isDocumentDirty();}};
$('#document-reference').onclick=async()=>{documentRefs.set(activeDocument.id,activeDocument.revision);await switchView('home');render();$('#prompt').focus();};
$('#document-ai').onclick=async()=>{if(isDocumentDirty())return toast('先保存手动修改，再让积木修改');kind='document';documentRefs.set(activeDocument.id,activeDocument.revision);await switchView('home');render();$('#task-label').hidden=false;$('#task-label').textContent='修改当前文稿';$('#task-clear').hidden=false;$('#prompt').placeholder='描述这份文稿要怎么修改…';$('#prompt').focus();};
$('#document-export').onclick=()=>{const url=URL.createObjectURL(new Blob([documentDraft.content],{type:'text/markdown;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=documentDraft.title+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('#document-versions').onclick=async()=>{try{const versions=await api('/api/artifacts/'+activeDocument.id+'/versions');$('#document-version-list').innerHTML=versions.map(v=>`<div class="version-row"><span>v${v.revision} · ${esc(v.reason)}</span><button class="text-button" data-document-restore="${v.id}">恢复</button></div>`).join('');$('#document-version-list').hidden=!$('#document-version-list').hidden;}catch(err){$('#document-error').textContent=err.message;}};
document.addEventListener('change',async e=>{const d=e.target.dataset;try{
 if(d.categoryName){const c=state.categories.find(c=>c.id===d.categoryName);await api('/api/categories',{id:c.id,revision:c.revision,name:e.target.value});await load();}
 if(d.assetCategory){await api('/api/assets/category',{id:d.assetCategory,category_id:e.target.value});await load();}
 if(d.contextSkill){const s=state.skills.find(s=>s.id===d.contextSkill);if(e.target.checked){skillRefs.set(s.id,s.revision);}else skillRefs.delete(s.id);render();}
 if(d.contextDocument){const a=state.artifacts.find(a=>a.id===d.contextDocument);if(e.target.checked){if(documentRefs.size>=5){e.target.checked=false;return toast('最多引用5份文稿');}documentRefs.set(a.id,a.revision);}else documentRefs.delete(a.id);render();updateContextBudget();}
 }catch(err){toast(err.message);await load();}});
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;try{
 if(d.folderToggle){if(openFolders.has(d.folderToggle))openFolders.delete(d.folderToggle);else openFolders.add(d.folderToggle);renderAssetCatalog();}
 if(d.folderMenu){e.stopImmediatePropagation();const c=state.categories.find(c=>c.id===d.folderMenu);let menu=b.parentElement.querySelector('.folder-action-menu');if(menu){menu.remove();return;}menu=document.createElement('div');menu.className='folder-action-menu';menu.innerHTML=`<button data-folder-create-md="${esc(c.id)}">新增 MD 文件</button><button data-folder-upload="${esc(c.id)}">本地上传</button><button data-folder-new="${esc(c.id)}" data-folder-scope="${c.scope}">新建子文件夹</button><button data-folder-rename="${esc(c.id)}">重命名</button><button data-folder-move="${esc(c.id)}">移动到</button><button data-folder-up="${esc(c.id)}">上移</button><button data-folder-down="${esc(c.id)}">下移</button><button data-category-delete="${esc(c.id)}">删除文件夹</button>`;b.parentElement.append(menu);return;}
 if(d.folderRename){const c=state.categories.find(c=>c.id===d.folderRename),row=b.closest('.folder-entry');row.querySelector('.folder-action-menu')?.remove();const input=document.createElement('input');input.value=c.name;input.className='folder-rename-input';row.append(input);input.focus();input.onkeydown=async event=>{if(event.key==='Escape')input.remove();if(event.key==='Enter'){try{await api('/api/categories',{id:c.id,revision:c.revision,name:input.value});await load();}catch(err){toast(err.message);}}};}
 if(d.folderNew){categoryEditing={scope:d.folderScope,parent_id:d.folderNew==='root'?'':d.folderNew};$('#category-form').hidden=false;$('#category-name').placeholder='新建'+(categoryEditing.parent_id?'子':'')+'文件夹';b.closest('.folder-entry,.asset-origin-group').append($('#category-form'));$('#category-name').focus();}
 if(d.libraryType){libraryType=d.libraryType;renderAssetCatalog();}
 if(Object.hasOwn(d,'libraryCategory')){if(!await leaveAssetFile())return;assetSelectedId=null;libraryCategory=d.libraryCategory;libraryOrigin=d.libraryOrigin||libraryOrigin;renderAssetCatalog();}
 if(d.libraryOpen)await selectAssetFile(d.libraryOpen);
 if(d.libraryReference){if(!await leaveAssetFile())return;assetEditing=false;const a=catalogItems().find(a=>a.id===d.libraryReference);if(a.type==='original')sourceIds.add(a.id);else if(a.type==='board')boardRefs.set(a.id,a.revision);else documentRefs.set(a.id,a.revision);kind='chat';await switchView('home');render();$('#prompt').focus();}
 if(d.editSkill)editSkill(d.editSkill);if(d.useSkill)await useSkill(d.useSkill);
 if(d.removeSkill){skillRefs.delete(d.removeSkill);kind='chat';render();}if(d.removeDocument){documentRefs.delete(d.removeDocument);render();}
 if(d.categoryEdit)categoryManager(d.categoryEdit);
 if(d.categoryDelete){const c=state.categories.find(c=>c.id===d.categoryDelete);if(await confirm('删除「'+c.name+'」分类？','分类中的文件与文稿不会删除，会保留在根目录；子文件夹上移一级。')){await api('/api/categories/remove',{id:c.id,revision:c.revision});await load();}}
 if(d.settingsTab)selectSettingsTab(d.settingsTab);
 if(d.documentRestore){if(!await leaveDocument()||!await confirm('恢复旧版本？','以旧版内容创建一个新版本，不删除任何历史。'))return;const saved=await api('/api/artifacts/'+activeDocument.id+'/restore',{version_id:d.documentRestore,revision:activeDocument.revision});activeDocument=null;documentDraft=null;await load();await openDocument(saved.id);toast('已恢复为新版本');}
 }catch(err){toast(err.message);}});
window.addEventListener('beforeunload',e=>{if(isDocumentDirty()){e.preventDefault();e.returnValue='';}});

document.addEventListener('change',e=>{if(e.target.dataset.destinationJob)reviewDestinations.set(e.target.dataset.destinationJob,e.target.value);});

$('#attach-skill').onclick=()=>{const panel=$('#composer-skill-options');panel.hidden=!panel.hidden;panel.innerHTML=(state.skills||[]).map(s=>`<label><input type="checkbox" data-context-skill="${esc(s.id)}" ${skillRefs.has(s.id)?'checked':''}><span>${esc(s.title)}</span></label>`).join('');};
$('#chat-local-file').onclick=()=>{sourceMode='file';$('#source-form').reset();populateSourceCategories();$('#source-file').click();};
