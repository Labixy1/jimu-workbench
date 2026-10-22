'use strict';
let resourceTab='skills',connectionData=null,connectionsLoading=false,connectionsError='',toolEditing=null,sourceMode='file',mcpState={};
function setSourceMode(mode){
 const next=['file','text','url'].includes(mode)?mode:'file';
 if(next!==sourceMode){pendingFile=null;$('#source-file').value='';$('#file-import-status').textContent='';}
 sourceMode=next;
 $('#source-upload').hidden=sourceMode!=='file';$('#source-url-field').hidden=sourceMode!=='url';
 $('#source-content-field').hidden=sourceMode==='file';$('#source-fetch').hidden=sourceMode!=='url';
 document.querySelectorAll('[data-source-mode]').forEach(b=>b.classList.toggle('active',b.dataset.sourceMode===sourceMode));
 $('#source-error').textContent='';
}
async function loadConnections(){
 if(connectionsLoading)return;
 connectionsLoading=true;connectionsError='';renderResources();
 try{connectionData=await api('/api/connections');mcpState=await api('/api/mcp');}
 catch(error){connectionsError=error.message;}
 finally{connectionsLoading=false;renderResources();}
}
function renderResources(){
 if(view!=='skills')return;
 const text={skills:['技能','Agent 按需加载的 Skill，也可以在对话中主动引用。'],connectors:['连接器','从外部获取材料，先预览，再保存到资产。'],tools:['常用网站','']}[resourceTab];
 $('#resource-heading').textContent=text[0];$('#resource-description').textContent=text[1];
 $('#skill-actions').hidden=resourceTab!=='skills';$('#tool-new').hidden=resourceTab!=='tools';
 for(const tab of ['skills','connectors','tools'])$('#resource-'+tab).hidden=tab!==resourceTab;
 document.querySelectorAll('[data-resource-tab]').forEach(b=>b.classList.toggle('active',b.dataset.resourceTab===resourceTab));
 if(resourceTab==='connectors'){
  $('#resource-connectors').innerHTML=`<div class="extension-grid">
   <article class="extension-card"><div class="extension-card-head"><span class="extension-avatar">G</span><button class="extension-title" data-connector-info="github">GitHub</button><button class="extension-add" data-mcp-connect="github" aria-label="连接GitHub MCP" title="连接GitHub MCP">${mcpState.github?.status==='connected'?'✓':'+'}</button></div><p>官方 MCP · 仓库、代码、Issue、PR。${esc(mcpLabel('github'))}</p><div class="connector-actions"><button data-open-github>导入 README</button><button data-mcp-github-test>测试读取</button></div></article>
   <article class="extension-card"><div class="extension-card-head"><span class="extension-avatar">B</span><button class="extension-title" data-browser-use>Browser Use</button><button class="extension-add" data-mcp-connect="browser_use" aria-label="连接Browser Use MCP" title="连接Browser Use MCP">${mcpState.browser_use?.status==='connected'?'✓':'+'}</button></div><p>本地 MCP · 打开网页、登录后读取。${esc(mcpLabel('browser_use'))}</p><div class="connector-actions"><button data-capture-open>采集网页</button></div></article>
   <article class="extension-card"><div class="extension-card-head"><span class="extension-avatar">↗</span><button class="extension-title" data-clipper-help>浏览器采集</button><button class="extension-add" data-clipper-help aria-label="安装浏览器采集" title="安装与使用">+</button></div><p>用自己的浏览器采集文章、封面和日期，选择目录后保存。</p><div class="connector-actions"><button data-clipper-help>安装与使用</button></div></article>
  </div>${connectionsError?'<p class="error">'+esc(connectionsError)+'</p>':''}`;
 }
 if(resourceTab==='tools'){
  if(!connectionData){$('#resource-tools').innerHTML=connectionsError?`<p class="error">${esc(connectionsError)}</p><button class="secondary" data-retry-connections>重试</button>`:'<p class="hint">正在读取常用网站…</p>';return;}
  const links=connectionData.links||[];
  $('#resource-tools').innerHTML=['设计','Vibe Coding','MCP与连接器','技能与Skill Hub','产品研究','模型与评测','AI官网','其他'].map(group=>{const rows=links.filter(l=>l.group===group);return rows.length?`<section class="tool-group"><h2>${group}</h2><div class="extension-grid">${rows.map(l=>`<article class="extension-card"><div class="extension-card-head"><span class="website-icon"><img src="/api/site-icon?id=${encodeURIComponent(l.id)}" alt="" loading="lazy" referrerpolicy="no-referrer"><span>${esc(l.name.slice(0,1))}</span></span><a class="extension-title" href="${esc(safeWebsite(l.url))}" target="_blank" rel="noopener noreferrer">${esc(l.name)}</a><button class="extension-add" data-edit-tool="${esc(l.id)}" aria-label="编辑${esc(l.name)}" title="编辑网站">⋯</button></div><p>${esc(l.description||new URL(safeWebsite(l.url)).hostname)}</p><div class="website-actions"><a href="${esc(safeWebsite(l.url))}" target="_blank" rel="noopener noreferrer">打开官网 ↗</a><button data-reference-website="${esc(l.id)}">引用到对话</button><button data-delete-tool="${esc(l.id)}">删除</button></div></article>`).join('')}</div></section>`:'';}).join('');
  $('#resource-tools').querySelectorAll('.website-icon img').forEach(img=>{img.onload=()=>img.parentElement.classList.add('icon-loaded');img.onerror=()=>img.remove();});
 }
}
function mcpLabel(name){const s=mcpState[name];return s?.status==='connected'?'已连接':s?.status==='needs_auth'?'需要授权':s?.error?'连接失败：'+s.error:'未连接';}
function safeWebsite(url){try{const p=new URL(url);return ['http:','https:'].includes(p.protocol)&&!p.username&&!p.password?p.href:'about:blank';}catch{return 'about:blank';}}
function editTool(id=null){
 toolEditing=connectionData?.links?.find(l=>l.id===id)||null;
 $('#tool-editor-heading').textContent=toolEditing?'编辑常用网站':'添加常用网站';
 for(const key of ['name','url','description'])$('#tool-'+key).value=toolEditing?.[key]||'';
 $('#tool-group').value=toolEditing?.group||'其他';$('#tool-error').textContent='';$('#tool-editor').showModal();
}
function githubDialog(){
 $('#github-connector-info').close();
 $('#github-form').reset();$('#github-error').textContent='';
 $('#github-auth-note').textContent=connectionData?.github?.cli_installed?'检测到本机 gh。读取时会检查现有登录，不读取或保存其令牌。':'公开仓库无需登录；私有仓库需安装 gh 并运行 gh auth login。本页不接收令牌。';
 $('#github-dialog').showModal();
}
$('#tool-new').onclick=async()=>{if(!connectionData)await loadConnections();if(connectionData)editTool();};
$('#tool-form').onsubmit=async e=>{
 e.preventDefault();const b=e.submitter;b.disabled=true;
 try{await api('/api/tool-links',{id:toolEditing?.id,revision:toolEditing?.revision,name:$('#tool-name').value,url:$('#tool-url').value,group:$('#tool-group').value,description:$('#tool-description').value});$('#tool-editor').close();await loadConnections();toast('已保存个人常用网站');}
 catch(err){$('#tool-error').textContent=err.message;}finally{b.disabled=false;}
};
$('#github-form').onsubmit=async e=>{
 e.preventDefault();const b=$('#github-read');b.disabled=true;$('#github-error').textContent='';
 try{
  const result=await api('/api/github/preview',{repo:$('#github-repo').value,allow_remote:true,allow_private:$('#github-private').checked});
  $('#github-dialog').close();sourceDialog('text');$('#source-title').value=result.title;$('#source-url').value=result.url;$('#source-content').value=result.content;$('#source-visibility').value=result.visibility;
  $('#file-import-status').textContent='已读取 GitHub README（'+(result.private?'私有':'公开')+'）。核对后点击保存；尚未入库，也未发送 DeepSeek。';
 }catch(err){$('#github-error').textContent=err.message;}finally{b.disabled=false;}
};
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;const d=b.dataset;
 try{
  if(d.mcpConnect){if(d.mcpConnect==='github'){$('#github-mcp-auth').showModal();}else{b.disabled=true;try{mcpState=await api('/api/mcp/connect',{name:d.mcpConnect});renderResources();}finally{b.disabled=false;}}}
  if(d.mcpRefresh!==undefined){mcpState=await api('/api/mcp');renderResources();}
  if(d.resourceTab){resourceTab=d.resourceTab;await switchView('skills');renderResources();if(!connectionData&&resourceTab!=='skills')await loadConnections();}
  if(d.importMode){b.closest('details')?.removeAttribute('open');sourceDialog(d.importMode);}
  if(d.sourceMode)setSourceMode(d.sourceMode);
  if(d.clipperHelp!==undefined||d.openGithub!==undefined)b.closest('details')?.removeAttribute('open');
  if(d.openGithub!==undefined)githubDialog();
  if(d.connectorInfo==='github')$('#github-connector-info').showModal();
  if(d.browserUse!==undefined)$('#browser-use-dialog').showModal();
  if(d.browserCapture!==undefined){$('#browser-use-dialog').close();openCaptureDialog();}
  if(d.mcpGithubTest!==undefined){b.disabled=true;try{const r=await api('/api/mcp/github-test',{allow_remote:true});toast('GitHub MCP 真实读取成功：'+r.repository+' · '+r.tool);}finally{b.disabled=false;}}
  if(d.browserManual!==undefined){$('#browser-use-dialog').close();$('#clipper-help').showModal();}
  if(d.editTool)editTool(d.editTool);
  if(d.deleteTool){const link=connectionData.links.find(l=>l.id===d.deleteTool);if(await confirm('移除「'+link.name+'」？','只移除这个网址入口，不删除已采集的资产。')){await api('/api/tool-links/remove',{id:link.id,revision:link.revision});websiteRefs.delete(link.id);await loadConnections();render();}}
  if(d.retryConnections!==undefined)await loadConnections();
 }catch(err){toast(err.message);}
});

