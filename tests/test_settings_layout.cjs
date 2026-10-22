'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const css=fs.readFileSync(path.join(root,'web/framework.css'),'utf8');
function rule(selector){const start=css.indexOf(selector+' {');assert(start>=0);return css.slice(start,css.indexOf('}',start)+1);}
assert(rule('#settings-dialog').includes('height:min(640px,84dvh)'));
assert(rule('#settings-dialog').includes('overflow:hidden'));
assert(rule('#settings-dialog[open]').includes('grid-template-rows:auto minmax(0,1fr)'));
assert(rule('.settings-layout').includes('min-height:0'));
assert(rule('.settings-content').includes('overflow:auto'));
assert(rule('.settings-content').includes('scrollbar-gutter:stable'));
const panels=new Map(['model','preferences','appearance','data'].map(id=>['#settings-'+id,{hidden:false}]));
const content={scrollTop:240};panels.set('#settings-dialog .settings-content',content);
const buttons=['model','preferences','appearance','data'].map(id=>({dataset:{settingsTab:id},classList:{toggle(name,value){this[name]=value;}}}));
const ctx=vm.createContext({$:s=>panels.get(s),document:{querySelectorAll:()=>buttons}});
const js=fs.readFileSync(path.join(root,'web/framework.js'),'utf8');
vm.runInContext(js.slice(js.indexOf('function selectSettingsTab('),js.indexOf("$('#asset-new-document')")),ctx);
for(const tab of ['preferences','appearance','data','model']){
 content.scrollTop=240;ctx.selectSettingsTab(tab);
 assert.equal(content.scrollTop,0);
 for(const id of ['model','preferences','appearance','data'])assert.equal(panels.get('#settings-'+id).hidden,id!==tab);
 for(const button of buttons)assert.equal(button.classList.active,button.dataset.settingsTab===tab);
}
console.log('PASS fixed settings shell, internal scrolling, stable gutter and tab scroll reset');
