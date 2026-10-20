'use strict';
const $=s=>document.querySelector(s);
function readVisiblePage(){
 const selected=window.getSelection()?.toString().trim();
 const region=document.querySelector('main,[role="main"],article')||document.body;
 const content=selected||region?.innerText?.trim()||'';
 const url=new URL(location.href);url.search='';url.hash='';
 return {title:document.title.slice(0,200),url:url.href,content};
}
$('#capture').onclick=async()=>{
 try{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  const url=new URL(tab.url);
  if(!['https:','http:'].includes(url.protocol))throw Error('请在普通网页中采集，不支持浏览器设置页。');
  const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:readVisiblePage});
  const data=results[0]?.result;
  if(!data?.content||data.content.length<20)throw Error('没有足够正文。请完成登录，或选中JD正文后重试。');
  if(data.content.length>20000)throw Error('正文超过2万字。请只选中需要的内容后重新采集，不会自动截断。');
  $('#title').value=data.title;$('#url').value=data.url;$('#content').value=data.content;$('#handoff').hidden=false;$('#status').textContent='检查正文，移除无关内容或敏感信息后再导入。';
 }catch(e){$('#status').textContent=e.message;}
};
$('#handoff').onsubmit=async e=>{
 e.preventDefault();
 try{
  const data={title:$('#title').value,url:$('#url').value,content:$('#content').value,category:$('#category').value};
  if(data.content.length<20||data.content.length>20000)throw Error('正文需为20至20000字。');
  const bytes=new TextEncoder().encode(JSON.stringify(data));let binary='';for(const b of bytes)binary+=String.fromCharCode(b);
  const payload=btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  await chrome.tabs.create({url:'http://127.0.0.1:8768/'+($('#space').value==='demo'?'?space=demo':'')+'#clip='+payload});
  $('#status').textContent='已打开积木预览。请在导入窗口检查并点击保存。';
 }catch(err){$('#status').textContent=err.message;}
};
