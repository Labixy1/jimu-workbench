import React from 'react';
import {createRoot} from 'react-dom/client';
import {Excalidraw,exportToSvg,convertToExcalidrawElements} from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';
window.EXCALIDRAW_ASSET_PATH='/board-assets/';
let canvas,root,signature='';
const digest=(elements,appState)=>JSON.stringify([elements.map(e=>[e.id,e.version,e.isDeleted]),appState.viewBackgroundColor]);
export function mountBoard(container,scene={}){
 if(root)root.unmount();
 canvas=null;signature='';root=createRoot(container);
 root.render(<Excalidraw initialData={{elements:scene.elements||[],appState:{...scene.appState,theme:'light'},scrollToContent:true}} langCode="zh-CN" excalidrawAPI={api=>{canvas=api;signature='';requestAnimationFrame(()=>requestAnimationFrame(()=>{if(canvas===api&&api.getSceneElements().length)api.scrollToContent(undefined,{fitToViewport:true,viewportZoomFactor:0.7});}));}} onChange={(elements,appState)=>{if(canvas){const next=digest(elements,appState);if(signature&&signature!==next)window.dispatchEvent(new Event('board-edited'));signature=next;}}} UIOptions={{tools:{image:false},canvasActions:{loadScene:false,saveToActiveFile:false,saveAsImage:false,export:false,toggleTheme:false}}} renderTopRightUI={()=>null} />);
}
export function boardScene(){if(!canvas)throw Error('画板还在加载');return {elements:canvas.getSceneElements(),appState:{viewBackgroundColor:canvas.getAppState().viewBackgroundColor},files:{}};}
export async function boardSvg(){const s=boardScene();return (await exportToSvg({...s,appState:{...canvas.getAppState(),exportWithDarkMode:false},exportPadding:20})).outerHTML;}
export function seedFlow(nodes){if(!canvas)throw Error('画板还在加载');if(canvas.getSceneElements().length)throw Error('请在空画板中生成流程，避免覆盖已有图形');const skeleton=[];nodes.slice(0,10).forEach((label,i)=>{skeleton.push({type:'rectangle',id:'node-'+i,x:100,y:i*130,width:300,height:75,strokeColor:'#81786a',backgroundColor:'#faf8f4',fillStyle:'solid',label:{text:label,fontSize:18}});if(i)skeleton.push({type:'arrow',x:250,y:(i-1)*130+80,points:[[0,0],[0,45]],strokeColor:'#81786a'});});canvas.updateScene({elements:convertToExcalidrawElements(skeleton)});canvas.scrollToContent(undefined,{fitToViewport:true,viewportZoomFactor:0.65});}
