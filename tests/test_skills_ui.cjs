'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const framework=fs.readFileSync('web/framework.js','utf8'),workflow=fs.readFileSync('web/chat-workflow.js','utf8');
const nodes=new Map(),events=[];
const skills=['experience-writing','jd-review','knowledge-compilation','weekly-reading','board-generation'].map((id,i)=>({id,name:id,title:'Skill '+i,description:'Use when needed',revision:1,files:['SKILL.md']}));
function node(selector){if(!nodes.has(selector))nodes.set(selector,{value:'',innerHTML:'',textContent:'',hidden:false,focus(){events.push('focus')},classList:{toggle(){}},showModal(){this.open=true},close(){this.open=false}});return nodes.get(selector);}
const ctx=vm.createContext({$:node,esc:String,state:{skills},skillRefs:new Map(),kind:'chat',render(){events.push('render')},switchView:async view=>{events.push(view);return true},document:{addEventListener(){}},atob,TextDecoder,Uint8Array,md:text=>'<p>'+text+'</p>',scoped:p=>p,api:async()=>{},toast(){}});
vm.runInContext('let skillEditing=null;',ctx);
vm.runInContext(framework.slice(framework.indexOf('function renderSkills('),framework.indexOf('document.addEventListener(\'click\',async e=>{\n const button=e.target.closest(\'[data-delete-skill]')),ctx);
vm.runInContext(framework.slice(framework.indexOf('async function useSkill('),framework.indexOf('function renderReferencePicker(')),ctx);
(async()=>{
 ctx.renderSkills();assert(!node('#skill-list').innerHTML.includes('data-built-in-board'));
 assert(node('#skill-list').innerHTML.includes('SKILL.md'));
 for(const skill of skills){await ctx.useSkill(skill.id);assert.equal(ctx.kind,'chat');}
 assert.equal(ctx.skillRefs.size,5,'no three-skill cap');
 await ctx.useSkill(skills[0].id);assert.equal(ctx.skillRefs.size,5,'single click is idempotent');
 assert(events.filter(e=>e==='home').length===6);
 ctx.switchView=async()=>false;ctx.skillRefs.clear();await ctx.useSkill(skills[0].id);assert.equal(ctx.skillRefs.size,0,'cancelled navigation does not add a reference');
 const flyout=workflow.slice(workflow.indexOf("document.addEventListener('click',e=>{const b=e.target.closest('[data-flyout-skill]"),workflow.indexOf('function proposalFile'));
 assert(!flyout.includes("kind='"),'hover picker cannot turn a skill into a hard-coded workflow');
 const doc='---\nname: sample\ndescription: Use for a focused test.\n---\n# Sample\nRead references/example.md.';
 ctx.openSkillEditor({id:'sample',title:'Sample',skill_md:doc,resources:[{path:'references/example.md',content:btoa('Reference text')}]});
 assert.equal(node('#skill-preview').hidden,false);
 node('#skill-instructions').value=doc+'\nUnsaved change.';
 vm.runInContext("skillActiveFile='references/example.md';skillEditorTab='edit'",ctx);ctx.renderSkillEditor();
 assert(node('#skill-preview').innerHTML.includes('Reference text'));
 vm.runInContext("skillActiveFile='SKILL.md'",ctx);ctx.renderSkillEditor();assert(node('#skill-instructions').value.endsWith('Unsaved change.'));
 ctx.confirm=async()=>false;await ctx.closeSkillEditor();assert.equal(node('#skill-editor').open,true);
 ctx.confirm=async()=>true;await ctx.closeSkillEditor();assert.equal(node('#skill-editor').open,false);
 vm.runInContext(workflow.slice(workflow.indexOf('function proposalFile'),workflow.indexOf('function renderReview')),ctx);
 assert.equal(ctx.proposalFile({payload:{kind:'chat',chat_output:'document',proposal:{page:{title:'Result',content:'Body'}}}}).title,'Result');
 const polish=fs.readFileSync('web/chat-polish.js','utf8');
 vm.runInContext(polish.slice(polish.indexOf('function executionToolMarkup'),polish.indexOf('function executionMarkup')),ctx);
 assert(ctx.executionToolMarkup({name:'skill',skill:'sample',status:'completed'}).includes('加载 Skill · sample · 完成'));
 const html=fs.readFileSync('web/index.html','utf8');assert(!html.includes('id="skill-picker"'));assert(!html.includes('最多同时引用3个'));
 const css=fs.readFileSync('web/desktop.css','utf8');assert(css.includes('height:min(680px,calc(100dvh - 56px))'));
 console.log('PASS Skill package UI, explicit references without task routing, resource/draft persistence and native load traces');
})().catch(error=>{console.error(error);process.exitCode=1;});
