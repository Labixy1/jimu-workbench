'use strict';
if(new URLSearchParams(location.search).get('showcase')==='1'){
 const originalFetch=window.fetch.bind(window),bundle=originalFetch('/showcase-data.json').then(r=>r.json());
 const respond=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
 window.fetch=async(input,options={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  if(!url.pathname.startsWith('/api/'))return originalFetch(input,options);
  const data=await bundle,path=url.pathname,method=(options.method||(typeof input==='object'&&input.method)||'GET').toUpperCase();
  if(method!=='GET')return new Response(JSON.stringify({error:'公开演示副本不能调用模型或保存数据；请在本地正常空间操作。'}),{status:400,headers:{'Content-Type':'application/json'}});
  if(path==='/api/state')return respond(data.state);
  if(path==='/api/connections')return respond({links:data.state.tool_links||[],github:{cli_installed:false},browser_use:{connected:false}});
  if(path==='/api/sites')return respond(data.sites||[]);
  if(path==='/api/usage')return respond(data.usage);
  if(path==='/api/notes')return respond(data.notes.filter(n=>n.target_id===url.searchParams.get('id')));
  if(path.startsWith('/api/conversations/')){const id=path.split('/').pop();return respond({messages:data.messages[id]||[],jobs:data.state.jobs.filter(j=>j.conversation_id===id)});}
  if(path.endsWith('/versions'))return respond(data.versions[path.split('/')[3]]||[]);
  if(path==='/api/archived')return respond({sources:[],artifacts:[],conversations:[]});
  return respond({});
 };
 document.addEventListener('DOMContentLoaded',()=>{
  const banner=document.querySelector('#test-mode');banner.hidden=false;
  banner.textContent='公开演示 · 真实结果回看';
  const link=document.querySelector('#demo-link');link.textContent='本地完整版';link.href='/';
  document.querySelector('.brand').href='/?showcase=1';
 });
}
