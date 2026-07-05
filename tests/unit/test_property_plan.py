"""Property tests (Hypothesis) for the extracted plan math (test-suite SPEC §7.2).

Complements the example-based tests with invariants that must hold across a wide input space:
overage_blocks monotonicity/non-negativity, and plan_costs never crashing while returning a
well-formed, internally consistent result.
"""
import datetime

import pytest
from hypothesis import given, strategies as st

pytestmark = pytest.mark.unit

BLOCK = 10000
BLOCK_COST = 40.0
JAN = datetime.date(2025, 1, 1)

PLAN_INFO = {
    "Basic": {"cost": 500, "traffic_limit": 35000},
    "Performance Small": {"cost": 1925, "traffic_limit": 35000},
    "Performance Medium": {"cost": 3300, "traffic_limit": 70000},
}
PLAN_NAMES = list(PLAN_INFO)


@given(overage=st.integers(min_value=0, max_value=10**9))
def test_overage_blocks_nonnegative_int(psh, overage):
    n = psh.overage_blocks(overage, BLOCK)
    assert isinstance(n, int)
    assert n >= 0
    assert psh.overage_blocks(0, BLOCK) == 0


@given(a=st.integers(min_value=0, max_value=10**9), b=st.integers(min_value=0, max_value=10**9))
def test_overage_blocks_monotonic(psh, a, b):
    lo, hi = sorted((a, b))
    assert psh.overage_blocks(lo, BLOCK) <= psh.overage_blocks(hi, BLOCK)


def _months(n):
    y, m, out = 2025, 1, []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


@given(visits=st.lists(st.integers(min_value=0, max_value=5_000_000), min_size=5, max_size=13))
def test_plan_costs_wellformed_and_consistent(psh, visits):
    keys = _months(len(visits))
    visits_by_month = dict(zip(keys, visits))
    cost_same, costs_median, costs_best, median_visitors = psh.plan_costs(
        PLAN_INFO,
        PLAN_NAMES,
        visits_by_month,
        list(visits),
        -1,
        keys[-1],
        JAN,
        BLOCK,
        BLOCK_COST,
        lambda _m: None,
    )
    assert set(cost_same) == set(PLAN_NAMES)
    assert set(costs_median) == set(PLAN_NAMES)
    assert set(costs_best) == set(PLAN_NAMES)
    assert median_visitors >= 0
    for p in PLAN_NAMES:
        # Costs are the base plan cost plus non-negative overage, so never below base.
        assert cost_same[p] >= float(PLAN_INFO[p]["cost"])
        assert costs_median[p] >= float(PLAN_INFO[p]["cost"])
        # The conservative selection metric is exactly the elementwise max.
        assert costs_best[p] == max(cost_same[p], costs_median[p])
