'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const nodes = new Map();
let confirmation = false;
const ctx = vm.createContext({
  document: {addEventListener() {}}, window: {addEventListener() {}},
  $: key => nodes.get(key), confirm: async () => confirmation,
  esc: value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c])),
});
for (const file of ['knowledge.js', 'board-preview.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'web', file), 'utf8'), ctx);
}
const framework = fs.readFileSync(path.join(root, 'web/framework.js'), 'utf8');
vm.runInContext(framework.slice(framework.indexOf('function documentSourcesMarkup('), framework.indexOf('function renderDocument()')), ctx);
let count = 0;
const test = async (name, fn) => {await fn(); count++; console.log('PASS ' + name);};
(async () => {
  await test('knowledge columns follow the first non-weekly tag', () => {
    const groups = ctx.knowledgeGroups([{body:{tags:['Agent', 'Tools']}}, {body:{tags:['Agent']}}, {body:{tags:[]}}], false);
    assert.equal(groups[0][0], 'Agent'); assert.equal(groups[0][1].length, 2); assert.equal(groups[1][0], '未分类');
  });
  await test('weekly marker is not used as the column title', () => {
    assert.equal(ctx.knowledgeGroups([{body:{tags:['周刊', '每周阅读']}}], true)[0][0], '每周阅读');
    assert.equal(ctx.knowledgeGroups([{body:{tags:['周刊']}}], true)[0][0], '阅读周刊');
  });
  await test('empty or malformed scene has an empty preview', () => {
    assert.match(ctx.boardThumbnail(null, 'test'), /空白画板/);
    assert.match(ctx.boardThumbnail({elements:{}}, 'test'), /空白画板/);
  });
  await test('deleted elements are absent', () => {
    assert.match(ctx.boardThumbnail({elements:[{isDeleted:true}]}, 'test'), /空白画板/);
  });
  await test('document sources group exact quotes without executing source markup', () => {
    const output=ctx.documentSourcesMarkup({citations:[{source_id:'src_one',quote:'<script>unsafe</script>'},{source_id:'src_one',quote:'second quote'}]},[{id:'src_one',title:'<img onerror=bad>'}]);
    assert(output.includes('来源依据 · 1 份材料'));
    assert.equal((output.match(/data-source=/g)||[]).length,1);
    assert.equal((output.match(/<blockquote>/g)||[]).length,2);
    assert(!output.includes('<script>'));
    assert(!output.includes('<img'));
    assert(output.includes('&lt;script&gt;'));
  });
  await test('missing document sources retain quotes without a broken source button', () => {
    assert.equal(ctx.documentSourcesMarkup({citations:[]},[]),'');
    const output=ctx.documentSourcesMarkup({citations:[{source_id:'src_gone',quote:'original words'}]},[]);
    assert(output.includes('来源已归档'));
    assert(output.includes('original words'));
    assert(!output.includes('data-source='));
  });
  await test('reference arrows keep their dashed style', () => {
    const svg=ctx.boardThumbnail({elements:[{type:'arrow',id:'reference',x:50,y:50,width:80,height:0,points:[[0,0],[80,0]],strokeStyle:'dashed'}]},'reference');
    assert(svg.includes('stroke-dasharray="8 6"'));
  });
  await test('text, colors and marker ids cannot inject markup', () => {
    const svg = ctx.boardThumbnail({elements:[{type:'text', text:'<script>bad</script>', strokeColor:'red" onload="evil', width:30, height:30}], appState:{viewBackgroundColor:'url(https://evil)'}}, '"><script>');
    assert(!svg.includes('<script>')); assert(!svg.includes('onload')); assert(!svg.includes('https://evil'));
    assert(svg.includes('&lt;script&gt;'));
  });
  await test('nonfinite geometry and oversized point arrays stay finite', () => {
    const svg = ctx.boardThumbnail({elements:[{type:'arrow', x:NaN, y:Infinity, width:-20, height:15, points:Array.from({length:30000}, () => [NaN, Infinity])}]}, 'test');
    assert(!/NaN|Infinity/.test(svg)); assert(svg.length < 20000);
  });
  await test('reversed arrows and rotated rectangles retain a finite viewport', () => {
    const svg = ctx.boardThumbnail({elements:[{type:'rectangle', x:5, y:20, width:120, height:15, angle:Math.PI/2}, {type:'arrow', points:[[0,0],[-90,-100]]}]}, 'test');
    assert(svg.includes('rotate(90')); assert(!/NaN|Infinity/.test(svg));
  });
  await test('canceling navigation preserves the exact dirty document', async () => {
    vm.runInContext("knowledgeDraft={id:'wiki_test', content:'unsaved', dirty:true}; knowledgeEditing=true", ctx);
    assert.equal(await ctx.leaveKnowledge(), false);
    assert.equal(vm.runInContext('knowledgeDraft.content', ctx), 'unsaved');
    assert.equal(vm.runInContext('knowledgeEditing', ctx), true);
  });
  await test('confirmed navigation discards only the local draft', async () => {
    confirmation = true; assert.equal(await ctx.leaveKnowledge(), true);
    assert.equal(vm.runInContext('knowledgeDraft', ctx), null);
  });
  await test('annotation drafts are separate for each document', () => {
    nodes.set('#knowledge-note-quote', {value:'quote A'}); nodes.set('#knowledge-note-text', {value:'note A'});
    ctx.rememberKnowledgeNote('wiki_a'); nodes.get('#knowledge-note-text').value='note B'; ctx.rememberKnowledgeNote('wiki_b');
    assert.equal(vm.runInContext("knowledgeNoteDrafts.get('wiki_a').text", ctx), 'note A');
    assert.equal(vm.runInContext("knowledgeNoteDrafts.get('wiki_b').text", ctx), 'note B');
  });
  await test('stale annotation response cannot replace the current document', async () => {
    vm.runInContext("pageId='wiki_b'", ctx); let resolve;
    ctx.api = () => new Promise(r => resolve=r); nodes.set('#knowledge-notes', {innerHTML:'current notes'});
    const pending=ctx.loadKnowledgeNotes('wiki_a'); resolve([{quote:'wrong', text:'wrong'}]); await pending;
    assert.equal(nodes.get('#knowledge-notes').innerHTML, 'current notes');
  });
  await test('document save carries the original version and keeps references', async () => {
    const page={id:'wiki_a', revision:2, body:{tags:['Agent'], citations:[{source_id:'src_a', quote:'original'}], diagram:['first'], links:[]}};
    ctx.pages=()=>[page]; let payload;
    ctx.api=async (url,data)=>{payload=data; return {id:'wiki_a', revision:3};};
    ctx.load=async()=>{}; ctx.toast=()=>{};
    vm.runInContext("knowledgeDraft={id:'wiki_a',revision:2,title:'title',summary:'summary',content:'text',tags:'Agent',links:['wiki_b'],dirty:true}",ctx);
    await ctx.saveKnowledge(); assert.equal(payload.revision,2); assert.equal(payload.page.links[0],'wiki_b');
    assert.equal(payload.page.citations,page.body.citations); assert.equal(payload.page.diagram,page.body.diagram);
  });
  await test('revision conflict keeps the exact local draft and displays an error', async () => {
    ctx.api=async()=>{throw Error('stale version');}; nodes.set('#knowledge-save-error',{textContent:''});
    vm.runInContext("knowledgeDraft={id:'wiki_a',revision:2,title:'title',summary:'summary',content:'keep me',tags:'Agent',links:[],dirty:true}",ctx);
    await ctx.saveKnowledge(); assert.equal(vm.runInContext('knowledgeDraft.content',ctx),'keep me');
    assert.equal(nodes.get('#knowledge-save-error').textContent,'stale version');
  });
  console.log(`${count} presentation checks passed`);
})().catch(error => {console.error(error); process.exitCode=1;});
