'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8');
const ctx=vm.createContext({URL,esc:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),pages:()=>[]});
vm.runInContext(source.slice(source.indexOf('function md('),source.indexOf('async function load()')),ctx);
const html=ctx.md('# Fixture\n\n[Original source](https://example.com/post?id=2&mode=read)\n---\n**Evidence**\n`<script>`');
assert(html.includes('href="https://example.com/post?id=2&amp;mode=read"'));
assert(html.includes('rel="noopener noreferrer"'));
assert(html.includes('<hr>'));
assert(html.includes('<strong>Evidence</strong>'));
assert(html.includes('<code>&lt;script&gt;</code>'));
for(const input of ['[click](javascript:alert(1))','[click](data:text/html,evil)','[click](https://user:pass@example.com)','<img src=x onerror=alert(1)>']){
 const result=ctx.md(input);assert(!result.includes('<a '));assert(!result.includes('<img'));
}
const code=ctx.md('```html\n<script>alert(1)</script>\n[not a link](https://example.com)\n```');
assert(code.includes('<pre><code>'));assert(!code.includes('<a'));assert(!code.includes('<script>'));
const table=ctx.md('| Title | URL |\n| --- | --- |\n| **Fixture** | [Source](https://example.com) |');
assert(table.includes('<table>'));assert(table.includes('<strong>Fixture</strong>'));assert(table.includes('<a '));
console.log('PASS readable Markdown links, separators, fenced code, tables and unsafe-link rejection');