$('#github-mcp-authorize').onclick=async()=>{try{const r=await api('/api/mcp/auth',{name:'github'});const a=$('#github-mcp-auth-link');a.href=r.authorizationUrl;a.hidden=false;a.textContent='打开 GitHub 授权页';}catch(e){$('#github-mcp-auth-error').textContent=e.message;}};
$('#github-use-local-login').onclick=async()=>{const b=$('#github-use-local-login');b.disabled=true;$('#github-mcp-auth-error').textContent='正在连接…';try{mcpState=await api('/api/mcp/github-login',{});if(mcpState.github?.status==='connected'){$('#github-mcp-auth').close();toast('GitHub 已连接 · 只读');}else $('#github-mcp-auth-error').textContent=mcpState.github?.error||'连接未完成';renderResources();}catch(error){$('#github-mcp-auth-error').textContent=error.message;}finally{b.disabled=false;}};
async function checkMcpPermissions(){try{const list=await api('/api/mcp/permissions');const panel=$('#mcp-permissions');panel.innerHTML=list.map(p=>`<article class="mcp-permission"><b>外部工具请求：${esc(p.permission)}</b><p>${esc((p.patterns||[]).join(', '))}</p><button data-mcp-reply="once" data-permission-id="${esc(p.id)}">允许本次</button><button data-mcp-reply="reject" data-permission-id="${esc(p.id)}">拒绝</button></article>`).join('');}catch{}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-mcp-reply]');if(!b)return;try{await api('/api/mcp/reply',{id:b.dataset.permissionId,reply:b.dataset.mcpReply});await checkMcpPermissions();}catch(err){toast(err.message);}});

