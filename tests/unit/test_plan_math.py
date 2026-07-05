"""Unit tests for the pure plan-math helpers extracted from main() (test-suite SPEC Part A).

overage_blocks / contract_year_end / estimate_month_visits are import-free pure functions,
so they are exercised directly as psh.<fn>.  Values are pinned exactly (overage_blocks uses
Python's banker's rounding).
"""
import datetime

import pytest

pytestmark = pytest.mark.unit


# ── overage_blocks: round((overage + block/2) / block), banker's rounding ────────────
# Literal expected values (block=10000) — pins the exact rounding, incl. the .5 cases where
# Python's banker's rounding matters (2.5 -> 2, 3.5 -> 4).
@pytest.mark.parametrize(
    "overage,expected",
    [
        (0, 0),          # 0.5 -> 0 (banker's)
        (5000, 1),       # 1.0 -> 1
        (10000, 2),      # 1.5 -> 2 (banker's rounds up here)
        (15000, 2),      # 2.0 -> 2
        (20000, 2),      # 2.5 -> 2 (banker's rounds down here)
        (25000, 3),      # 3.0 -> 3
        (30000, 4),      # 3.5 -> 4 (banker's rounds up here)
    ],
)
def test_overage_blocks_pinned(psh, overage, expected):
    assert psh.overage_blocks(overage, 10000) == expected


def test_overage_blocks_zero_and_monotonic(psh):
    assert psh.overage_blocks(0, 10000) == 0
    prev = -1
    for overage in range(0, 200000, 2500):
        n = psh.overage_blocks(overage, 10000)
        assert n >= prev  # non-decreasing in overage
        assert n >= 0
        prev = n


# ── contract_year_end: True only for June 16-29 ──────────────────────────────────────
@pytest.mark.parametrize(
    "date,expected",
    [
        (datetime.date(2026, 6, 16), True),
        (datetime.date(2026, 6, 29), True),
        (datetime.date(2026, 6, 22), True),
        (datetime.date(2026, 6, 15), False),
        (datetime.date(2026, 6, 30), False),
        (datetime.date(2026, 5, 20), False),
        (datetime.date(2026, 7, 20), False),
        (datetime.date(2026, 12, 25), False),
    ],
)
def test_contract_year_end(psh, date, expected):
    assert psh.contract_year_end(date) is expected


# ── estimate_month_visits: extrapolate the final partial month ───────────────────────
def _dates(*yyyymm):
    return [datetime.date.fromisoformat(m + "-15") for m in yyyymm]


def test_estimate_complete_month_returns_minus_one(psh):
    # end_day == last_day -> month is over -> no estimate.
    vbm = {"2026-01": 100, "2026-02": 200, "2026-03": 300}
    assert psh.estimate_month_visits(vbm, _dates("2026-01", "2026-02", "2026-03"), 31, 31) == -1


def test_estimate_first_day_returns_minus_one(psh):
    # end_day == 1 -> the guard 1 < end_day is false.
    vbm = {"2026-03": 0}
    assert psh.estimate_month_visits(vbm, _dates("2026-03"), 31, 1) == -1


def test_estimate_late_month_pure_extrapolation(psh):
    # last_day >= 25 -> straight extrapolation of the current month only.
    vbm = {"2026-02": 200, "2026-03": 60}
    dates = _dates("2026-02", "2026-03")
    # 60 * 31 / (28 - 1) = 68.888... -> round -> 69
    assert psh.estimate_month_visits(vbm, dates, 31, 28) == round(60 * 31 / (28 - 1))


def test_estimate_single_month_history(psh):
    # Only one month of data -> pure extrapolation regardless of last_day.
    vbm = {"2026-03": 90}
    assert psh.estimate_month_visits(vbm, _dates("2026-03"), 20, 10) == round(90 * 20 / (10 - 1))


def test_estimate_mid_month_blends_previous(psh):
    # 15 <= last_day < 25 -> (2*extrapolate + previous) / 3  (synthetic last_day; real months
    # never have <25 days, but the helper is pure and must honor its inputs).
    vbm = {"2026-02": 300, "2026-03": 40}
    extrapolate = 40 * 20 / (10 - 1)
    assert psh.estimate_month_visits(vbm, _dates("2026-02", "2026-03"), 20, 10) == round(
        (2 * extrapolate + 300) / 3
    )


def test_estimate_early_month_blends_previous(psh):
    # last_day < 15 -> (extrapolate + previous) / 2.
    vbm = {"2026-02": 300, "2026-03": 40}
    extrapolate = 40 * 10 / (5 - 1)
    assert psh.estimate_month_visits(vbm, _dates("2026-02", "2026-03"), 10, 5) == round(
        (extrapolate + 300) / 2
    )
