'use strict';
function clipperPayload(hash){
 if(!hash.startsWith('#clip='))return null;
 const encoded=hash.slice(6);
 if(!/^[a-zA-Z0-9_-]+$/.test(encoded)||encoded.length>240000)throw Error('网页采集内容格式错误或过大');
 const binary=atob(encoded.replace(/-/g,'+').replace(/_/g,'/')),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
 const data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
 if(typeof data.title!=='string'||!data.title.trim()||data.title.length>200||typeof data.content!=='string'||data.content.length<20||data.content.length>40000)throw Error('请检查标题与正文长度');
 const url=new URL(data.url);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('采集来源网址无效');
 const keep=new Set(['id','p','v','article','article_id','post','page','story']);
 if(url.hostname==='mp.weixin.qq.com'){for(const key of ['__biz','mid','idx','sn'])keep.add(key);if(!url.searchParams.has('mid')&&url.searchParams.has('signature'))for(const key of ['src','timestamp','ver','signature','new'])keep.add(key);}
 for(const key of [...url.searchParams.keys()])if(!keep.has(key))url.searchParams.delete(key);url.hash='';
 if(data.category&&!['jd','article','reference'].includes(data.category))throw Error('采集分类无效');
 return {...data,url:url.href};
}
async function receiveClip(){
 if(!location.hash.startsWith('#clip='))return;
 const hash=location.hash;history.replaceState(null,'',location.pathname+location.search);
 try{const data=clipperPayload(hash);await openCaptureDialog(data);}catch(error){toast(error.message);}
}
window.addEventListener('hashchange',receiveClip);
