'use strict';
let workTab='reading',deskSignature='',usageSnapshot=null,usageLoading=false,usageError='',balanceSnapshot=null,balanceLoading=false,balanceError='';
let readingFilter='all',newsSelection=new Set(),newsRefreshing=false,newsWarnings=[],newsGenerating=false;
let readingUpdateTimer=null,readingUpdatePolling=false;
function readingSubscriptions(){return state.weekly.subscriptions||((state.weekly.config?.id||state.weekly.config?.urls?.length)?[state.weekly.config]:[]);}
function subscriptionForPage(page,runs,subscriptions){
 if(state.weekly.page_subscriptions?.[page.id])return state.weekly.page_subscriptions[page.id];
 const run=runs.find(r=>r.published_id===page.id);
 if(run)return run.subscription_id||'sub_legacy';
 return 'history';
}
function subscriptionCards(items,runs){
 const busy=runs.some(r=>['collecting','queued','running'].includes(r.status));
 return items.map(c=>{const recent=runs.filter(r=>r.subscription_id===c.id),running=recent.find(r=>['collecting','queued','running'].includes(r.status)),pending=recent.filter(r=>r.status==='review').length;
 return `<article class="reading-subscription-card ${readingFilter===c.id?'selected':''}"><button class="subscription-name" data-reading-filter="${esc(c.id)}" aria-pressed="${readingFilter===c.id}"><strong>${esc(c.title)}</strong><span>${'手动更新'}</span></button><div class="subscription-source-preview">${c.urls.slice(0,2).map(url=>`<span title="${esc(url)}">${esc(new URL(url).hostname)}</span>`).join('')||'<span>未设置来源</span>'}${c.urls.length>2?`<span>+${c.urls.length-2}</span>`:''}</div><div class="subscription-card-status">${running?issueStates[running.status]:'手动采集，不自动运行'}${c.query?' · '+esc(c.query):''}</div><div class="subscription-card-actions"><button class="text-button" data-weekly-settings="${esc(c.id)}">设置</button><button class="text-button" data-subscription-remove="${esc(c.id)}" ${running?'disabled':''}>移除</button><button class="secondary" data-news-refresh="${esc(c.id)}" ${!c.urls.length||busy||newsRefreshing?'disabled':''} title="${busy?'另一个订阅更新中，请等待完成':'只更新这个订阅'}">${newsRefreshing?'刷新中…':running?'整理中…':'刷新资讯'}</button></div></article>`;}).join('');
}
const issueStates={collecting:'正在采集',queued:'等待生成',running:'正在生成',review:'待你审核',approved:'已保存',failed:'未完成',no_updates:'没有新内容',interrupted:'已中断',rejected:'未采纳'};
const localDate=value=>value?new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'尚未安排';
function scheduleLabel(config){return (config.frequency==='daily'?'每天':'每周'+['一','二','三','四','五','六','日'][config.weekday])+' '+config.time;}
function issueRows(items){return items.map(p=>`<button class="desk-issue" data-desk-issue="${p.id}"><span class="issue-date">${localDate(p.updated)}<small>${esc(p.body.tags.find(t=>t!=='周刊')||'阅读周刊')}</small></span><span class="issue-text"><strong>${esc(p.title)}</strong><span>${esc(p.body.summary)}</span></span><span class="issue-open">阅读 ↗</span></button>`).join('');}
function runRows(runs){return runs.map(r=>`<div class="desk-run"><div><strong>${esc(r.config?.title||'阅读任务')}</strong><span>${localDate(r.created)}</span>${r.error?`<p class="error">${esc(r.error)}</p>`:''}${r.warnings?.length?`<details><summary>采集说明 · ${r.warnings.length}</summary>${r.warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details>`:''}</div><div><span class="run-state ${esc(r.status)}">${issueStates[r.status]||esc(r.status)}</span>${r.published_id&&pages().some(p=>p.id===r.published_id)?`<button class="text-button" data-desk-issue="${r.published_id}">阅读</button>`:r.conversation_id&&state.conversations.some(c=>c.id===r.conversation_id)?`<button class="text-button" data-conversation="${r.conversation_id}">${r.status==='review'?'审核草稿':'查看过程'}</button>`:''}</div></div>`).join('');}
let readingCategory='all',readingCollection=[],readingCollectionLoaded=false;
const readingTopics=['全部','模型与Agent','产品与设计','电商经营'];
function topicFor(n){if(readingTopics.includes(n.topic))return n.topic;const text=(n.title+' '+n.excerpt).toLowerCase();return /电商|商家|营销|ecommerce|commerce/.test(text)?'电商经营':/design|产品|设计|workflow/.test(text)?'产品与设计':'模型与Agent';}
function collectionPanel(section,title){const items=readingCollection.filter(i=>i.section===section).map(i=>state.sources.find(s=>s.id===i.source_id&&!s.archived)).filter(Boolean);return `<section class="reading-block"><div class="reading-block-head"><h2>${title}</h2><button data-reading-add="${section}" aria-label="添加${title}">+</button></div>${items.length?items.map(s=>`<button class="reading-saved-row" data-source="${esc(s.id)}"><strong>${esc(s.title)}</strong><span>${esc(s.content.slice(0,70))}</span></button>`).join(''):`<div class="reading-empty">${section==='wechat'?'收下关注作者的新文章':'收集面经、面试题与自己的回答'}<button data-reading-add="${section}">添加文章</button></div>`}</section>`;}
let readingIssueId='latest';

function issuePeriodLabel(issue){
 if(!issue?.body.period_start)return weekRange(issue?new Date(issue.updated):new Date());
 const format=value=>value.slice(5).replace('-','/');
 return format(issue.body.period_start)+' — '+format(issue.body.period_end);
}
function findReadingNews(id){
 const archived=(state.reading?.issues||[]).find(p=>p.id===readingIssueId)?.body.news?.find(n=>n.id===id);
 return (state.weekly.news||[]).find(n=>n.id===id)||archived||(state.reading?.issues||[]).flatMap(p=>p.body.news||[]).find(n=>n.id===id);
}
function newsCoverPath(n){return scoped('/api/news/'+encodeURIComponent(n.id)+'/cover');}
function newsDateLabel(n){
 if(n.published_at)return new Date(n.published_at).toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'});
 return n.fetched_at?'采集 '+new Date(n.fetched_at).toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'}):'日期未提供';
}
function readingArticleCard(n){
 const preview=n.content_status==='browser'?(n.source_kind||'浏览器')+'正文':n.content_status==='article'?'正文':'来源摘要';
 const saved=(state.reading?.favorites||[]).includes(n.source_id);
 return `<article class="weekly-article-card"><button class="weekly-cover ${n.cover_url?'has-cover':'empty-cover'}" data-news-open="${esc(n.id)}" aria-label="预览${esc(n.title)}">${n.cover_url?`<img src="${newsCoverPath(n)}" alt="${esc(n.title)} · 原文封面" loading="lazy" decoding="async" data-reading-cover>`:''}</button><div class="weekly-card-content"><div class="reading-article-source"><span>${esc(newsSource(n))}</span><span>${esc(preview)}</span></div><button class="news-title" data-news-open="${esc(n.id)}">${esc(n.title)}</button><p>${esc((n.excerpt||'').slice(0,160))}</p><div class="weekly-card-meta"><button class="news-favorite" data-collect-news="${esc(n.id)}" title="收藏网页" ${saved?'disabled':''}>${saved?'已收藏':'收藏'}</button><time>${esc(newsDateLabel(n))}</time></div></div></article>`;
}
document.addEventListener('error',e=>{
 if(e.target.matches?.('[data-reading-cover]'))e.target.hidden=true;
 if(e.target.matches?.('[data-article-image]')){e.target.hidden=true;e.target.closest('figure')?.classList.add('image-unavailable');}
},true);
let activeNewsId='';
const newsImageAttempts=new Set(),newsReadsPending=new Set();
function newsArticleContent(n){
 if(!Array.isArray(n.content_blocks))return esc(n.content||n.excerpt||'');
 return n.content_blocks.map(block=>{
  if(block.type==='text')return `<div class="news-article-text">${esc(block.text)}</div>`;
  if(block.type!=='image'||!/^[a-f0-9]{24}$/.test(block.id))return '';
  const path=scoped('/api/news/'+encodeURIComponent(n.id)+'/images/'+block.id);
  return `<figure class="news-article-image"><img src="${path}" alt="${esc(block.alt||'原文配图')}" loading="lazy" decoding="async" data-article-image><figcaption>原文图片暂不可用，可前往原文查看。</figcaption></figure>`;
 }).join('');
}
function rememberReadingNews(n){
 const items=state.weekly.news||[];const index=items.findIndex(item=>item.id===n.id);
 if(index>=0)items[index]=n;else items.push(n);
 state.weekly.news=items;
}
async function readNewsArticle(n){
 if(!n||newsReadsPending.has(n.id))return;
 const id=n.id;newsImageAttempts.add(id);newsReadsPending.add(id);
 if(activeNewsId===id)renderNewsPreview(n);
 try{
  const result=await api('/api/news/enrich',{ids:[id],allow_remote:true});
  if(!result.items?.[0])throw Error('未读取到文章');
  n=result.items[0];rememberReadingNews(n);
 }catch(error){n={...n,read_error:error.message};rememberReadingNews(n);}
 finally{
  newsReadsPending.delete(id);
  if(activeNewsId===id&&$('#news-preview')?.open){
   const scroll=$('#news-preview .news-preview-scroll')?.scrollTop||0;
   renderNewsPreview(n);$('#news-preview .news-preview-scroll').scrollTop=scroll;
  }
 }
}
async function openNewsPreview(id){
 const n=findReadingNews(id);if(!n)throw Error('文章不存在，请刷新后重试');
 activeNewsId=id;
 let dialog=$('#news-preview');if(!dialog){dialog=document.createElement('dialog');dialog.id='news-preview';document.body.append(dialog);}
 renderNewsPreview(n);
 if(!dialog.open)dialog.showModal();
 if(n.content&&!Array.isArray(n.content_blocks)&&!newsImageAttempts.has(id))await readNewsArticle(n);
}
function renderNewsPreview(n){
 const complete=Boolean(n.content),label=n.content_status==='browser'?'浏览器采集正文':complete?'已读取正文':'订阅源摘要 · 非全文';
 const date=n.published_at?(n.published_label||new Date(n.published_at).toLocaleDateString('zh-CN')):[n.published_label?'页面时间：'+n.published_label:'发布日期未提供',newsDateLabel(n)].join(' · ');
 const saved=(state.reading?.favorites||[]).includes(n.source_id);
 const newsReadBusy=newsReadsPending.has(n.id);
 const inlineImages=(n.content_blocks||[]).some(block=>block.type==='image');
 $('#news-preview').innerHTML=`<header class="news-preview-toolbar"><span>${esc(newsSource(n))}</span><button data-news-preview-close aria-label="关闭文章预览">×</button></header><div class="news-preview-scroll">${n.cover_url&&!inlineImages?`<div class="news-preview-cover"><img src="${newsCoverPath(n)}" alt="${esc(n.title)} · 原文封面" data-reading-cover></div>`:''}<div class="news-preview-body"><div class="news-preview-meta"><span>${label}</span><time>${esc(date)}</time>${newsReadBusy?'<span role="status">正在补全图文…</span>':''}</div><h2>${esc(n.title)}</h2><div class="news-preview-copy">${newsArticleContent(n)}</div>${n.read_error?`<p class="news-read-error">${complete?'图文未能补全':'原文未能读取'}：${esc(n.read_error)}。${complete?'已保留现有正文。':'这里展示的仍是来源提供的摘要。'}</p>`:''}</div></div><footer class="news-preview-actions"><a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a><div>${!complete||n.read_error?`<button data-news-read="${esc(n.id)}" ${newsReadBusy?'disabled':''}>${newsReadBusy?'读取中…':complete?'重试图文':'读取正文'}</button>`:''}<button data-news-reference="${esc(n.id)}">带入对话</button><button data-news-note="${esc(n.id)}">做笔记</button><button data-collect-news="${esc(n.id)}" ${saved?'disabled':''}>${saved?'已收藏':'收藏'}</button></div></footer>`;
}
async function openNewsNotes(n){
 readerTarget={kind:'news',id:n.id};
 $('#reader-title').textContent=n.title;$('#reader-type').textContent=newsSource(n)+' · 阅读笔记';
 $('#reader-content').innerHTML=`<div class="news-reader-copy">${newsArticleContent(n)}</div>`;
 $('#reader-actions').innerHTML=`<button class="secondary" data-news-return="${esc(n.id)}">返回文章</button><a class="text-button" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>`;
 $('#note-quote').value='';$('#note-text').value='';$('#note-error').textContent='';
 await loadNotes();if(!$('#reader-dialog').open)$('#reader-dialog').showModal();
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 try{
 if(b.hasAttribute('data-news-preview-close')){$('#news-preview').close();activeNewsId='';}
 if(b.dataset.newsReference){const n=findReadingNews(b.dataset.newsReference);if(n){b.disabled=true;try{const r=await api('/api/news/reference',{id:n.id});await load();sourceIds.add(r.source_id);$('#news-preview').close();await switchView('home');render();$('#prompt').focus();}finally{b.disabled=false;}}}
 if(b.dataset.newsNote){const n=findReadingNews(b.dataset.newsNote);if(n){$('#news-preview').close();await openNewsNotes(n);}}
 if(b.dataset.newsReturn){$('#reader-dialog').close();await openNewsPreview(b.dataset.newsReturn);}
 if(b.dataset.newsRead)await readNewsArticle(findReadingNews(b.dataset.newsRead));
 }catch(error){toast(error.message);}
});

