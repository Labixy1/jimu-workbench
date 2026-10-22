'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),calls=[],timers=[],toasts=[];
function node(selector){
 if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',value:'',checked:false,disabled:false,open:false,
  classList:{toggle(name,value){this[name]=value;}},showModal(){this.open=true;},close(){this.open=false;},setAttribute(){},
  querySelector:s=>node(selector+' '+s),querySelectorAll:()=>[]});
 return nodes.get(selector);
}
const schedule={enabled:false,frequency:'weekly',weekday:0,time:'09:00',revision:0,next_run:null};
const state={sources:[],categories:[],asset_meta:{},weekly:{subscriptions:[{id:'fixture',title:'Explicit fixture',urls:['https://example.com/feed']}],news:[],runs:[]},reading:{issues:[],favorites:[],groups:[],focus:[],updates:{schedule:{...schedule},current:null,last_run:null}}};
let statusReply,saveFails=false,loads=0;
const ctx=vm.createContext({URL,document:{addEventListener(){},querySelectorAll:()=>[]},$:node,esc:String,view:'work',pages:()=>[],catalogItems:()=>[],state,
 setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},load:async()=>{loads++;},toast:s=>toasts.push(s),
 api:async(url,data)=>{calls.push({url,data});if(url==='/api/reading/update')return{id:'run_fixture',status:'running',trigger:'manual'};
  if(url==='/api/reading/updates')return statusReply||state.reading.updates;
  if(url==='/api/reading/schedule'){if(saveFails)throw Error('Explicit fixture save failure');return{...data,revision:data.revision+1};}
  return[];}});
vm.runInContext(fs.readFileSync('web/desk.js','utf8'),ctx);
vm.runInContext('readingCollectionLoaded=true',ctx);
ctx.renderDesk();
let html=node('#work-content').innerHTML;
assert(html.includes('>手动更新</button>'));assert(html.includes('>定时更新</button>'));assert(html.includes('>来源管理</button>'));
assert(!html.includes('>更新本期</button>'));
ctx.watchReadingUpdates();assert.equal(timers.length,0,'default disabled setting does not poll or schedule work');
assert.equal(ctx.readingScheduleTime('2026-10-21T01:00:00Z'),'10/21 09:00');

function setFields(enabled,frequency='weekly'){
 node('#reading-auto-enabled').checked=enabled;node('#reading-auto-frequency').value=frequency;
 node('#reading-auto-weekday').value='0';node('#reading-auto-time').value='09:00';
 ctx.syncReadingScheduleForm();
}
(async()=>{
 await ctx.readingScheduleDialog();
 assert(node('#reading-schedule-dialog').open);
 assert(node('#reading-schedule-dialog').innerHTML.includes('北京时间'));
 assert(node('#reading-schedule-dialog').innerHTML.includes('不调用付费模型'));
 assert.equal(calls.filter(c=>c.data).length,0,'opening settings never saves or starts a run');
 setFields(false);assert(node('#reading-auto-fields').disabled);
 setFields(true,'daily');assert(!node('#reading-auto-fields').disabled);assert(node('#reading-auto-weekday').disabled);
 setFields(true,'weekly');assert(!node('#reading-auto-weekday').disabled);
 assert.equal(calls.filter(c=>c.data).length,0,'editing fields is only a draft until save');
 setFields(false);
 await node('#reading-schedule-dialog form').onsubmit({preventDefault(){}});
 assert.equal(calls.find(c=>c.data).url,'/api/reading/schedule');assert.equal(calls.find(c=>c.data).data.enabled,false);
 assert(!node('#reading-schedule-dialog').open);assert(!state.reading.updates.schedule.enabled);
 await ctx.readingScheduleDialog();setFields(true,'daily');saveFails=true;
 await node('#reading-schedule-dialog form').onsubmit({preventDefault(){}});
 assert(node('#reading-schedule-dialog').open);assert(node('#reading-auto-error').textContent.includes('fixture save failure'));
 assert(!node('#reading-auto-save').disabled);assert(!state.reading.updates.schedule.enabled);
 node('#reading-schedule-dialog').close();saveFails=false;
 await ctx.updateCurrentReading();await ctx.updateCurrentReading();
 assert.equal(calls.filter(c=>c.url==='/api/reading/update').length,1,'double-click cannot launch two refreshes');
 assert(state.reading.updates.current);assert(node('#work-content').innerHTML.includes('更新中…'));
 assert.equal(timers.at(-1).ms,1800);
 statusReply={schedule:{...schedule},current:null,last_run:{id:'run_fixture',status:'partial',added:1,warnings:[{url:'https://example.com/broken',error:'Explicit fixture failure'}],read_warnings:[]}};
 await ctx.pollReadingUpdates();
 assert.equal(state.reading.updates.current,null);assert.equal(loads,1);
 assert(toasts.at(-1).includes('部分来源'));assert.equal(vm.runInContext('newsRefreshing',ctx),false);
 ctx.renderDesk();assert(node('#work-content').innerHTML.includes('查看更新情况'));
 await ctx.readingScheduleDialog();assert(node('#reading-auto-status').innerHTML.includes('Explicit fixture failure'));
 setFields(true,'daily');await node('#reading-schedule-dialog form').onsubmit({preventDefault(){}});
 assert(state.reading.updates.schedule.enabled);assert.equal(timers.at(-1).ms,15000);
 const css=fs.readFileSync('web/desktop.css','utf8');
 assert(css.includes('width: 480px; height: 466px;'));assert(css.includes('height: var(--reading-room-height);'));
 assert(css.includes('.reading-auto-body { padding: 0 24px; flex: 1; min-height: 0; overflow: auto;'));
 assert(css.includes('flex: 0 0 88px;'));
 console.log('PASS reading update controls, schedule draft/save/errors, non-overlap, completion polling and fixed geometry');
})().catch(error=>{console.error(error);process.exitCode=1;});
