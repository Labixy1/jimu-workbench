'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/asset-browser.js','utf8');
const framework=fs.readFileSync('web/framework.js','utf8');
const nodes=new Map();
const input={value:'Unsaved folder',selectionStart:3,selectionEnd:8,disabled:false,focus(){document.activeElement=this;},select(){},setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}};
const error={textContent:''},save={disabled:false},cancel={disabled:false};
const form={hidden:false,parent:null,contains:element=>element===input,querySelectorAll:()=>[input,save,cancel],addEventListener(){}};
const sidebar={scrollTop:80,append(node){assert.notEqual(node,null,'append(null) creates visible null text');node.parent=this;nodes.set('#category-form',node);}};
const row={append(node){node.parent=list;}};
const list={markup:'',set innerHTML(value){
 if(form.parent===this)nodes.delete('#category-form');
 this.markup=value;
},get innerHTML(){return this.markup;},querySelector(){return {closest:()=>row};}};
const document={activeElement:input,querySelectorAll:()=>[],addEventListener(){}};
nodes.set('#category-form',form);nodes.set('#category-name',input);nodes.set('#category-error',error);nodes.set('#category-cancel',cancel);
nodes.set('.category-sidebar',sidebar);nodes.set('#category-list',list);nodes.set('#source-search',{value:''});nodes.set('#source-list',{innerHTML:''});
const categories=[{id:'parent',name:'Project',scope:'materials',parent_id:'',revision:2}];
const calls=[];
let releaseRequest;
const ctx=vm.createContext({
 document,$:selector=>nodes.get(selector)||null,esc:String,
 state:{categories,sources:[],artifacts:[]},catalogItems:()=>[],
 libraryCategory:'parent',libraryOrigin:'materials',categoryEditing:{scope:'materials',parent_id:'parent'},categorySaving:false,
 openFolders:new Set(['parent']),closeAssetMenus(){},assetIcon:()=>'<svg></svg>',assetMoreIcon:()=>'<svg></svg>',
 leaveAssetFile:async()=>true,api:async(path,data)=>{calls.push({path,data});if(releaseRequest)await releaseRequest;return {id:'child',name:data.name,scope:data.scope,parent_id:data.parent_id};},
 load:async()=>{ctx.renderAssetBrowser();},
});
vm.runInContext("let assetSelectedId=null,assetEditing=false;const assetCategoryForm=$('#category-form');",ctx);
vm.runInContext(source.slice(source.indexOf('function renderAssetBrowser()'),source.indexOf('function renderAssetBody()')),ctx);
ctx.renderAssetCatalog=()=>ctx.renderAssetBrowser();
vm.runInContext(framework.slice(framework.indexOf('async function beginFolderEdit('),framework.indexOf('function isDocumentDirty(')),ctx);
vm.runInContext(framework.slice(framework.indexOf("$('#category-form').onsubmit="),framework.indexOf("$('#document-preview-tab').onclick=")),ctx);
(async()=>{
 // The form is deliberately attached inside the subtree about to be replaced.
 form.parent=list;
 for(let i=0;i<5;i++)ctx.renderAssetBrowser();
 assert.equal(nodes.get('#category-form'),form);
 assert.equal(form.hidden,false);
 assert.equal(input.value,'Unsaved folder');
 assert.equal(input.selectionStart,3);assert.equal(input.selectionEnd,8);
 assert.equal(sidebar.scrollTop,80);
 assert(!list.innerHTML.includes('null'));
 assert(list.innerHTML.includes('folder-entry selected'));
 ctx.cancelFolderEdit();assert.equal(form.hidden,true);assert.equal(input.value,'');
 await ctx.beginFolderEdit({scope:'creations',parent_id:''});
 assert.equal(ctx.libraryOrigin,'creations');assert.equal(ctx.libraryCategory,'all');
 input.value='  ';await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,0);assert(error.textContent.includes('名称'));
 input.value='Result notes';
 let unblock;releaseRequest=new Promise(resolve=>unblock=resolve);
 const request=form.onsubmit({preventDefault(){}});
 assert.equal(save.disabled,true);
 await form.onsubmit({preventDefault(){}});
 assert.equal(calls.length,1,'double submits are ignored');
 unblock();await request;releaseRequest=null;
 assert.equal(calls[0].data.scope,'creations');assert.equal(calls[0].data.parent_id,'');
 assert.equal(form.hidden,true);assert.equal(save.disabled,false);
 await ctx.beginFolderEdit({id:'parent',revision:2,scope:'materials',parent_id:''},'Project');
 input.value='New project';await form.onsubmit({preventDefault(){}});
 assert.equal(calls[1].data.id,'parent');assert.equal(calls[1].data.revision,2);
 await ctx.beginFolderEdit({scope:'materials',parent_id:'parent'});
 input.value='Retry name';ctx.api=async()=>{throw Error('Fixture conflict');};
 await form.onsubmit({preventDefault(){}});
 assert.equal(input.value,'Retry name');assert.equal(error.textContent,'Fixture conflict');assert.equal(save.disabled,false);
 const css=fs.readFileSync('web/desktop.css','utf8');
 assert(css.includes('#sources-view .category-sidebar { background: transparent; box-shadow: none;'));
 assert(css.includes('grid-template-columns: minmax(0,1fr) 28px;'));
 assert(css.includes('.asset-menu-popup[popover] { position: fixed;'));
 const html=fs.readFileSync('web/index.html','utf8');
 assert.equal((html.match(/id="category-form"/g)||[]).length,1);
 assert(html.includes('id="category-cancel"'));
 console.log('PASS live folder form survives tree rerenders, preserves drafts, handles create/rename/errors and reserves aligned controls');
})().catch(error=>{console.error(error);process.exitCode=1;});