function favoriteNews(id){return (state.weekly.news||[]).find(n=>n.source_id===id)||(state.reading?.issues||[]).flatMap(p=>p.body.news||[]).find(n=>n.source_id===id);}
function readingFavoriteCard(a){
 const d=assetData(a.id),ext=assetExtension(a),article=favoriteNews(a.id);
 const cover=ext==='board'?boardThumbnail(d.doc.body.scene,a.id):article?(article.cover_url?`<img src="${newsCoverPath(article)}" alt="${esc(a.title)} · 原文封面" loading="lazy" data-reading-cover>`:''):`<div class="favorite-paper">${esc(d.content.slice(0,180))}</div>`;
 const action=article?`data-news-open="${esc(article.id)}"`:`data-favorite-open="${esc(a.id)}"`;
 return `<div class="favorite-entry" draggable="true" data-favorite-drag="${esc(a.id)}"><button class="reading-favorite-card" ${action}><div class="favorite-cover ${article?'is-article-cover':''}">${cover}</div><strong>${esc(a.title)}</strong><small>${esc(article?newsSource(article):ext==='board'?'画板':ext.toUpperCase())}</small></button>${d.source?.url?`<a class="favorite-web-link" href="${esc(safeWebsite(d.source.url))}" target="_blank" rel="noopener noreferrer">打开网页 ↗</a>`:''}<button class="favorite-remove" data-favorite-remove="${esc(a.id)}" aria-label="取消收藏${esc(a.title)}">×</button></div>`;
}