$('#github-mcp-token-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{mcpState=await api('/api/mcp/github-token',{token:$('#github-mcp-token').value});$('#github-mcp-token').value='';if(mcpState.github?.status==='connected')$('#github-mcp-auth').close();else $('#github-mcp-auth-error').textContent=mcpState.github?.error||'授权未成功';renderResources();}catch(err){$('#github-mcp-auth-error').textContent=err.message;}finally{b.disabled=false;}};

const websiteRefs=new Map();
$('#attach-website').onclick=async()=>{if(!connectionData)await loadConnections();$('#website-options').innerHTML=(connectionData?.links||[]).map(l=>`<label class="context-option"><input type="checkbox" data-website-ref="${esc(l.id)}" ${websiteRefs.has(l.id)?'checked':''}><span><b>${esc(l.name)}</b><small>${esc(l.description||l.url)}</small></span></label>`).join('');$('#website-picker').showModal();};
document.addEventListener('change',e=>{if(e.target.dataset.websiteRef){const l=connectionData.links.find(l=>l.id===e.target.dataset.websiteRef);if(e.target.checked){if(websiteRefs.size>=5){e.target.checked=false;return toast('最多引用5个网站');}websiteRefs.set(l.id,l);}else websiteRefs.delete(l.id);render();}});
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.referenceWebsite){const l=connectionData.links.find(l=>l.id===b.dataset.referenceWebsite);if(websiteRefs.size>=5&&!websiteRefs.has(l.id))return toast('最多引用5个网站');websiteRefs.set(l.id,l);await switchView('home');render();$('#prompt').focus();}if(b.dataset.removeWebsite){websiteRefs.delete(b.dataset.removeWebsite);render();}});
$('#tool-fetch-metadata').onclick=async()=>{const b=$('#tool-fetch-metadata');b.disabled=true;try{const r=await api('/api/site-metadata',{url:$('#tool-url').value});if(r.title&&!$('#tool-name').value)$('#tool-name').value=r.title.slice(0,60);if(r.description)$('#tool-description').value=r.description.slice(0,200);else toast('官网未提供摘要，可手动填写');}catch(e){$('#tool-error').textContent=e.message;}finally{b.disabled=false;}};
