from 정수기프로젝트.app.mcp.subscription.renewal_benefits import assess_renewal_benefit
import pytest
@pytest.mark.parametrize('day,eligible',[('2026-07-28',False),('2026-07-29',True),('2026-11-30',True),('2027-11-30',True),('2027-12-01',False)])
def test_window_boundaries(day,eligible):
    r=assess_renewal_benefit('2026-11-30',day,72,[{'amount':50900}],'official')
    assert (r['status']=='conditional')==eligible
    assert r['confirmed_rate_percent'] is None
    assert r['maximum_scenario_saving']==(2545 if eligible else None)
@pytest.mark.parametrize('months,source',[(60,'official'),(72,'synthetic')])
def test_no_unverified_rate(months,source):
    r=assess_renewal_benefit('2026-11-30','2026-10-13',months,[{'amount':50900}],source)
    assert r['maximum_scenario_saving'] is None