const defaultReadingFocus=[
 {name:'DeepSeek',kind:'官网',url:'https://api-docs.deepseek.com/updates',domains:['deepseek.com'],logo:'/brand/deepseek.svg',description:'开源模型、API 与开发者动态'},
 {name:'豆包',kind:'官网',url:'https://www.doubao.com/',domains:['doubao.com','volcengine.com'],logo:'/brand/doubao.png',description:'字节跳动的 AI 助手与模型产品'},
 {name:'OpenAI',kind:'官网',url:'https://openai.com/news/',domains:['openai.com'],logo:'/brand/openai.png',description:'ChatGPT、模型研究与产品更新'},
 {name:'Claude',kind:'官网',url:'https://www.anthropic.com/news',domains:['anthropic.com','claude.com','claude.ai'],logo:'/brand/anthropic.png',description:'Anthropic 的 AI 助手与研究动态'}
];
function focusHostname(url){try{return new URL(url).hostname;}catch{return '';}}
function focusMatches(f,n){
 if(f.domains){const host=focusHostname(n.feed_url||n.url);return f.domains.some(domain=>host===domain||host.endsWith('.'+domain));}
 return n.author_url===f.url||n.feed_url===f.url||n.url===f.url||n.source_name===f.name;
}
function focusDescription(f){
 if(f.description?.trim())return f.description.trim();
 return ({'官网':'产品介绍与官方更新','公众号':'关注这个账号的文章与观点','小红书账号':'关注这个账号的笔记与分享'})[f.kind]||'关注这个来源的新内容';
}
function focusLogo(f){
 const logo=f.logo||(f.kind==='官网'&&f.id?scoped('/api/site-icon?id='+encodeURIComponent(f.id)):'');
 const initial=Array.from(f.name||'').slice(0,/^[a-z]/i.test(f.name||'')?1:2).join('');
 return `<span class="focus-logo" aria-hidden="true"><span>${esc(initial)}</span>${logo?`<img src="${esc(logo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-focus-logo>`:''}</span>`;
}
function readingFocusCard(f){
 const list=(state.weekly.news||[]).filter(n=>focusMatches(f,n)).sort((a,b)=>String(b.published_at||b.fetched_at||'').localeCompare(String(a.published_at||a.fetched_at||''))).slice(0,3);
 // Social accounts share a hostname; only exact account matches belong on their cards.
 const sources=list.length?[]:state.sources.filter(s=>!s.archived&&s.url&&(s.url===f.url||f.kind==='官网'&&(f.domains?focusMatches(f,s):focusHostname(s.url)===focusHostname(f.url)))).slice(0,2);
 const updates=list.map(n=>`<button class="focus-update" data-news-open="${esc(n.id)}" title="${esc(n.title)}"><time>${esc(newsDateLabel(n))}</time><span>${esc(n.title)}</span></button>`).join('');
 const saved=sources.map(s=>`<button class="focus-update focus-saved-update" data-source="${esc(s.id)}" title="${esc(s.title)}"><span>${esc(s.title)}</span></button>`).join('');
 return `<article class="reading-focus"><a class="focus-identity" href="${esc(f.url)}" target="_blank" rel="noopener noreferrer" aria-label="打开${esc(f.name)}${esc(f.kind)}">${focusLogo(f)}<span class="focus-identity-copy"><strong>${esc(f.name)}</strong><small>${esc(f.kind)}</small></span><svg class="icon focus-external" aria-hidden="true" viewBox="0 0 20 20"><path d="M6 14 14 6M6 6h8v8"/></svg></a><p class="focus-description" title="${esc(focusDescription(f))}">${esc(focusDescription(f))}</p><div class="focus-updates">${updates||saved||'<p class="focus-empty">暂无已采集动态</p>'}</div></article>`;
}
document.addEventListener('load',e=>{if(e.target.matches?.('[data-focus-logo]'))e.target.parentElement.classList.add('logo-loaded');},true);
document.addEventListener('error',e=>{if(e.target.matches?.('[data-focus-logo]'))e.target.remove();},true);

