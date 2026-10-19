import test from 'node:test';
import assert from 'node:assert/strict';
import {availableAnswerActions} from './answerActions.js';
test('해지 고민 응답에서 서버가 허용한 비용·문제 해결 행동만 제공한다',()=>{
 const actions=availableAnswerActions({status:'answered',missing_fields:[],next_actions:['exit_cost','official_support','exit_cost','unknown']});
 assert.deepEqual(actions.map(a=>a.id),['exit_cost','official_support']);
 assert.match(actions[0].question,/오늘/);
 assert.match(actions[1].question,/공식 AI Chat/);
});
test('권한·추가 입력 대기 중에는 완료 응답 행동을 표시하지 않는다',()=>{
 assert.deepEqual(availableAnswerActions({status:'needs_info',missing_fields:['consent'],next_actions:['exit_cost']}),[]);
});
