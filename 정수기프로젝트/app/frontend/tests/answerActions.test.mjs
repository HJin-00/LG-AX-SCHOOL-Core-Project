import test from 'node:test';
import assert from 'node:assert/strict';
import {availableAnswerActions} from '../src/api/answerActions.js';
test('완료된 답변의 서버 행동만 중복 없이 표시하고 권한 대기에는 숨긴다',()=>{
 assert.deepEqual(availableAnswerActions({status:'answered',next_actions:['compare_new','unknown','exit_cost','compare_new']}).map(a=>a.id),['compare_new','exit_cost']);
 assert.deepEqual(availableAnswerActions({status:'needs_info',next_actions:['compare_new']}),[]);
 assert.deepEqual(availableAnswerActions({status:'answered',missing_fields:['consent'],next_actions:['compare_new']}),[]);
});
