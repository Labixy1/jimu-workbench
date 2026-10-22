'use strict';
const $=s=>document.querySelector(s);
let captured=null;
try{$('#endpoint').value=localStorage.getItem('jimu-endpoint')||'http://127.0.0.1:8768';}catch{}
function localEndpoint(value){
 const url=new URL(value);
 if(url.protocol!=='http:'||!['localhost','127.0.0.1'].includes(url.hostname)||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('只支持本机积木地址，例如 http://127.0.0.1:8768');
 return url.origin;
}
$('#capture').onclick=async()=>{
 const button=$('#capture');button.disabled=true;$('#status').textContent='正在读取当前文章…';
 try{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  const url=new URL(tab.url);
  if(!['https:','http:'].includes(url.protocol))throw Error('请打开需要收藏的文章页面。');
  const results=await chrome.scripting.executeScript({target:{tabId:tab.id},func:readVisiblePage});
  captured=results[0]?.result;
  if(!captured?.content||captured.content.length<20)throw Error('没有读到正文。请完成登录，或选中文字后重试。');
  if(captured.content.length>40000)throw Error('正文超过4万字。请选中需要的内容后重新采集，不会自动截断。');
  if(/^(access denied|just a moment|环境异常|访问受限|验证中心)/i.test(captured.title))throw Error('这是验证或拦截页面，请正常完成登录后再采集。');
  $('#title').value=captured.title;$('#url').value=captured.url;$('#content').value=captured.content;$('#handoff').hidden=false;
  $('#metadata').textContent=[captured.source_kind,captured.published_at?new Date(captured.published_at).toLocaleDateString('zh-CN'):'未提供准确日期',captured.cover_url?'含原文封面':'无封面'].join(' · ');
  $('#status').textContent='已读取，可检查正文后带到积木。';
 }catch(e){$('#status').textContent=e.message;}finally{button.disabled=false;}
};
$('#handoff').onsubmit=async e=>{
 e.preventDefault();const button=e.submitter;button.disabled=true;
 try{
  const endpoint=localEndpoint($('#endpoint').value.trim());
  const data={...captured,title:$('#title').value,url:$('#url').value,content:$('#content').value,category:'article'};
  if(data.content.length<20||data.content.length>40000)throw Error('正文需为20至40000字。');
  const bytes=new TextEncoder().encode(JSON.stringify(data));let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
  const payload=btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  try{localStorage.setItem('jimu-endpoint',endpoint);}catch{}
  await chrome.tabs.create({url:endpoint+'/#clip='+payload});
  $('#status').textContent='已打开积木预览，点击保存后才入库。';
 }catch(error){$('#status').textContent=error.message;}finally{button.disabled=false;}
};
