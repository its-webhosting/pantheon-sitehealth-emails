"""Unit tests for build_plan_over_time() (P10 fix).

The function collapses a {date: plan} mapping into contiguous plan spans.  The key P10
property is that an empty mapping returns [] instead of raising IndexError (the old inline
code did `plan_on_day[sorted(...)[0]]`, which crashed a zero-traffic site).
"""
import datetime

import pytest

pytestmark = pytest.mark.unit

RIGHT = datetime.date(2026, 3, 31)


def test_empty_mapping_returns_empty_list(psh):
    assert psh.build_plan_over_time({}, RIGHT) == []


def test_single_day_single_span(psh):
    d = datetime.date(2026, 3, 1)
    spans = psh.build_plan_over_time({d: "Performance Small"}, RIGHT)
    assert spans == [{"start": d, "end": RIGHT, "plan": "Performance Small"}]


def test_multiple_days_same_plan_collapse_to_one_span(psh):
    days = {datetime.date(2026, 3, d): "Basic" for d in range(1, 6)}
    spans = psh.build_plan_over_time(days, RIGHT)
    assert spans == [
        {"start": datetime.date(2026, 3, 1), "end": RIGHT, "plan": "Basic"}
    ]


def test_plan_change_produces_two_spans(psh):
    plan_on_day = {
        datetime.date(2026, 3, 1): "Basic",
        datetime.date(2026, 3, 2): "Basic",
        datetime.date(2026, 3, 3): "Performance Small",
        datetime.date(2026, 3, 4): "Performance Small",
    }
    spans = psh.build_plan_over_time(plan_on_day, RIGHT)
    assert spans == [
        {"start": datetime.date(2026, 3, 1), "end": datetime.date(2026, 3, 2), "plan": "Basic"},
        {"start": datetime.date(2026, 3, 3), "end": RIGHT, "plan": "Performance Small"},
    ]
