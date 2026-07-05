"""Unit tests for plan_costs — the pure cost model extracted from main() (test-suite SPEC
Part A; the U-M downgrade guardrails / notices remain in main() and are covered by the golden).

plan_costs does no DB I/O: overage-protection state is injected via op_lookup(month) -> record
| None, so we drive it with SimpleNamespace stand-ins for PantheonOverageProtection rows.
Expected costs are hand-computed and pinned.
"""
import datetime
import types

import pytest

pytestmark = pytest.mark.unit

BLOCK_SIZE = 10000
BLOCK_COST = 40.0
JAN = datetime.date(2025, 1, 1)


def months(start_year_month, n):
    """Return n consecutive 'YYYY-MM' keys starting at start_year_month."""
    y, m = (int(x) for x in start_year_month.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def vbm(start, n, visits):
    return {mo: visits for mo in months(start, n)}


def op_none(_month):
    return None


def op_used(used):
    return lambda _month: types.SimpleNamespace(used_this_month=used)


def call(psh, plan_info, visits_by_month, *, estimate=-1, op_lookup=op_none, v=None):
    plan_names = list(plan_info)
    keys = list(visits_by_month)
    if v is None:
        v = [visits_by_month[k] for k in keys]
    return psh.plan_costs(
        plan_info,
        plan_names,
        visits_by_month,
        v,
        estimate,
        keys[-1],
        JAN,
        BLOCK_SIZE,
        BLOCK_COST,
        op_lookup,
    )


# ── No overage: cost == base cost; costs_best == max(same, median) ───────────────────
def test_no_overage_costs_are_base(psh):
    plan_info = {
        "Basic": {"cost": 500, "traffic_limit": 35000},
        "Performance Small": {"cost": 1925, "traffic_limit": 35000},
    }
    cost_same, costs_median, costs_best, median_visitors = call(
        psh, plan_info, vbm("2025-01", 12, 10000)
    )
    assert cost_same == {"Basic": 500.0, "Performance Small": 1925.0}
    assert costs_median == {"Basic": 500.0, "Performance Small": 1925.0}
    assert median_visitors == 10000
    # Conservative selection metric.
    assert costs_best == {p: max(cost_same[p], costs_median[p]) for p in plan_info}


# ── Overage with an OP record present but unused -> full overage billed ───────────────
def test_overage_no_waiver(psh):
    plan_info = {"P": {"cost": 100, "traffic_limit": 0}}
    cost_same, costs_median, costs_best, median_visitors = call(
        psh, plan_info, vbm("2025-01", 12, 10000), op_lookup=op_used(False)
    )
    # 10000 overage -> round((10000+5000)/10000)=2 blocks -> $80/mo * 12 + $100 base.
    assert cost_same["P"] == 100 + 80 * 12
    # costs_median uses months_without_op=8 for a non-Basic plan.
    assert costs_median["P"] == 100 + 2 * BLOCK_COST * 8
    assert costs_best["P"] == max(cost_same["P"], costs_median["P"])


# ── OP used_this_month=True zeroes every month's overage ─────────────────────────────
def test_overage_fully_waived_by_used_op(psh):
    plan_info = {"P": {"cost": 100, "traffic_limit": 0}}
    cost_same_waived, _, _, _ = call(
        psh, plan_info, vbm("2025-01", 12, 10000), op_lookup=op_used(True)
    )
    cost_same_billed, _, _, _ = call(
        psh, plan_info, vbm("2025-01", 12, 10000), op_lookup=op_used(False)
    )
    assert cost_same_waived["P"] == 100  # base only
    assert cost_same_waived["P"] < cost_same_billed["P"]


# ── Retroactive protection: no OP record, -01 month resets a 4-month waiver window ────
def test_retroactive_waiver_window(psh):
    plan_info = {"P": {"cost": 100, "traffic_limit": 0}}
    cost_same, _, _, _ = call(
        psh, plan_info, vbm("2025-01", 12, 10000), op_lookup=op_none
    )
    # Jan resets op_remaining=4 -> Jan-Apr waived (4 months), May-Dec billed (8 * $80).
    assert cost_same["P"] == 100 + 80 * 8


# ── estimate > 0 replaces the final month's visits in the cost projection ─────────────
def test_estimate_substituted_for_final_month(psh):
    plan_info = {"P": {"cost": 0, "traffic_limit": 0}}
    v = vbm("2025-01", 12, 0)  # all months zero...
    with_estimate, _, _, _ = call(
        psh, plan_info, dict(v), estimate=100000, op_lookup=op_used(False)
    )
    without, _, _, _ = call(psh, plan_info, dict(v), estimate=-1, op_lookup=op_used(False))
    # 100000 overage on the last month -> round((100000+5000)/10000)=10 blocks -> $400.
    assert with_estimate["P"] == 400
    assert without["P"] == 0


# ── Fewer than 12 months -> median-fill extrapolation to a full year ─────────────────
def test_short_history_extrapolated_to_twelve_months(psh):
    plan_info = {"P": {"cost": 100, "traffic_limit": 0}}
    cost_same, _, _, _ = call(
        psh, plan_info, vbm("2025-01", 6, 10000), op_lookup=op_used(False)
    )
    # 6 months at $80 + (12-6) * median([$80]*6) = 480 + 480, plus $100 base.
    assert cost_same["P"] == 100 + 480 + 480


# ── median_visitors reflects v with the estimate swapped into the last slot ───────────
def test_median_visitors_reflects_estimate_swap(psh):
    # Choose v so replacing the last element with the estimate actually MOVES the median (so the
    # test fails if the `v[-1] = estimate` substitution is removed).  With v=[10,20,30,40,50] the
    # median is 30; swapping the max (50) for a small estimate (5) makes it median([5,10,20,30,40])=20.
    plan_info = {"P": {"cost": 0, "traffic_limit": 10_000_000}}  # no overage anywhere
    visits_by_month = vbm("2025-01", 5, 0)
    base_v = [10, 20, 30, 40, 50]

    _, _, _, without = call(psh, plan_info, dict(visits_by_month), estimate=-1, v=list(base_v))
    _, _, _, with_estimate = call(psh, plan_info, dict(visits_by_month), estimate=5, v=list(base_v))

    assert without == 30  # median([10,20,30,40,50])
    assert with_estimate == 20  # median([10,20,30,40,5]) -> the swap moved the median
