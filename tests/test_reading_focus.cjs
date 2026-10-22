'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),nodes=new Map(),events=[];
function node(selector){if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:''});return nodes.get(selector);}
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={sources:[],weekly:{news:[]},reading:{focus:[]}};
const ctx=vm.createContext({URL,document:{addEventListener:(...event)=>events.push(event)},$:node,esc,state,scoped:path=>path});
vm.runInContext(fs.readFileSync(path.join(root,'web/desk.js'),'utf8'),ctx);
const defaults=vm.runInContext('defaultReadingFocus',ctx);
for(const source of defaults){
 const html=ctx.readingFocusCard(source);
 assert(html.includes('class="focus-identity"'));
 assert(html.includes('class="focus-description"'));
 assert(html.includes(esc(source.description)));
 assert(html.includes(source.logo));
 assert(fs.existsSync(path.join(root,'web',source.logo)));
 assert(html.includes('暂无已采集动态'));
}
const account={id:'focus-fixture',name:'测试账号',kind:'公众号',url:'https://example.com/account',description:'关注 <Agent> & "产品"'};
state.weekly.news=[
 {id:'old',title:'Old fixture',author_url:account.url,published_at:'2026-10-01'},
 {id:'other',title:'Unrelated account',author_url:'https://example.com/other',published_at:'2026-10-22'},
 {id:'latest',title:'<New fixture>',source_name:account.name,published_at:'2026-10-21'},
];
let html=ctx.readingFocusCard(account);
assert(html.includes('关注 &lt;Agent&gt; &amp; &quot;产品&quot;'));
assert(html.indexOf('data-news-open="latest"')<html.indexOf('data-news-open="old"'));
assert(!html.includes('data-news-open="other"'));
assert(!html.includes('/api/site-icon'),'do not use a platform icon as an account avatar');
assert(html.includes('<span>测试</span>'));
assert(html.includes('&lt;New fixture&gt;'));
state.weekly.news=[];
state.sources=[{id:'unrelated',url:'https://example.com/someone-else',title:'Another account'}];
assert(!ctx.readingFocusCard(account).includes('data-source="unrelated"'));
assert(ctx.readingFocusCard({...account,kind:'官网'}).includes('/api/site-icon?id=focus-fixture'));
ctx.scoped=path=>path+'&space=demo';
assert(ctx.readingFocusCard({...account,kind:'官网'}).includes('id=focus-fixture&amp;space=demo'));
assert(!ctx.focusMatches(defaults[0],{url:'https://deepseek.com.attacker.example/story'}));
assert(ctx.focusMatches(defaults[0],{url:'https://api-docs.deepseek.com/updates'}));
let loaded=false,removed=false;
const image={matches:selector=>selector==='[data-focus-logo]',parentElement:{classList:{add:name=>{loaded=name==='logo-loaded';}}},remove:()=>{removed=true;}};
for(const [type,listener] of events)if(type==='load'||type==='error')listener({target:image});
assert(loaded);assert(removed);
const css=fs.readFileSync(path.join(root,'web/desktop.css'),'utf8');
assert(css.includes('.focus-card-list { display: grid; gap: 12px;'));
assert(css.includes('.reading-sketch .reading-focus-panel { height: 100%; min-height: 0; max-height: 100%;'));
assert(css.includes('#focus-manager { width: 600px; height: 600px;'));
console.log('PASS focus identities, official icons, escaped descriptions, real account matching and stable panels');
