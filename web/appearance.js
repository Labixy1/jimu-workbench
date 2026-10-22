'use strict';
const jimuThemes=[{id:'classic',name:'原色',note:'简洁中性',colors:['#f7f7f7','#ffffff','#e9e9e9','#202020']},{id:'sage',name:'纸感鼠尾草',note:'温润、安静',colors:['#f3f4ed','#fffefb','#e6eddf','#345742']},{id:'mist',name:'清透雾蓝',note:'清爽、专注',colors:['#f1f5f8','#ffffff','#e4edf5','#34556e']}];
let jimuTheme='classic',appearanceSaving=false;
function applyJimuTheme(theme){jimuTheme=jimuThemes.some(t=>t.id===theme)?theme:'classic';document.documentElement.dataset.theme=jimuTheme;try{localStorage.setItem('jimu-theme',jimuTheme);}catch{}renderAppearance();}
function renderAppearance(){const panel=document.getElementById('appearance-options');if(!panel)return;panel.innerHTML=jimuThemes.map(t=>`<button type="button" class="appearance-card ${jimuTheme===t.id?'selected':''}" data-theme-choice="${t.id}" aria-pressed="${jimuTheme===t.id}" ${appearanceSaving?'disabled':''}><span class="appearance-sample" style="--sample-side:${t.colors[0]};--sample-body:${t.colors[1]};--sample-active:${t.colors[2]};--sample-ink:${t.colors[3]}"><i></i><span><b></b><b></b><b></b></span></span><strong>${t.name}</strong><small>${t.note}</small>${jimuTheme===t.id?'<span class="theme-check">✓</span>':''}</button>`).join('');}
try{applyJimuTheme(localStorage.getItem('jimu-theme'));}catch{applyJimuTheme('classic');}
document.addEventListener('DOMContentLoaded',()=>{
 renderAppearance();
 fetch('/api/appearance').then(r=>{if(!r.ok)throw Error();return r.json();}).then(v=>applyJimuTheme(v.theme)).catch(()=>{});
 document.addEventListener('click',async e=>{const b=e.target.closest('[data-theme-choice]');if(!b||appearanceSaving)return;appearanceSaving=true;renderAppearance();try{const saved=await api('/api/appearance',{theme:b.dataset.themeChoice});applyJimuTheme(saved.theme);}catch(error){toast(error.message);}finally{appearanceSaving=false;renderAppearance();}});
});
