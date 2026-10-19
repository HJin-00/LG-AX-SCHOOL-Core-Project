import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
test('새 디자인의 모든 진입점은 실제 상담 기능에 연결된다',async()=>{
 const root=fileURLToPath(new URL('../',import.meta.url));const folder=await mkdtemp(path.join(tmpdir(),'team-design-'));const target=path.join(folder,'check.cjs');
 try{
 await build({stdin:{resolveDir:root,loader:'jsx',contents:`import React from 'react';import {renderToStaticMarkup} from 'react-dom/server';import {MemoryRouter} from 'react-router-dom';import Welcome from './src/components/layout/Welcome.jsx';import HomeHero from './src/components/layout/HomeHero.jsx';import Sidebar from './src/components/layout/Sidebar.jsx';import {services} from './src/components/layout/topics.js';import ChatMessage from './src/components/chat/ChatMessage.jsx';
 const render=x=>renderToStaticMarkup(React.createElement(MemoryRouter,null,x));
 export const home=render(React.createElement(HomeHero));
 export const existing=render(React.createElement(Welcome,{serviceType:'existing',onLoadProduct:()=>{},onTopicSelect:()=>{}}));
 export const purchase=render(React.createElement(Welcome,{serviceType:'purchase',onTopicSelect:()=>{}}));
 export const comparison=render(React.createElement(ChatMessage,{message:{role:'assistant',status:'answered',topic:'contract',requestTopic:'renewal',sources:[],cards:[{type:'renewal_comparison',data:{request:{planned_start_date:'2026-12-01',comparison_months:36,comparison_date:'2026-10-06',installation_conditions:{}},comparison_start:'2026-11-01',comparison_end:'2029-10-31',renewal_start:'2026-12-01',options:[{choice:'keep',estimated_total:360000,confirmed_subtotal:360000,missing_fields:[]},{choice:'renew',subscription_months:35,estimated_total:null,scenario_total:720000,confirmed_subtotal:0,missing_fields:[]}],limitations:'확인 조건 기준'}}]}}));
 export const briefReady=render(React.createElement(ChatMessage,{message:{role:'assistant',status:'brief_created',topic:'contract',brief_id:'brief-test',answer:'준비 완료',cards:[{type:'renewal_comparison',data:{}}]}}));
 export const periodExplanation=render(React.createElement(ChatMessage,{message:{role:'assistant',status:'answered',topic:'contract',answer:'**의무사용 종료일**: 약정한 의무사용 기간의 마지막 날입니다.\\n\\n**전체 계약 종료일**: 전체 구독 계약의 마지막 날입니다.\\n\\n두 날짜의 관계: 의무사용이 끝나도 남은 전체 계약 동안 이용과 요금이 계속될 수 있습니다.'+' 설명'.repeat(180),sources:[],cards:[]}}));
 export const sidebar=render(React.createElement(Sidebar,{topics:services.existing.categories,disabled:true}));`},bundle:true,platform:'node',format:'cjs',loader:{'.png':'dataurl','.jpg':'dataurl','.css':'empty'},outfile:target});
 const result=createRequire(import.meta.url)(target);
 assert.match(result.home,/href="\/existing"/);assert.match(result.home,/https:\/\/www.lge.co.kr\/category\/water-purifiers/);
 for(const page of [result.existing]){assert(!/disabled=""/.test(page),'초기 카드가 잘못된 category ID로 비활성화되면 안 됨');assert(!page.includes('lookup_subscription_offers'));assert(!page.includes('assess_symptom_next_step'));}
 assert.match(result.existing,/다른 정수기로 바꾸면/);assert.match(result.existing,/내 계약은 언제 끝나/);assert.match(result.existing,/지금 해지하면/);assert.match(result.existing,/AI Chat/);
 assert(!result.home.includes('href="/purchase"'));
 assert.match(result.briefReady,/상담 준비서 PDF 다운로드/);
 assert.equal((result.briefReady.match(/상담 준비서가 준비됐어요/g)||[]).length,1);
 assert(!result.briefReady.includes('현재 제품 유지'));
 assert(!result.briefReady.includes('변경한 조건으로 비교'));
 assert.match(result.comparison,/월평균/);assert.match(result.comparison,/다른 제품 고르기/);assert.match(result.comparison,/희망 조건 바꾸기/);
 assert.match(result.sidebar,/disabled=""/);
 assert.match(result.periodExplanation,/두 날짜의 관계/);assert(!result.periodExplanation.includes('설명 전체 보기'));

 assert.match(result.comparison,/agent-message--wide/);assert.match(result.comparison,/35개월/);assert.match(result.comparison,/10,000/);assert.match(result.comparison,/20,000/);assert(!result.comparison.includes('undefined'));
 }finally{await rm(folder,{recursive:true,force:true});}
});
