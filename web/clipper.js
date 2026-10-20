'use strict';
function clipperPayload(hash){
 if(!hash.startsWith('#clip='))return null;
 const encoded=hash.slice(6);
 if(!/^[a-zA-Z0-9_-]+$/.test(encoded)||encoded.length>180000)throw Error('网页采集内容格式错误或过大');
 const binary=atob(encoded.replace(/-/g,'+').replace(/_/g,'/')),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
 const data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
 if(typeof data.title!=='string'||!data.title.trim()||data.title.length>200||typeof data.content!=='string'||data.content.length<20||data.content.length>20000)throw Error('请检查标题与正文长度');
 const url=new URL(data.url);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('采集来源网址无效');url.search='';url.hash='';
 if(!['jd','article','reference'].includes(data.category))throw Error('采集分类无效');
 return {...data,url:url.href};
}
function receiveClip(){
 if(!location.hash.startsWith('#clip='))return;
 const hash=location.hash;history.replaceState(null,'',location.pathname+location.search);
 try{const data=clipperPayload(hash);sourceDialog('text');$('#source-title').value=data.title;$('#source-content').value=data.content;$('#source-url').value=data.url;$('#source-category').value=data.category;$('#source-visibility').value='private';$('#file-import-status').textContent='来自浏览器采集：请核对正文，确认保存后才进入本机资产。不会自动发送模型。';}catch(e){toast(e.message);}
}
window.addEventListener('hashchange',receiveClip);