function renderDesk(){
 if(view!=='work')return;
 if(!readingCollectionLoaded){readingCollectionLoaded=true;api('/api/reading/items').then(items=>{readingCollection=items;renderDesk();}).catch(()=>{readingCollectionLoaded=false;});}
 const subscriptions=readingSubscriptions(),runs=state.weekly.runs||[];
 const updateState=state.reading?.updates,updating=newsRefreshing||!!updateState?.current;
 const schedule=updateState?.schedule;
 const updateWarnings=newsWarnings.length||updateState?.last_run?.warnings?.length||updateState?.last_run?.read_warnings?.length||updateState?.last_run?.error;
 const savedIssues=(state.reading?.issues||[]).map(p=>({...p,updated:p.body.period_start||p.created,news:p.body.news,snapshot:true}));
 const weeklyIssues=savedIssues.filter(p=>p.body.period_start).sort((a,b)=>b.body.period_start.localeCompare(a.body.period_start));
 const issues=weeklyIssues.length?weeklyIssues:[...savedIssues,...pages().filter(p=>p.body.tags.includes('周刊'))].sort((a,b)=>new Date(b.updated)-new Date(a.updated));
 const latestIssue=weeklyIssues[0]||null;
 const issue=readingIssueId==='latest'?latestIssue:issues.find(p=>p.id===readingIssueId);
 const issueSources=issue?new Set((issue.body.citations||[]).map(c=>c.source_id)):null;
 const news=(issue?.snapshot?issue.news:(state.weekly.news||[])).filter(n=>(issue?.snapshot||!issueSources||issueSources.has(n.source_id))&&(readingCategory==='all'||topicFor(n)===readingCategory));
 if(favoriteCategory!=='all'&&!(state.reading?.groups||[]).includes(favoriteCategory))favoriteCategory='all';
 const favoriteIds=new Set([...(state.reading?.favorites||[]),...state.sources.filter(s=>state.asset_meta?.[s.id]?.favorite).map(s=>s.id),...readingCollection.map(i=>i.source_id)]);
 const ordered=state.reading?.favorites||[];const favorites=catalogItems().filter(a=>favoriteIds.has(a.id)).sort((a,b)=>{const index=id=>ordered.includes(id)?ordered.indexOf(id):9999;return index(a.id)-index(b.id);});
 const focus=[...defaultReadingFocus,...(state.reading?.focus||[])];
 $('#work-content').innerHTML=`<div class="reading-dashboard reading-sketch"><div class="reading-main-column"><section class="reading-block weekly-surface"><header class="weekly-heading"><div><h2>周刊</h2></div><div class="weekly-header-actions"><button data-reading-manage aria-label="来源管理" title="来源设置">来源管理</button><button class="weekly-update-button" data-update-current ${updating?'disabled':''}>${updating?'更新中…':'手动更新'}</button><button data-reading-schedule class="${schedule?.enabled?'schedule-enabled':''}" title="${schedule?.enabled?esc(scheduleLabel(schedule))+' · 北京时间':'设置更新时间'}">定时更新</button></div></header><nav class="weekly-issue-tabs"><button data-reading-issue="latest" class="${readingIssueId==='latest'?'active':''}">最新周刊<small>${issuePeriodLabel(latestIssue)}</small></button>${issues.filter(p=>p.id!==latestIssue?.id&&(!latestIssue?weekRange(new Date(p.updated))!==weekRange(new Date()):true)).slice(0,5).map((p,i)=>`<button data-reading-issue="${esc(p.id)}" class="${readingIssueId===p.id?'active':''}" title="${esc(p.title)}">第 ${issues.length-i-1} 期<small>${issuePeriodLabel(p)}</small></button>`).join('')}</nav><nav class="reading-topic-tabs">${readingTopics.map(t=>`<button data-reading-topic="${t==='全部'?'all':t}" class="${readingCategory===(t==='全部'?'all':t)?'active':''}">${t}</button>`).join('')}</nav><div class="selected-issue"><span>${issue?esc(issue.title):'按发布时间收录'} · ${news.length} 篇</span>${issue?`<button data-desk-issue="${esc(issue.id)}">本期目录 ↗</button>`:''}${updateWarnings?'<button class="reading-update-warning" data-reading-schedule>查看更新情况</button>':''}</div><div class="weekly-card-grid">${news.map(readingArticleCard).join('')||'<div class="reading-empty">暂无文章，更新来源后在这里阅读。</div>'}</div></section><section class="reading-block reading-favorites"><div class="reading-block-head"><h2>我的收藏</h2><details class="favorite-add-menu"><summary aria-label="添加收藏" title="添加到当前分类">＋</summary><div><button data-favorite-picker>从资产添加</button><button data-favorite-local>从本地添加</button><button data-capture-open>从网页采集</button></div></details></div><nav class="reading-topic-tabs"><button data-favorite-category="all" class="${favoriteCategory==='all'?'active':''}">全部</button>${(state.reading?.groups||[]).map(name=>`<button data-favorite-category="${esc(name)}" class="${favoriteCategory===name?'active':''}">${esc(name)}</button>`).join('')}<button data-favorite-group-manager aria-label="管理收藏分类" title="管理分类"><svg class="icon"><use href="#i-settings"/></svg></button></nav><div class="favorite-card-grid">${favorites.filter(a=>favoriteCategory==='all'||(state.reading?.favorite_categories?.[a.id]||'')===favoriteCategory).map(readingFavoriteCard).join('')||'<div class="reading-empty">把想反复阅读的资产放在这里。</div>'}</div></section></div><aside class="reading-block reading-focus-panel"><div class="reading-block-head"><h2>重点关注</h2><button data-focus-manager aria-label="管理重点关注" title="管理重点关注">＋</button></div><div class="focus-source-types"><span>官网</span><span>公众号</span><span>小红书账号</span></div><div class="focus-card-list">${focus.map(readingFocusCard).join('')}</div><div class="focus-manual-note">公众号、小红书需要登录时，打开浏览器完成后采集。</div><div class="reading-capture-entry"><button data-capture-open>采集文章 ↗</button></div></aside></div>`;
}

function renderUsage(){
 const u=usageSnapshot,known=u&&u.input_tokens!==null&&u.output_tokens!==null;
 const fmt=value=>value===null||value===undefined?'—':Number(value).toLocaleString('zh-CN');
 const balance=balanceSnapshot?.balance_infos||[];
 $('#settings-usage').innerHTML=`<div class="desk-section-head"><div><h2>DeepSeek 用量</h2><p>最近 7 天 · 本机积木的调用，不是整个账户的历史账单。</p></div><button class="secondary" data-usage-refresh ${usageLoading?'disabled':''}>${usageLoading?'读取中…':'刷新记录'}</button></div><div class="usage-stats"><div><span>API 调用</span><strong>${fmt(u?.calls)}</strong><small>包含模型、搜索与抓取</small></div><div><span>输入 Token</span><strong>${known?fmt(u.input_tokens):'—'}</strong><small>以服务商返回为准</small></div><div><span>输出 Token</span><strong>${known?fmt(u.output_tokens):'—'}</strong><small>不估算未返回的用量</small></div><div><span>失败调用</span><strong>${fmt(u?.failed)}</strong><small>失败不等于未计费</small></div></div>${usageError?`<p class="error">${esc(usageError)}</p>`:''}<div class="usage-columns"><section class="usage-history"><h3>每日调用</h3><div class="usage-bars">${(u?.days||[]).map(d=>`<div><span>${d.calls}</span><div class="usage-bar-track"><i style="height:${d.calls?Math.max(4,Math.round(d.calls/Math.max(1,...u.days.map(v=>v.calls))*92)):2}px"></i></div><small>${d.date.slice(5)}</small></div>`).join('')}</div><p class="desk-muted">${u?.since?'记录自 '+localDate(u.since)+' 起，之前的调用不补算。':'开始记录后，真实调用会出现在这里。'} ${u?.missing_usage_calls?'有 '+u.missing_usage_calls+' 次模型调用没有完整 Token 返回。':''}</p></section><section class="balance-section"><h3>账户余额</h3>${balance.length?balance.map(b=>`<div class="balance-value"><strong>${b.currency==='CNY'?'¥':'$'} ${esc(b.total_balance)}</strong><span>${b.currency}</span></div>`).join(''):'<div class="balance-placeholder">尚未查询</div>'}<p>余额来自 DeepSeek 官方接口。不会读取其他应用的历史账单。</p><button class="secondary" data-balance-refresh ${balanceLoading?'disabled':''}>${balanceLoading?'查询中…':balance.length?'刷新余额':'查询余额'}</button>${balanceSnapshot?`<small>查询于 ${localDate(balanceSnapshot.checked_at)}</small>`:''}${balanceError?`<p class="error">${esc(balanceError)}</p>`:''}</section></div>${u?.recent.length?`<section class="usage-requests"><h3>最近调用</h3>${u.recent.map(r=>`<div><span>${localDate(r.created)}</span><span>${{chat:'模型',search:'搜索',fetch:'抓取'}[r.operation]} ${esc(r.model)}</span><span>${{ok:'完成',failed:'失败',running:'执行中',incomplete:'未完整返回'}[r.status]||r.status}</span><span>${r.input_tokens===null||r.output_tokens===null?'—':fmt(r.input_tokens+r.output_tokens)+' Token'}</span></div>`).join('')}</section>`:''}`;
}
async function refreshUsage(){if(usageLoading)return;usageLoading=true;usageError='';renderUsage();try{usageSnapshot=await api('/api/usage');}catch(e){usageError=e.message;}finally{usageLoading=false;deskSignature='';renderUsage();}}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;const d=b.dataset;
 try{
  if(d.workTab){workTab=d.workTab;deskSignature='';renderDesk();if(workTab==='usage'&&!usageSnapshot)refreshUsage();}
  if(d.view==='work'&&workTab==='usage'&&!usageSnapshot)refreshUsage();
  if(d.deskIssue){const archived=(state.reading?.issues||[]).find(p=>p.id===d.deskIssue);if(archived){openReadingSnapshot(archived.title,archived.body.news.map(n=>'## '+n.title+'\n\n'+n.excerpt+'\n\n[原文]('+n.url+')').join('\n\n'));return;}await openDocument(d.deskIssue);}
  if(d.backReading!==undefined){workTab='reading';deskSignature='';await switchView('work');}
  if(d.readingFilter){readingFilter=d.readingFilter;deskSignature='';renderDesk();}

  if(d.newsRefresh){await refreshNews(d.newsRefresh);}
 if(d.newsGenerate){await generateNews(d.newsGenerate);}
 if(d.newsOpen)await openNewsPreview(d.newsOpen);
 if(d.subscriptionRemove){const c=readingSubscriptions().find(c=>c.id===d.subscriptionRemove);if(!c)return;if(!await confirm('移除「'+c.title+'」？','停止这个订阅的后续更新。已保存的阅读内容、原文和更新记录仍保留在「全部更新」中。'))return;await api('/api/weekly/remove',{id:c.id,revision:c.revision});await load();toast('订阅已移除，已有内容保留');}
  if(d.usageRefresh!==undefined)await refreshUsage();
  if(d.balanceRefresh!==undefined){if(!await confirm('查询 DeepSeek 账户余额？','仅使用本机已配置的 API Key，发送给官方 api.deepseek.com/user/balance。不会发送文档或对话，不生成模型内容。'))return;balanceLoading=true;balanceError='';renderUsage();try{balanceSnapshot=await api('/api/model/balance',{allow_remote:true});}catch(error){balanceError=error.message;}finally{balanceLoading=false;deskSignature='';renderUsage();}}
 }catch(error){toast(error.message);}
});

