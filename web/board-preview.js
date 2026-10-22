'use strict';
function boardThumbnail(scene,id){
 const num=v=>Number.isFinite(v)&&Math.abs(v)<=1000000?v:0;
 const color=(v,fallback)=>/^(#[0-9a-f]{3,8}|transparent|white|black)$/i.test(String(v))?v:fallback;
 const elements=(Array.isArray(scene?.elements)?scene.elements:[]).filter(e=>e&&!e.isDeleted),marker='thumb-'+String(id).replace(/[^a-z0-9]/gi,'');
 if(!elements.length)return '<div class="board-thumb-empty">空白画板</div>';
 // Include line points in the bounds so negative/reversed arrows fit the preview.
 const points=e=>Array.isArray(e.points)?e.points.slice(0,2000).filter(Array.isArray):[];
 const bounds=elements.flatMap(e=>{const x=num(e.x),y=num(e.y),w=Math.abs(num(e.width)),h=Math.abs(num(e.height)),angle=num(e.angle),cos=Math.cos(angle),sin=Math.sin(angle);return (['line','arrow','freedraw'].includes(e.type)&&points(e).length?points(e):[[0,0],[w,0],[w,h],[0,h]]).map(p=>{const px=num(p[0])-w/2,py=num(p[1])-h/2;return [x+w/2+px*cos-py*sin,y+h/2+px*sin+py*cos];});}).reduce((b,p)=>[Math.min(b[0],p[0]),Math.min(b[1],p[1]),Math.max(b[2],p[0]),Math.max(b[3],p[1])],[Infinity,Infinity,-Infinity,-Infinity]);
 const [left,top]=bounds,width=Math.max(1,bounds[2]-left),height=Math.max(1,bounds[3]-top),scale=Math.min(550/width,290/height);
 const shapes=elements.map(e=>{const w=Math.abs(num(e.width)),h=Math.abs(num(e.height)),stroke=color(e.strokeColor,'#81786a'),fill=color(e.backgroundColor,'transparent'),angle=num(e.angle)*180/Math.PI,transform=`translate(${num(e.x)} ${num(e.y)}) rotate(${angle} ${w/2} ${h/2})`,attrs=`stroke="${stroke}" fill="${fill}" stroke-width="${Math.max(1,Math.min(6,num(e.strokeWidth)||2))}"`;
 let shape='';const dash=e.strokeStyle==='dashed'?'stroke-dasharray="8 6"':'';
 if(e.type==='text'){const lines=String(e.text||'').split('\n').slice(0,80),size=Math.max(8,Math.min(150,num(e.fontSize)||18));shape=`<text fill="${stroke}" font-family="PingFang SC,sans-serif" font-size="${size}" text-anchor="${e.textAlign==='center'?'middle':e.textAlign==='right'?'end':'start'}" x="${e.textAlign==='center'?w/2:e.textAlign==='right'?w:0}">${lines.map((t,i)=>`<tspan x="${e.textAlign==='center'?w/2:e.textAlign==='right'?w:0}" y="${size+i*size*1.3}">${esc(t)}</tspan>`).join('')}</text>`;}
 else if(e.type==='ellipse')shape=`<ellipse cx="${w/2}" cy="${h/2}" rx="${w/2}" ry="${h/2}" ${attrs}/>`;
 else if(e.type==='diamond')shape=`<polygon points="${w/2},0 ${w},${h/2} ${w/2},${h} 0,${h/2}" ${attrs} ${dash}/>`;
 else if(['line','arrow','freedraw'].includes(e.type)){const line=(points(e).length?points(e):[[0,0],[w,h]]).map(p=>num(p[0])+','+num(p[1])).join(' ');shape=`<polyline points="${line}" stroke="${stroke}" stroke-width="2" fill="none" ${dash} ${e.type==='arrow'?'marker-end="url(#'+marker+')"':''}/>`;}
 else shape=`<rect width="${w}" height="${h}" rx="${e.roundness?Math.min(10,w/8):0}" ${attrs} ${dash}/>`;
 return `<g transform="${transform}">${shape}</g>`;}).join('');
 return `<svg viewBox="0 0 600 340" aria-hidden="true"><defs><marker id="${marker}" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="none" stroke="#81786a"/></marker></defs><rect width="600" height="340" fill="${color(scene?.appState?.viewBackgroundColor,'#fffefa')}"/><g transform="translate(${(600-width*scale)/2} ${(340-height*scale)/2}) scale(${scale}) translate(${-left} ${-top})">${shapes}</g></svg>`;
}
