'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.resolve(__dirname, '../web');
const html = fs.readFileSync(path.join(web, 'index.html'), 'utf8');
const app = fs.readFileSync(path.join(web, 'app.js'), 'utf8');
const knowledge = fs.readFileSync(path.join(web, 'knowledge.js'), 'utf8');
const thread = {scrollHeight: 1000, clientHeight: 500, scrollTop: 500};
const messagesNode = {innerHTML: ''};
const ctx = vm.createContext({
  $: selector => selector === '.chat-thread' ? thread : messagesNode,
  requestAnimationFrame: callback => callback(),
  esc: text => String(text).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  md: text => String(text).replaceAll('<', '&lt;'),
  state: {jobs: [{id: 'fixture_ui_job', payload: {kind: 'chat'}}]},
  messages: [], lastSignature: '',
});
vm.runInContext(app.slice(app.indexOf('function renderMessages()'), app.indexOf('function renderProgress()')), ctx);
const composer = html.indexOf('<div class="composer-dock">');
assert(html.indexOf('id="review-panel"') < composer, 'review belongs in the scrollable thread');
assert(html.indexOf('id="job-progress"') < composer, 'execution status belongs in the scrollable thread');
assert.equal((html.match(/id="composer"/g) || []).length, 1);
assert(knowledge.includes('id="knowledge-save-error" class="error" role="alert"'), 'save errors also exist in annotation mode');
ctx.messages = [{role: 'assistant', text: 'Local UI fixture', job_id: 'fixture_ui_job'}];
ctx.renderMessages();
assert(messagesNode.innerHTML.includes('存为文稿'));
assert.equal(thread.scrollTop, 1000, 'follow a reply when already at the end');
thread.scrollTop = 100;
ctx.messages = [{role: 'user', text: '<script>not executable</script>'}];
ctx.renderMessages();
assert.equal(thread.scrollTop, 100, 'do not pull a reader away from an older message');
assert(!messagesNode.innerHTML.includes('<script>'));
console.log('PASS chat structure, scroll follow, safe text and annotation-mode save errors');