function newsSource(n){if(n.source_name)return n.source_name;const u=new URL(n.feed_url||n.url);return u.hostname==='github.com'?u.pathname.split('/').slice(1,3).join('/')+' · GitHub':u.hostname;}
function newsSection(subscriptions){
 const list=(state.weekly.news||[]).filter(n=>readingFilter==='all'||n.subscription_id===readingFilter);
 const selected=(state.weekly.news||[]).filter(n=>newsSelection.has(n.id)),subscription=selected[0]?.subscription_id;
 return `<section class="learning-news"><div class="desk-section-head"><div><h2>最新资讯 <span class="subscription-count">${list.length}</span></h2><p>公开RSS / Atom · 保留原始标题与摘要，非AI编写的新闻</p></div><button class="secondary" data-news-generate="${esc(subscription||'')}" ${!selected.length||newsGenerating?'disabled':''}>${newsGenerating?'提交中…':'整理学习周刊'}${selected.length?' · '+selected.length:''}</button></div>${newsWarnings.length?`<details class="news-warnings" open><summary>部分来源未完成</summary>${newsWarnings.map(w=>`<p>${esc(w.url)}：${esc(w.error)}</p>`).join('')}</details>`:''}${list.length?`<div class="news-list">${list.map(n=>`<article class="news-row"><label class="news-check"><input type="checkbox" data-news-select="${esc(n.id)}" ${newsSelection.has(n.id)?'checked':''} aria-label="选择${esc(n.title)}"></label><div class="news-body"><div class="news-meta"><span>${esc(newsSource(n))}</span><time>${n.published_at?'发布 '+localDate(n.published_at):'发布日期未提供'}</time><span>采集 ${localDate(n.fetched_at)}</span></div><button class="news-title" data-news-open="${esc(n.id)}">${esc(n.title)}</button><p>${esc(n.excerpt.slice(0,230))}${n.excerpt.length>230?'…':''}</p><div class="news-actions"><button class="text-button" data-news-open="${esc(n.id)}">阅读摘要与做笔记</button><a class="text-button" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">原文 ↗</a></div></div></article>`).join('')}</div>`:'<div class="reading-content-empty"><h3>从关注的来源开始</h3><p>点击订阅的「刷新资讯」，读取公开更新。抓取不会消耗模型Token；整理周刊时才调用DeepSeek。</p></div>'}</section>`;
}
async function refreshNews(id){
 if(newsRefreshing)return;
 newsRefreshing=true;deskSignature='';renderDesk();
 try{const r=await api('/api/news/refresh',{id,allow_remote:true});newsWarnings=r.warnings;await load();toast(r.added?'已采集 '+r.added+' 条新资讯':'刷新完成，没有新增条目');}
 catch(e){toast(e.message);}finally{newsRefreshing=false;deskSignature='';renderDesk();}
}
async function generateNews(id){
 if(newsGenerating)return;
 if(!await confirm('用DeepSeek整理学习周刊？','仅发送勾选的最多5篇公开摘要。使用阅读周报技能完成提取、整理、核对；生成的是待审核草稿，不会自动保存。'))return;
 newsGenerating=true;deskSignature='';renderDesk();
 try{await api('/api/news/generate',{id,news_ids:[...newsSelection],allow_remote:true});newsSelection.clear();await load();weeklyPoll();toast('已开始整理，完成后可审核草稿');}
 catch(e){toast(e.message);}finally{newsGenerating=false;deskSignature='';renderDesk();}
}
document.addEventListener('change',e=>{const id=e.target.dataset.newsSelect;if(!id)return;const n=(state.weekly.news||[]).find(n=>n.id===id);if(e.target.checked){const first=(state.weekly.news||[]).find(n=>newsSelection.has(n.id));if(newsSelection.size>=5||first&&first.subscription_id!==n.subscription_id){e.target.checked=false;toast('每次选择同一订阅的1至5篇资讯');return;}newsSelection.add(id);}else newsSelection.delete(id);deskSignature='';renderDesk();});

function weeklyDraftCard(r){const j=state.jobs?.find(j=>j.id===r.job_id),p=j?.payload.proposal?.page;return `<article class="weekly-draft-card"><div><span class="eyebrow">DeepSeek整理 · 待审核</span><h3>${esc(p?.title||r.config?.title||'学习周刊')}</h3><p>${esc(p?.summary||'草稿已完成，请检查来源、结论和学习建议。')}</p>${p?`<details><summary>预览本期内容</summary><div class="markdown">${md(p.content)}</div></details>`:''}</div><button class="secondary" data-conversation="${esc(r.conversation_id)}">审核草稿</button></article>`;}

document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;if(d.readingTopic){readingCategory=d.readingTopic;renderDesk();}if(d.readingAdd){$('#reading-section').value=d.readingAdd;$('#reading-source-options').innerHTML=state.sources.map(s=>`<button class="reading-pick-row" data-reading-save="${esc(s.id)}">${esc(s.title)}</button>`).join('')||'<p class="empty">先导入一篇文章</p>';$('#reading-add-error').textContent='';$('#reading-add').showModal();}if(d.readingSave){try{await api('/api/reading/items',{source_id:d.readingSave,section:$('#reading-section').value});readingCollection=await api('/api/reading/items');$('#reading-add').close();renderDesk();}catch(err){$('#reading-add-error').textContent=err.message;}}});
$('#reading-import').onclick=()=>{$('#reading-add').close();sourceDialog('url');};

