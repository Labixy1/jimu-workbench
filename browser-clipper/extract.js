'use strict';
function readVisiblePage(){
 const host=location.hostname,kind=host==='mp.weixin.qq.com'?'公众号':host.endsWith('xiaohongshu.com')?'小红书':'网页';
 const meta=name=>document.querySelector(`meta[property="${name}"],meta[name="${name}"]`)?.content?.trim()||'';
 const text=selector=>document.querySelector(selector)?.innerText?.trim()||'';
 const selection=window.getSelection()?.toString().trim()||'';
 const selectors=kind==='公众号'?['#js_content']:kind==='小红书'?['#detail-desc','.note-content']:['article','.entry-content','main','[role="main"]'];
 let region=null;for(const selector of selectors){region=document.querySelector(selector);if(region)break;}
 const content=selection||region?.innerText?.trim()||'';
 const title=text('#activity-name')||text('#detail-title')||meta('og:title')||document.title;
 const url=new URL(location.href),keep=new Set(['id','p','v','article','article_id','post','page','story']);
 if(kind==='公众号'){for(const key of ['__biz','mid','idx','sn'])keep.add(key);if(!url.searchParams.has('mid')&&url.searchParams.has('signature'))for(const key of ['src','timestamp','ver','signature','new'])keep.add(key);}
 for(const key of [...url.searchParams.keys()])if(!keep.has(key))url.searchParams.delete(key);url.hash='';
 const author=text('#js_name')||text('.author-name')||meta('author');
 let cover=meta('og:image')||meta('twitter:image');
 if(cover){try{cover=new URL(cover,location.href).href;if(!/^https?:/.test(cover)||/logo|avatar|qrcode|qr_code|(?:[/_.-])icon(?:[/_.-])/i.test(cover))cover='';}catch{cover='';}}
 let date=meta('article:published_time')||meta('datepublished')||document.querySelector('time[datetime]')?.getAttribute('datetime')||'';
 date=/T.*(?:Z|[+-]\d{2}:?\d{2})$/.test(date)&&!Number.isNaN(Date.parse(date))&&Date.parse(date)<=Date.now()?new Date(date).toISOString():null;
 const label=text('#publish_time')||text('.date')||'';
 return {title:title.trim().slice(0,200),url:url.href,content,cover_url:cover,published_at:date,published_label:label.slice(0,100),author,source_name:author||host,source_kind:kind,category:'article'};
}
