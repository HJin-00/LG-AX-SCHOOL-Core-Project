from types import SimpleNamespace as R
from 정수기프로젝트.app.agent.next_actions import answer_actions

def test_completed_answers_suggest_related_actions():
    reply=R(status='answered',missing_fields=[],cards=[])
    assert answer_actions('contract_fees',reply)==['compare_new','exit_cost','contract_terms']
    assert answer_actions('exit_cost',reply)==['compare_new','contract_fees']
    assert answer_actions('official_support',reply)==[]

def test_incomplete_or_existing_selection_does_not_duplicate_actions():
    assert answer_actions('contract_fees',R(status='needs_info',missing_fields=['consent'],cards=[]))==[]
    for kind in ['renewal_catalog','renewal_comparison','product']:
        assert answer_actions('contract_terms',R(status='answered',missing_fields=[],cards=[R(type=kind)]))==[]