document.addEventListener('click',e=>{const b=e.target.closest('[data-reading-issue]');if(!b)return;readingIssueId=b.dataset.readingIssue;renderDesk();});

let sourceTestResults=[],sourceTesting=false;
function sourceManager(){
 let dialog=$('#reading-source-manager');if(!dialog){dialog=document.createElement('dialog');dialog.id='reading-source-manager';document.body.append(dialog);}
 const configs=readingSubscriptions();
 dialog.innerHTML=`<header><h2>来源管理</h2><button data-source-manager-close aria-label="关闭来源管理">×</button></header><div class="source-manager-toolbar"><button data-source-row-add>＋ 添加条目</button><button data-test-all-sources class="secondary" ${sourceTesting?'disabled':''}>${sourceTesting?'测试中…':'一键测试全部'}</button></div><div class="source-manager-columns"><span>标题</span><span>地址</span><span>操作</span><span>状态</span></div><div class="source-manager-list">${configs.map(c=>c.urls.map((url,i)=>`<div class="source-edit-row" data-subscription="${esc(c.id)}" data-url-index="${i}"><input class="source-row-title" value="${esc(c.source_titles?.[url]||new URL(url).hostname)}" aria-label="来源标题"><input class="source-row-url" value="${esc(url)}" aria-label="来源地址"><div><button data-source-row-save>保存</button><button data-source-row-test>测试</button><button data-source-row-delete>删除</button></div><small>${esc(sourceTestResults.find(r=>r.url===url)?.error|| (sourceTestResults.find(r=>r.url===url)?.ok?'可读取':'未测试'))}</small></div>`).join('')).join('')}</div>`;
 if(!dialog.open)dialog.showModal();
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.hasAttribute('data-reading-manage'))sourceManager();
 if(b.hasAttribute('data-source-manager-close'))$('#reading-source-manager').close();
 if(b.hasAttribute('data-weekly-settings')||b.hasAttribute('data-weekly-new'))$('#reading-source-manager')?.close();
 if(b.hasAttribute('data-test-all-sources')){if(sourceTesting)return;sourceTesting=true;sourceManager();try{const r=await api('/api/news/test',{allow_remote:true});sourceTestResults=r.results;}catch(err){toast(err.message);}finally{sourceTesting=false;sourceManager();}}
});

function openReadingSnapshot(title,content){let d=$('#reading-snapshot');if(!d){d=document.createElement('dialog');d.id='reading-snapshot';document.body.append(d);}d.innerHTML=`<header><strong>${esc(title)}</strong><button aria-label="关闭历史周刊">×</button></header><small>保存的来源摘要 · 非全文</small><div class="markdown">${md(content)}</div>`;d.querySelector('button').onclick=()=>d.close();d.showModal();}
async function updateCurrentReading(){
 if(newsRefreshing||state.reading?.updates?.current)return;
 if(!readingSubscriptions().some(c=>c.urls.length)){sourceManager();return;}
 newsRefreshing=true;newsWarnings=[];renderDesk();
 try{
  const run=await api('/api/reading/update',{allow_remote:true});
  state.reading.updates={...state.reading.updates,current:run,last_run:run};
  readingIssueId='latest';watchReadingUpdates();
 }catch(error){toast(error.message);}finally{newsRefreshing=false;renderDesk();}
}
document.addEventListener('click',e=>{if(e.target.closest('[data-update-current]'))updateCurrentReading();});

function watchReadingUpdates(){
 if(readingUpdateTimer!==null||readingUpdatePolling)return;
 const updates=state.reading?.updates;
 if(!updates?.current&&!updates?.schedule?.enabled)return;
 readingUpdateTimer=setTimeout(pollReadingUpdates,updates.current?1800:15000);
}
async function pollReadingUpdates(){
 readingUpdateTimer=null;readingUpdatePolling=true;
 const before=state.reading?.updates;
 try{
  const next=await api('/api/reading/updates');
  const changed=JSON.stringify(before)!==JSON.stringify(next);
  state.reading.updates=next;
  if(changed){
   const run=next.last_run;
   if(run&&!next.current){
    newsWarnings=run.warnings||[];await load();
    toast(run.error|| (run.status==='partial'?'已更新 · 部分来源或正文暂不可用':'已更新 · 新增 '+run.added+' 条'));
   }else renderDesk();
   if($('#reading-schedule-dialog')?.open)renderReadingUpdateStatus();
  }
 }catch(error){state.reading.updates=before;if(view==='work')toast('更新状态暂不可用，稍后重试');}
 finally{readingUpdatePolling=false;watchReadingUpdates();}
}
function readingScheduleTime(value){
 return value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'';
}
function readingScheduleDefaults(){return {enabled:false,frequency:'weekly',weekday:0,time:'09:00',revision:0};}
function syncReadingScheduleForm(){
 const enabled=$('#reading-auto-enabled').checked,weekly=$('#reading-auto-frequency').value==='weekly';
 $('#reading-auto-fields').disabled=!enabled;
 $('#reading-auto-weekday').disabled=!enabled||!weekly;
 $('#reading-auto-weekday-field').classList.toggle('schedule-field-inactive',!weekly);
}
function renderReadingUpdateStatus(){
 const updates=state.reading?.updates,config=updates?.schedule,run=updates?.last_run;
 const statuses={running:'更新中',completed:'更新完成',partial:'部分更新',failed:'更新失败',interrupted:'更新中断'};
 const next=config?.enabled?'下次更新：'+readingScheduleTime(config.next_run):'定时更新未开启';
 const last=run?`${statuses[run.status]||run.status} · ${readingScheduleTime(run.finished||run.started)}${run.status==='completed'?' · 新增 '+run.added+' 条':''}`:'暂无更新记录';
 const warnings=[...(run?.warnings||[]),...(run?.read_warnings||[])];
 $('#reading-auto-status').innerHTML=`<p>${esc(next)}</p><p>${esc(last)}</p>${run?.error?`<p class="error">${esc(run.error)}</p>`:''}${warnings.length?`<details><summary>查看 ${warnings.length} 条采集说明</summary>${warnings.map(w=>`<p>${esc(w.url||findReadingNews(w.id)?.title||'正文读取')}：${esc(w.error)}</p>`).join('')}</details>`:''}`;
}
async function readingScheduleDialog(){
 try{state.reading.updates=await api('/api/reading/updates');}
 catch(error){toast('暂时无法读取定时设置，请重试');return;}
 let d=$('#reading-schedule-dialog');if(!d){d=document.createElement('dialog');d.id='reading-schedule-dialog';document.body.append(d);}
 const c=state.reading?.updates?.schedule||readingScheduleDefaults();
 d.setAttribute('aria-labelledby','reading-auto-title');
 d.innerHTML=`<form id="reading-auto-form"><header><h2 id="reading-auto-title">定时更新</h2><button type="button" data-reading-schedule-close aria-label="关闭定时更新">×</button></header><div class="reading-auto-body"><label class="reading-auto-toggle"><span>自动更新周刊</span><input id="reading-auto-enabled" type="checkbox" role="switch" ${c.enabled?'checked':''}><span class="reading-auto-switch" aria-hidden="true"></span></label><fieldset id="reading-auto-fields"><div class="reading-auto-fields"><label>更新频率<select id="reading-auto-frequency"><option value="daily" ${c.frequency==='daily'?'selected':''}>每天</option><option value="weekly" ${c.frequency==='weekly'?'selected':''}>每周</option></select></label><label id="reading-auto-weekday-field">星期<select id="reading-auto-weekday">${['周一','周二','周三','周四','周五','周六','周日'].map((name,i)=>`<option value="${i}" ${c.weekday===i?'selected':''}>${name}</option>`).join('')}</select></label><label>时间<input id="reading-auto-time" type="time" value="${esc(c.time)}" required></label></div></fieldset><p class="reading-auto-hint">北京时间 · 需电脑与积木服务保持运行。<br>按来源管理抓取公开更新，不调用付费模型。</p><div id="reading-auto-status" aria-live="polite"></div><p id="reading-auto-error" class="error" role="alert"></p></div><footer><button type="button" class="secondary" data-reading-schedule-close>取消</button><button class="primary" id="reading-auto-save">保存</button></footer></form>`;
 d.querySelectorAll('[data-reading-schedule-close]').forEach(b=>b.onclick=()=>d.close());
 $('#reading-auto-enabled').onchange=syncReadingScheduleForm;
 $('#reading-auto-frequency').onchange=syncReadingScheduleForm;
 syncReadingScheduleForm();renderReadingUpdateStatus();
 d.querySelector('form').onsubmit=async e=>{
  e.preventDefault();const save=$('#reading-auto-save');save.disabled=true;$('#reading-auto-error').textContent='';
  const data={enabled:$('#reading-auto-enabled').checked,frequency:$('#reading-auto-frequency').value,weekday:Number($('#reading-auto-weekday').value),time:$('#reading-auto-time').value,revision:c.revision};
  try{
   const schedule=await api('/api/reading/schedule',data);
   state.reading.updates={...state.reading.updates,schedule};
   d.close();renderDesk();watchReadingUpdates();toast(schedule.enabled?'已开启 · '+scheduleLabel(schedule):'已保存 · 定时更新关闭');
  }catch(error){$('#reading-auto-error').textContent=error.message;}
  finally{save.disabled=false;}
 };
 if(!d.open)d.showModal();
}
document.addEventListener('click',e=>{if(e.target.closest('[data-reading-schedule]'))readingScheduleDialog();});

