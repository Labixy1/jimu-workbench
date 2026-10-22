'use strict';
let capturePreview=null,captureBusy=false,captureBrowserOpen=false;
function captureHasEdits(){return !!capturePreview&&($('#capture-title').value!==capturePreview.article.title||$('#capture-content').value!==capturePreview.article.content);}
async function closeCaptureDialog(){
 if(captureBusy)return;
 if(captureHasEdits()&&!await confirm('放弃采集修改？','修改尚未保存。取消后可以继续编辑并保存到资产。'))return;
 $('#capture-dialog').close();
}
function captureFolderOptions(){
 const folders=state.categories||[],byId=new Map(folders.map(f=>[f.id,f]));
 const label=folder=>{const parts=[folder.name];let p=folder.parent_id,seen=new Set([folder.id]);while(p&&byId.has(p)&&!seen.has(p)){seen.add(p);parts.unshift(byId.get(p).name);p=byId.get(p).parent_id;}return (folder.scope==='creations'?'创作成果':'资料库')+' / '+parts.join(' / ');};
 return '<option value="">资料库</option>'+folders.map(f=>`<option value="${esc(f.id)}">${esc(label(f))}</option>`).join('');
}
async function openCaptureDialog(article=null,url='',favorite=false){
 let dialog=$('#capture-dialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='capture-dialog';document.body.append(dialog);}
 if(captureBusy)return;
 capturePreview=null;
 dialog.innerHTML=`<header class="capture-header"><div><h2>采集网页</h2><span>阅读，然后留下有用的内容</span></div><button data-capture-close aria-label="关闭网页采集">×</button></header><form id="capture-url-form"><input id="capture-url" type="url" placeholder="粘贴文章链接 · 官网、公众号、小红书" aria-label="文章地址" required><button class="secondary" id="capture-fetch">读取网页</button><button type="button" class="secondary" id="capture-open-browser">用浏览器打开</button></form><div class="capture-browser-bar" id="capture-browser-bar" hidden><span>在独立浏览器完成登录、打开文章，再回来读取。</span><button id="capture-read-browser" class="secondary">读取当前页</button><button id="capture-end-browser" aria-label="关闭采集浏览器">结束</button></div><div class="capture-layout"><div class="capture-content"><div id="capture-empty"><svg class="icon"><use href="#i-link"/></svg><h3>把一篇好文章带回来</h3><p>先粘贴链接读取。需要登录的页面，可以用浏览器打开。</p></div><div id="capture-preview" hidden><img id="capture-cover" hidden alt="原文封面"><textarea id="capture-title" aria-label="文章标题" maxlength="200" rows="2"></textarea><div id="capture-meta"></div><textarea id="capture-content" aria-label="采集正文" maxlength="119000"></textarea></div></div><aside class="capture-destination"><h3>保存位置</h3><label>资产目录<select id="capture-folder">${captureFolderOptions()}</select></label><label class="capture-check"><input id="capture-reading" type="checkbox" checked>加入阅览室</label><label class="capture-check"><input id="capture-favorite" type="checkbox">同时收藏</label><label id="capture-group-label" hidden>收藏分类<select id="capture-group"><option value="">全部</option>${(state.reading?.groups||[]).map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('')}</select></label><div id="capture-trace"></div><p class="capture-private">只保存在本机，不自动发送给模型。</p></aside></div><footer class="capture-footer"><p id="capture-error" role="status"></p><button id="capture-save" class="primary" disabled>保存到资产</button></footer>`;
 $('#capture-url').value=article?.url||url;
 $('#capture-favorite').checked=favorite;
 $('#capture-group-label').hidden=!favorite;
 if(favorite&&typeof favoriteCategory==='string'&&favoriteCategory!=='all')$('#capture-group').value=favoriteCategory;
 $('#capture-favorite').onchange=()=>{$('#capture-group-label').hidden=!$('#capture-favorite').checked;};
 $('#capture-url-form').onsubmit=e=>{e.preventDefault();capturePreview=null;captureAction(()=>api('/api/capture/preview',{url:$('#capture-url').value,allow_remote:true}));};
 $('#capture-open-browser').onclick=()=>{capturePreview=null;captureAction(async()=>{const r=await api('/api/capture/browser/open',{url:$('#capture-url').value,allow_remote:true});captureBrowserOpen=r.opened;$('#capture-browser-bar').hidden=!r.opened;$('#capture-error').textContent='浏览器已打开，完成登录后点击「读取当前页」。';renderCaptureTrace(r.trace);return null;});};
 $('#capture-read-browser').onclick=()=>{capturePreview=null;captureAction(()=>api('/api/capture/browser/read',{allow_remote:true}));};
 $('#capture-end-browser').onclick=()=>captureAction(async()=>{await api('/api/capture/browser/close',{});captureBrowserOpen=false;$('#capture-browser-bar').hidden=true;$('#capture-error').textContent='采集浏览器已关闭。';return null;});
 $('#capture-save').onclick=async()=>{
  if(!capturePreview||captureBusy)return;
  await captureAction(async()=>{
   const result=await api('/api/capture/save',{id:capturePreview.id,title:$('#capture-title').value,content:$('#capture-content').value,category_id:$('#capture-folder').value,reading:$('#capture-reading').checked,favorite:$('#capture-favorite').checked,favorite_category:$('#capture-group').value});
   capturePreview=null;await load();dialog.close();toast(result.duplicate?'已保存的资料，不重复添加':'已保存到资产');
   if(result.news_id){await switchView('work');await openNewsPreview(result.news_id);}else{await switchView('sources');await selectAssetFile(result.source_id);}return null;
  });
 };
 dialog.oncancel=e=>{e.preventDefault();closeCaptureDialog();};
 if(!dialog.open)dialog.showModal();
 try{const status=await api('/api/capture/browser');captureBrowserOpen=status.opened;$('#capture-browser-bar').hidden=!status.opened;}catch{}
 if(article)await captureAction(()=>api('/api/capture/stage',{article}));
}
async function captureAction(action){
 if(captureBusy)return;captureBusy=true;$('#capture-error').textContent='处理中…';
 const controls=[...$('#capture-dialog').querySelectorAll('button')];controls.forEach(b=>b.disabled=true);
 try{const preview=await action();if(preview?.article){capturePreview=preview;showCapturePreview(preview);$('#capture-error').textContent='已读取，检查后保存。';}}
 catch(error){$('#capture-error').textContent=error.message;if(!capturePreview){$('#capture-preview').hidden=true;$('#capture-empty').hidden=false;}if(captureBrowserOpen){try{const status=await api('/api/capture/browser');renderCaptureTrace(status.trace);}catch{}}}
 finally{captureBusy=false;controls.forEach(b=>b.disabled=false);$('#capture-save').disabled=!capturePreview;}
}
function showCapturePreview(preview){
 const a=preview.article;$('#capture-empty').hidden=true;$('#capture-preview').hidden=false;
 $('#capture-title').value=a.title;$('#capture-content').value=a.content;$('#capture-url').value=a.url;
 $('#capture-meta').textContent=[a.source_name,a.published_at?new Date(a.published_at).toLocaleDateString('zh-CN'):a.published_label?'页面时间：'+a.published_label:'发布日期未提供'].filter(Boolean).join(' · ');
 const image=$('#capture-cover');image.hidden=!a.cover_url;image.onerror=()=>{image.hidden=true;};
 if(a.cover_url)image.src=scoped('/api/capture/'+preview.id+'/cover');else image.removeAttribute('src');
 $('#capture-reading').checked=a.content.length>=80;
 renderCaptureTrace(preview.trace);
}
function renderCaptureTrace(trace){$('#capture-trace').innerHTML=(trace||[]).length?'<h3>本次调用</h3>'+trace.map(t=>`<div><code>${esc(t.tool)}</code><span class="${t.status==='failed'?'failed':t.status==='running'?'running':''}">${t.status==='completed'?'完成':t.status==='failed'?'失败':'进行中'}</span></div>`).join(''):'';}
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-capture-open'))openCaptureDialog(null,b.dataset.captureUrl||'',Boolean(b.closest('.favorite-add-menu')));
 if(b.hasAttribute('data-capture-close'))closeCaptureDialog();
});
