import {build} from 'esbuild';
import {cp,mkdir} from 'node:fs/promises';
await build({entryPoints:['ui-board/main.jsx'],bundle:true,conditions:['production'],minify:true,format:'esm',splitting:true,outdir:'web/board-assets',define:{'process.env.NODE_ENV':'"production"'},loader:{'.woff2':'file','.woff':'file'},assetNames:'[name]-[hash]'});
await cp('ui-board/node_modules/@excalidraw/excalidraw/dist/prod/fonts','web/board-assets/fonts',{recursive:true});