function favoritePicker(){let d=$('#favorite-picker');if(!d){d=document.createElement('dialog');d.id='favorite-picker';document.body.append(d);}d.innerHTML=`<header><h2>从资产添加收藏</h2><button data-favorite-close>×</button></header><div class="favorite-picker-list">${catalogItems().map(a=>`<button data-favorite-add="${esc(a.id)}">${assetIcon(assetExtension(a))}<span>${esc(a.title)}</span><small>${(state.reading?.favorites||[]).includes(a.id)?'已收藏':'＋'}</small></button>`).join('')||'<p class="empty">先上传文件或保存文稿</p>'}</div>`;if(!d.open)d.showModal();}
function focusManager(id){
 let d=$('#focus-manager');if(!d){d=document.createElement('dialog');d.id='focus-manager';document.body.append(d);}
 const focus=(state.reading?.focus||[]).find(f=>f.id===id);
 d.setAttribute('aria-labelledby','focus-manager-title');
 d.innerHTML=`<header><h2 id="focus-manager-title">重点关注</h2><button data-focus-close aria-label="关闭重点关注管理">×</button></header><div class="focus-manager-body"><form id="focus-form"><div class="focus-form-identity"><label for="focus-name">名称<input id="focus-name" placeholder="网站或账号名称" maxlength="60" value="${esc(focus?.name||'')}" required></label><label for="focus-kind">来源<select id="focus-kind">${['官网','公众号','小红书账号'].map(kind=>`<option ${kind===focus?.kind?'selected':''}>${kind}</option>`).join('')}</select></label></div><label for="focus-url">地址<input id="focus-url" type="url" placeholder="https://…" value="${esc(focus?.url||'')}" required></label><label for="focus-description">简介 <span>可选</span><input id="focus-description" placeholder="一句话介绍这个来源，或写下你关注的内容" maxlength="160" value="${esc(focus?.description||'')}"></label><div class="focus-form-actions"><p id="focus-error" class="error" role="status"></p>${focus?'<button type="button" data-focus-cancel>取消</button>':''}<button type="submit" class="primary">${focus?'保存':'添加关注'}</button></div></form><div class="focus-manager-list">${(state.reading?.focus||[]).map(f=>`<div class="focus-manager-row">${focusLogo(f)}<a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer"><strong>${esc(f.name)}</strong><span>${esc(f.description||f.kind)}</span></a><button data-focus-edit="${esc(f.id)}" aria-label="编辑${esc(f.name)}">编辑</button><button data-focus-remove="${esc(f.id)}" aria-label="移除${esc(f.name)}">移除</button></div>`).join('')}</div></div>`;
 const form=d.querySelector('form');
 form.onsubmit=async e=>{
  e.preventDefault();const button=form.querySelector('[type="submit"]');if(button.disabled)return;
  const data={...(focus?{id:focus.id}:{}),name:$('#focus-name').value,kind:$('#focus-kind').value,url:$('#focus-url').value,description:$('#focus-description').value};
  const controls=[...d.querySelectorAll('.focus-manager-body button,.focus-manager-body input,.focus-manager-body select')];controls.forEach(control=>control.disabled=true);
  try{await api('/api/reading/focus',data);await load();if(d.open)focusManager();renderDesk();}
  catch(err){$('#focus-error').textContent=err.message;controls.forEach(control=>control.disabled=false);}
 };
 if(!d.open)d.showModal();
 if(focus)$('#focus-description').focus();
}
document.addEventListener('click',e=>{const b=e.target.closest('button');if(b?.dataset.focusEdit)focusManager(b.dataset.focusEdit);if(b?.hasAttribute('data-focus-cancel'))focusManager();});
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.hasAttribute('data-favorite-picker'))favoritePicker();if(b.hasAttribute('data-favorite-close'))$('#favorite-picker').close();if(b.dataset.favoriteAdd){await api('/api/reading/favorite',{id:b.dataset.favoriteAdd,category:favoriteCategory});await load();favoritePicker();renderDesk();}if(b.dataset.favoriteRemove){await api('/api/reading/favorite',{id:b.dataset.favoriteRemove,remove:true});const old=readingCollection.find(i=>i.source_id===b.dataset.favoriteRemove);if(old){await api('/api/reading/items/remove',{source_id:b.dataset.favoriteRemove});readingCollection=readingCollection.filter(i=>i!==old);}if(state.asset_meta?.[b.dataset.favoriteRemove]?.favorite)await api('/api/assets/meta',{id:b.dataset.favoriteRemove,category:state.asset_meta[b.dataset.favoriteRemove].category,favorite:false});await load();renderDesk();}if(b.dataset.favoriteOpen){const a=catalogItems().find(a=>a.id===b.dataset.favoriteOpen);libraryCategory=a.category_id||'all';libraryOrigin=state.categories.find(c=>c.id===a.category_id)?.scope||(a.origin==='ai'?'creations':'materials');await switchView('sources');await selectAssetFile(a.id);}if(b.hasAttribute('data-focus-manager'))focusManager();if(b.hasAttribute('data-focus-close'))$('#focus-manager').close();if(b.dataset.focusRemove){await api('/api/reading/focus/remove',{id:b.dataset.focusRemove});await load();focusManager();renderDesk();}}catch(err){toast(err.message);}});

