'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const files=['style.css','workspace.css','desk.css','desktop.css','framework.css'];
const base=fs.readFileSync(path.join(root,'web/style.css'),'utf8');
const all=files.map(name=>fs.readFileSync(path.join(root,'web',name),'utf8')).join('\n');
const tokens=new Map([...all.matchAll(/(--[\w-]+)\s*:\s*([^;}]+)/g)].map(m=>[m[1],m[2].trim()]));
for(const match of all.matchAll(/var\((--[\w-]+)\)/g))assert(tokens.has(match[1]),'undefined token '+match[1]);
for(const name of files){
 const css=fs.readFileSync(path.join(root,'web',name),'utf8').replace(/\/\*[\s\S]*?\*\//g,'');
 let depth=0;for(const c of css){if(c==='{')depth++;if(c==='}')depth--;assert(depth>=0,'unmatched brace in '+name);}
 assert.equal(depth,0,'unclosed block in '+name);
 assert(!/font-size\s*:\s*(10|11)px/.test(css),'metadata below 12px in '+name);
 assert(!/Songti|STSong|Avenir/.test(css),'mixed display font in '+name);
 assert(!/:\s+(?:has|not|is|where|hover|focus|active)\(/.test(css),'broken pseudo selector in '+name);
}
function luminance(hex){
 const rgb=hex.slice(1).match(/../g).map(h=>parseInt(h,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
 return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];
}
function contrast(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
for(const text of ['--ink','--text-secondary','--muted'])for(const bg of ['--paper','--soft','--selected']){
 assert(contrast(tokens.get(text),tokens.get(bg))>=4.5,text+' on '+bg+' must remain readable');
}
assert(contrast(tokens.get('--on-strong'),tokens.get('--strong'))>=7);
for(const color of ['--success','--warning','--danger'])assert(contrast(tokens.get(color),tokens.get('--paper'))>=4.5);
const appearance=fs.readFileSync(path.join(root,'web/appearance.css'),'utf8');
for(const [,name,body] of appearance.matchAll(/:root\[data-theme="([^"]+)"\]\s*\{([^}]+)\}/g)){
 const palette=new Map([...body.matchAll(/(--[\w-]+):\s*(#[\da-f]{6})/g)].map(m=>[m[1],m[2]]));
 for(const text of ['--ink','--text-secondary','--muted'])for(const bg of ['--paper','--soft','--selected']){
  assert(contrast(palette.get(text),palette.get(bg))>=4.5,name+' '+text+' must remain readable on '+bg);
 }
 assert(contrast(palette.get('--on-strong'),palette.get('--strong'))>=4.5,name+' button contrast');
}
assert(base.includes('--sans: -apple-system, BlinkMacSystemFont'));
const desktop=fs.readFileSync(path.join(root,'web/desktop.css'),'utf8');
assert(desktop.includes('--shell-width: 208px'));
assert(desktop.includes('--header-height: 64px'));
assert(desktop.includes('.knowledge-workspace.directory-collapsed.inspector-collapsed'));
assert(desktop.includes('.subscription-card-actions .secondary'));
assert(desktop.includes('dialog .check-row input { width: auto; margin: 0; }'));
console.log('PASS shared neutral tokens, text contrast, 12px floor, consistent font and stable desktop shell');
