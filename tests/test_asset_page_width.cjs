'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/asset-browser.js','utf8');
const helpers=source.slice(source.indexOf('const assetPageWidths='),source.indexOf('function assetExtension('));
function setup(saved,unavailable=false){
 const body={dataset:{},draft:'unsaved document',scrollTop:170};
 const options=['normal','wide','full'].map(id=>({dataset:{assetPageWidth:id},setAttribute(name,value){this[name]=value;}}));
 const values=new Map([['jimu-asset-page-width',saved]]);
 const ctx=vm.createContext({
  localStorage:{getItem(key){if(unavailable)throw Error('Storage unavailable');return values.get(key);},setItem(key,value){if(unavailable)throw Error('Storage unavailable');values.set(key,value);}},
  $:()=>body,document:{querySelectorAll:()=>options}
 });
 vm.runInContext(helpers,ctx);
 return {ctx,body,options,values};
}
const {ctx,body,options,values}=setup(null);
assert.equal(vm.runInContext('assetPageWidth',ctx),'wide');
for(const width of ['normal','full','wide']){
 ctx.setAssetPageWidth(width);
 assert.equal(body.dataset.pageWidth,width);
 assert.equal(values.get('jimu-asset-page-width'),width);
 assert.equal(options.filter(option=>option['aria-pressed']==='true').length,1);
 assert.equal(options.find(option=>option['aria-pressed']==='true').dataset.assetPageWidth,width);
 assert.equal(body.draft,'unsaved document');
 assert.equal(body.scrollTop,170);
}
ctx.setAssetPageWidth('invalid');
assert.equal(body.dataset.pageWidth,'wide');
assert.equal(vm.runInContext('assetPageWidth',setup('full').ctx),'full');
assert.equal(vm.runInContext('assetPageWidth',setup('invalid').ctx),'wide');
const blocked=setup(null,true).ctx;
assert.doesNotThrow(()=>blocked.setAssetPageWidth('normal'));
assert.equal(vm.runInContext('assetPageWidth',blocked),'normal');
const markup=ctx.assetPageWidthPicker();
assert.equal((markup.match(/data-asset-page-width=/g)||[]).length,3);
assert(markup.includes('popover="auto"'));
assert(markup.includes('popovertarget="asset-page-width-menu"'));
for(const label of ['常规','超宽','全宽'])assert(markup.includes(label));
const css=fs.readFileSync('web/desktop.css','utf8');
assert(css.includes('.asset-body[data-page-width] { --asset-page-max:1280px; }'));
assert(css.includes('.asset-body[data-page-width="normal"] { --asset-page-max:880px; }'));
assert(css.includes('.asset-body[data-page-width="full"] { --asset-page-max:100%; }'));
assert(css.includes('>:is(.asset-body-content,.asset-inline-editor)'));
console.log('PASS three document widths, persistence, invalid/unavailable storage, unchanged drafts and scroll');