let favoriteCategory='all',collectionMode='收藏';
function weekRange(date){const start=new Date(date);start.setDate(start.getDate()-((start.getDay()+6)%7));const end=new Date(start);end.setDate(end.getDate()+6);const fmt=d=>`${d.getMonth()+1}/${d.getDate()}`;return fmt(start)+' — '+fmt(end);}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.favoriteCategory){favoriteCategory=b.dataset.favoriteCategory;renderDesk();}if(b.dataset.collectionMode){collectionMode=b.dataset.collectionMode;renderDesk();}if(b.hasAttribute('data-source-row-add')){const c=readingSubscriptions()[0];if(!c){await api('/api/weekly/config',{new:true,title:'我的来源',urls:[],enabled:false});await load();}const dialog=$('#reading-source-manager');const row=document.createElement('div');row.className='source-edit-row';row.dataset.subscription=readingSubscriptions()[0].id;row.dataset.urlIndex='-1';row.innerHTML='<input class="source-row-title" placeholder="标题" aria-label="来源标题"><input class="source-row-url" placeholder="https://…" aria-label="来源地址"><div><button data-source-row-save>保存</button><button data-source-row-test>测试</button><button data-source-row-delete>删除</button></div><small></small>';dialog.querySelector('.source-manager-list').append(row);}const row=b.closest('.source-edit-row');if(row){const c=readingSubscriptions().find(c=>c.id===row.dataset.subscription),index=Number(row.dataset.urlIndex),url=row.querySelector('.source-row-url').value;if(b.hasAttribute('data-source-row-test')){row.querySelector('small').textContent='测试中…';const r=await api('/api/news/test-url',{url});row.querySelector('small').textContent=r.ok?'可读取 · '+r.count+' 条':r.error;}if(b.hasAttribute('data-source-row-save')||b.hasAttribute('data-source-row-delete')){const urls=[...c.urls];if(index<0){if(b.hasAttribute('data-source-row-delete')){row.remove();return;}urls.push(url);}else if(b.hasAttribute('data-source-row-delete'))urls.splice(index,1);else urls[index]=url;await api('/api/weekly/config',{...c,source_titles:{...c.source_titles,[url]:row.querySelector('.source-row-title').value},urls,enabled:false});await load();sourceManager();}}if(b.hasAttribute('data-favorite-local')){let input=$('#favorite-file-input');if(!input){input=document.createElement('input');input.type='file';input.id='favorite-file-input';input.hidden=true;document.body.append(input);input.onchange=async()=>{try{const file=input.files[0];if(!file)return;if(file.size>67108864)throw Error('文件最多64MB');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));const r=await api('/api/assets/import',{name:file.name,base64:btoa(binary),category:'reference'});await api('/api/reading/favorite',{id:r.source?.id||r.artifact.id,category:favoriteCategory});await load();renderDesk();}catch(err){toast(err.message);}finally{input.value='';}};}input.click();}}catch(err){toast(err.message);}});

let favoriteDragId=null;
document.addEventListener('dragstart',e=>{const card=e.target.closest('[data-favorite-drag]');if(!card)return;favoriteDragId=card.dataset.favoriteDrag;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('application/x-jimu-favorite',favoriteDragId);});
document.addEventListener('dragover',e=>{const card=e.target.closest('[data-favorite-drag]');if(!card||!favoriteDragId)return;e.preventDefault();e.dataTransfer.dropEffect='move';card.classList.add('favorite-drop-target');});
document.addEventListener('dragleave',e=>e.target.closest('[data-favorite-drag]')?.classList.remove('favorite-drop-target'));
document.addEventListener('drop',async e=>{const card=e.target.closest('[data-favorite-drag]'),id=favoriteDragId;favoriteDragId=null;if(!card||!id)return;e.preventDefault();document.querySelectorAll('.favorite-drop-target').forEach(c=>c.classList.remove('favorite-drop-target'));const target=card.dataset.favoriteDrag;if(id===target)return;try{const visible=[...document.querySelectorAll('[data-favorite-drag]')].map(c=>c.dataset.favoriteDrag);for(const ident of visible)if(!(state.reading?.favorites||[]).includes(ident))await api('/api/reading/favorite',{id:ident,category:favoriteCategory});const order=visible.filter(i=>i!==id),index=order.indexOf(target);order.splice(index,0,id);await api('/api/reading/favorite/order',{ids:order});await load();renderDesk();}catch(err){toast(err.message);}});
document.addEventListener('dragend',()=>{favoriteDragId=null;document.querySelectorAll('.favorite-drop-target').forEach(c=>c.classList.remove('favorite-drop-target'));});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-collect-news]');if(!b||b.disabled)return;try{const n=findReadingNews(b.dataset.collectNews);if(!n)return;b.disabled=true;await api('/api/reading/favorite',{id:n.source_id,category:favoriteCategory});await load();renderDesk();if($('#news-preview')?.open&&activeNewsId===n.id){const saved=$('#news-preview [data-collect-news]');if(saved){saved.disabled=true;saved.textContent='已收藏';}}toast('已收藏网页资料');}catch(err){b.disabled=false;toast(err.message);}});

function favoriteGroupManager(){let dialog=$('#favorite-group-manager');if(!dialog){dialog=document.createElement('dialog');dialog.id='favorite-group-manager';document.body.append(dialog);}dialog.innerHTML=`<header><h2>管理分类</h2><button data-close-favorite-groups aria-label="关闭分类管理">×</button></header><form id="favorite-group-form"><input id="favorite-group-name" maxlength="40" placeholder="新分类名称" required><button class="secondary">新增</button></form><div>${(state.reading?.groups||[]).map(name=>`<div class="favorite-group-row"><span>${esc(name)}</span><button data-delete-favorite-group="${esc(name)}">删除</button></div>`).join('')}</div><p id="favorite-group-error" class="error"></p>`;dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();try{await api('/api/reading/groups',{name:$('#favorite-group-name').value});await load();renderDesk();favoriteGroupManager();}catch(err){$('#favorite-group-error').textContent=err.message;}};if(!dialog.open)dialog.showModal();}
document.addEventListener('click',async e=>{const button=e.target.closest('button');if(!button)return;if(button.hasAttribute('data-favorite-group-manager'))favoriteGroupManager();if(button.hasAttribute('data-close-favorite-groups'))$('#favorite-group-manager').close();if(button.dataset.deleteFavoriteGroup){const name=button.dataset.deleteFavoriteGroup;if(!await confirm('删除「'+name+'」分类？','收藏内容不删除，仍保留在全部中。'))return;try{await api('/api/reading/groups',{name,remove:true});await load();renderDesk();favoriteGroupManager();}catch(err){$('#favorite-group-error').textContent=err.message;}}button.closest('.favorite-add-menu')?.removeAttribute('open');});
