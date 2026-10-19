import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
test('손상된 복원 메시지는 정상 메시지 렌더를 중단하지 않는다',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'conversation-render-'));
 try{
 const entry=path.resolve('src/components/chat/Conversation.jsx');
 await build({stdin:{contents:`import React from 'react';import{renderToStaticMarkup}from'react-dom/server';import Conversation from ${JSON.stringify(entry)};export function render(messages){return renderToStaticMarkup(React.createElement(Conversation,{messages}));}`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,platform:'node',format:'cjs',outfile:path.join(dir,'render.cjs'),loader:{'.png':'dataurl','.jpg':'dataurl','.css':'empty'}});
 const {render}=require(path.join(dir,'render.cjs'));
 for(const broken of [null,{role:'assistant',cards:'broken'},{role:'assistant',cards:[null]},{role:'assistant',answer:{}}]){
 assert.doesNotThrow(()=>render([broken,{role:'user',text:'유효한 질문'}]));
 assert.match(render([broken,{role:'user',text:'유효한 질문'}]),/유효한 질문/);
 }
 }finally{await rm(dir,{recursive:true,force:true});}
});
