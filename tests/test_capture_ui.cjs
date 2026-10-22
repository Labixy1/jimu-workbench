'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/capture.js','utf8'),nodes=new Map();
function node(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',value:'',hidden:false,disabled:false,querySelectorAll:()=>[],removeAttribute(){}});return nodes.get(key);}
const ctx=vm.createContext({URL,Set,Map,$:node,document:{addEventListener(){}},state:{categories:[]},scoped:x=>x,esc:x=>String(x).replaceAll('<','&lt;').replaceAll('>','&gt;'),api:async()=>({trace:[]})});
vm.runInContext(source,ctx);
(async()=>{
 await ctx.captureAction(async()=>({id:'fixture',article:{title:'Explicit fixture',content:'Body fixture',url:'https://example.com',cover_url:'',source_name:'Fixture'},trace:[]}));
 assert.equal(node('#capture-title').value,'Explicit fixture');assert.equal(node('#capture-save').disabled,false);assert.equal(node('#capture-cover').hidden,true);
 assert.equal(ctx.captureHasEdits(),false);
 node('#capture-content').value='My edited fixture';assert.equal(ctx.captureHasEdits(),true);
 let closed=false;node('#capture-dialog').close=()=>{closed=true;};ctx.confirm=async()=>false;
 await ctx.closeCaptureDialog();assert.equal(closed,false,'cancel preserves unsaved edits');
 ctx.confirm=async()=>true;await ctx.closeCaptureDialog();assert.equal(closed,true);
 vm.runInContext('capturePreview=null',ctx);
 await ctx.captureAction(async()=>{throw Error('Explicit fixture reading error');});
 assert.equal(node('#capture-error').textContent,'Explicit fixture reading error');assert.equal(node('#capture-save').disabled,true);assert.equal(node('#capture-preview').hidden,true);
 ctx.renderCaptureTrace([{tool:'browser_get_html',status:'failed'}]);assert(node('#capture-trace').innerHTML.includes('class="failed"'));
 const framework=fs.readFileSync('web/framework.js','utf8');
 ctx.state.categories=[{id:'a',name:'Source folder',scope:'materials',parent_id:''},{id:'b',name:'Output folder',scope:'creations',parent_id:''}];
 vm.runInContext(framework.slice(framework.indexOf('function categoryOptions('),framework.indexOf('function populateSourceCategories(')),ctx);
 const options=ctx.assetSaveOptions('b','creations');assert(options.includes('value="a"'));assert(options.includes('value="b" selected'));assert(options.indexOf('Output folder')<options.indexOf('Source folder'));
 assert(source.includes("Boolean(b.closest('.favorite-add-menu'))"),'favorites entry preserves its intent');
 console.log('PASS native capture preview, failed-read guard, tool status and all asset destinations');
})().catch(error=>{console.error(error);process.exitCode=1;});
