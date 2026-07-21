"""Unit tier: psh.traffic.aggregate_visits_by_month -- the B43 aggregation extracted at
campaign I6 (SPEC D-i6-4).

Pure function (CAMPAIGN.md section 3.4): no sc, no I/O.  Imported from psh.traffic
directly -- the new gated module, not the psh._legacy fixture (whose re-import also
resolves, but the module is the seam under test).
"""
import datetime

import pytest

import psh.traffic
from psh.db import TrafficRow

pytestmark = pytest.mark.unit


def _row(day: str, visits: int = 0, plan: str = "Basic") -> TrafficRow:
    return TrafficRow(
        site_id="test-site-id",
        traffic_date=datetime.date.fromisoformat(day),
        site_plan=plan,
        visits=visits,
        pages_served=0,
        cache_hits=0,
    )


def test_seeds_every_window_month_to_zero_with_no_rows():
    visits, plans = psh.traffic.aggregate_visits_by_month(
        [], datetime.date(2026, 1, 15), datetime.date(2026, 3, 31)
    )
    assert visits == {"2026-01": 0, "2026-02": 0, "2026-03": 0}
    assert plans == {}


def test_sums_visits_within_each_month():
    rows = [
        _row("2026-02-27", visits=7),
        _row("2026-03-01", visits=10),
        _row("2026-03-02", visits=5),
    ]
    visits, _plans = psh.traffic.aggregate_visits_by_month(
        rows, datetime.date(2026, 2, 1), datetime.date(2026, 3, 31)
    )
    assert visits == {"2026-02": 7, "2026-03": 15}


def test_plan_on_day_maps_each_date_last_row_wins():
    rows = [
        _row("2026-03-01", plan="Basic"),
        _row("2026-03-02", plan="Performance Small"),
        _row("2026-03-02", plan="Performance Medium"),
    ]
    _visits, plans = psh.traffic.aggregate_visits_by_month(
        rows, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
    )
    assert plans == {
        datetime.date(2026, 3, 1): "Basic",
        datetime.date(2026, 3, 2): "Performance Medium",
    }


def test_window_spanning_a_year_boundary_seeds_the_right_months():
    visits, _plans = psh.traffic.aggregate_visits_by_month(
        [], datetime.date(2025, 11, 10), datetime.date(2026, 2, 28)
    )
    assert list(visits) == ["2025-11", "2025-12", "2026-01", "2026-02"]
