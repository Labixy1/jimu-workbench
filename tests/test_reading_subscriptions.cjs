'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),nodes=new Map();
function node(selector){if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:''});return nodes.get(selector);}
const subscriptions=[1,2,3].map(n=>({id:'sub_'+n,title:'主题'+n,urls:['https://example.com/'+n],enabled:false,revision:1}));
const news=[
 {id:'one',title:'Agent research',excerpt:'Tool execution and evidence',feed_url:'https://openai.com/news/rss.xml',url:'https://openai.com/news/one',published_at:'2026-10-19T10:00:00Z'},
 {id:'two',title:'Product design',excerpt:'产品与设计实践',feed_url:'https://example.com/rss',url:'https://example.com/two',published_at:'2026-10-19T09:00:00Z'}
];
const state={conversations:[],sources:[],categories:[],asset_meta:{},weekly:{subscriptions,news,runs:[]},reading:{favorites:[],groups:['Harness'],issues:[],focus:[]}};
const ctx=vm.createContext({URL,URLSearchParams,location:{search:''},document:{addEventListener(){},querySelectorAll(){return[]}},$:node,esc:String,view:'work',pages:()=>[],catalogItems:()=>[],api:async()=>[],state});
vm.runInContext(fs.readFileSync(path.join(root,'web/desk.js'),'utf8'),ctx);
vm.runInContext('readingCollectionLoaded=true',ctx);
ctx.renderDesk();
const output=()=>node('#work-content').innerHTML;
assert.equal((output().match(/class="weekly-article-card"/g)||[]).length,2);
assert(output().includes('data-update-current'));
assert(output().includes('data-reading-manage'));
assert(!output().includes('待审核'));
assert(!output().includes('sample-week-'));
assert(!output().includes('reading-subscription-card'));
ctx.location.search='?readingPreview=1';ctx.renderDesk();
assert(!output().includes('sample-week-'),'old preview URLs cannot reintroduce fictional issues');
assert(!fs.readFileSync(path.join(root,'web/desk.js'),'utf8').includes('readingSampleIssues'));
ctx.location.search='';
vm.runInContext("readingCategory='产品与设计'",ctx);ctx.renderDesk();
assert(!output().includes('class="news-title" data-news-open="one"'));
assert(output().includes('class="news-title" data-news-open="two"'));
vm.runInContext("readingCategory='电商经营'",ctx);ctx.renderDesk();
assert(output().includes('暂无文章'));
assert(output().includes('weekly-surface'));
state.weekly.news=[];state.reading.issues=[{id:'old-issue',title:'真实留存的上期',created:'2026-10-01T12:00:00Z',body:{news:[news[0]]}}];
vm.runInContext("readingCategory='all';readingIssueId='old-issue'",ctx);ctx.renderDesk();
assert(output().includes('真实留存的上期'));
assert(output().includes('class="news-title" data-news-open="one"'));
assert(!output().includes('class="news-title" data-news-open="two"'));
subscriptions[0].title='改名后的来源';ctx.renderDesk();
assert(output().includes('真实留存的上期'),'snapshots survive source renaming');
const css=fs.readFileSync(path.join(root,'web/desktop.css'),'utf8');
assert(css.includes('height: var(--reading-room-height);'));
assert(css.includes('grid-template-rows: minmax(490px, 1.6fr) minmax(300px, 1fr);'));
assert(css.includes('max-height: 100% !important;'));
console.log('PASS manual reading updates, independent category filters, no fake history and fixed empty panels');
