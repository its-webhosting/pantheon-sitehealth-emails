"""Unit tier: psh.traffic.build_traffic_window -- the B43 + B44-residue traffic-window /
chart-data prep extracted from main() (development/2026-08-07-main-extraction/SPEC.md §5.1).

Pure function seam (SPEC §6 row 1): a list[TrafficRow], two datetime.dates, two strs in;
a TrafficWindow NamedTuple out.  No I/O, no monkeypatching -- sc.options/sc.console come
from the autouse reset_sc fixture (tests/conftest.py).  Imported from psh.traffic directly,
same idiom as tests/unit/test_traffic_aggregation.py.
"""
import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

import psh.traffic
from psh.db import TrafficRow

pytestmark = pytest.mark.unit

START = datetime.date(2026, 1, 1)
END = datetime.date(2026, 3, 31)


def _row(day: str, visits: int = 0, plan: str = "Basic") -> TrafficRow:
    return TrafficRow(
        site_id="test-site-id",
        traffic_date=datetime.date.fromisoformat(day),
        site_plan=plan,
        visits=visits,
        pages_served=0,
        cache_hits=0,
    )


def test_zero_traffic_seeds_a_single_synthetic_plan_day():
    """R1.5: the five zero-traffic-seed postconditions, the P10 IndexError guard."""
    window = psh.traffic.build_traffic_window(
        [], START, END, "Basic", "its-wws-test1"
    )
    assert window.plan_on_day == {END: "Basic"}
    assert window.first_plan_day == END
    assert window.last_plan_day == END
    assert len(window.plan_over_time) == 1
    assert window.site_plan_start == END.replace(day=1)
    assert window.estimate == -1


def test_happy_path_aggregates_visits_and_collapses_plan_spans():
    """Real traffic across a plan change: visits_by_month sums per month, plan_over_time
    collapses to contiguous spans, and a mid-month end_date extrapolates (estimate != -1)."""
    mid_month_end = datetime.date(2026, 3, 15)
    rows = [
        _row("2026-01-10", visits=100, plan="Basic"),
        _row("2026-02-05", visits=50, plan="Basic"),
        _row("2026-02-20", visits=25, plan="Performance Small"),
        _row("2026-03-01", visits=10, plan="Performance Small"),
    ]
    window = psh.traffic.build_traffic_window(
        rows, START, mid_month_end, "Performance Small", "its-wws-test1"
    )
    assert window.visits_by_month == {"2026-01": 100, "2026-02": 75, "2026-03": 10}
    assert window.dates == [
        datetime.date(2026, 1, 15),
        datetime.date(2026, 2, 15),
        datetime.date(2026, 3, 15),
    ]
    assert window.plan_over_time == [
        {
            "start": datetime.date(2026, 1, 10),
            "end": datetime.date(2026, 2, 5),
            "plan": "Basic",
        },
        {
            "start": datetime.date(2026, 2, 20),
            "end": datetime.date(2026, 3, 31),
            "plan": "Performance Small",
        },
    ]
    assert window.first_plan_day == datetime.date(2026, 1, 10)
    assert window.last_plan_day == datetime.date(2026, 3, 1)
    assert window.site_plan_start == datetime.date(2026, 1, 1)
    assert window.plot_right_date == datetime.date(2026, 3, 31)
    assert window.estimate != -1


def test_empty_current_plan_is_carried_through_the_synthetic_seed():
    """Shadow path (R1.6): a current_plan of "" is not special-cased -- it seeds
    plan_on_day exactly like any other plan string would."""
    window = psh.traffic.build_traffic_window([], START, END, "", "its-wws-test1")
    assert window.plan_on_day == {END: ""}
    assert window.plan_over_time == [
        {"start": END, "end": END, "plan": ""}
    ]


def test_rows_entirely_outside_the_window_raise_keyerror():
    """Shadow path (R1.6): an out-of-window row is not sanitized here -- aggregate_visits_by_month's
    docstring says a month outside [start_date, end_date] KeyErrors, exactly as the inline code
    this replaces did.  This is a behavior-preserving move, not a new validation."""
    out_of_window_row = _row("2025-06-15", visits=5)
    with pytest.raises(KeyError):
        psh.traffic.build_traffic_window(
            [out_of_window_row], START, END, "Basic", "its-wws-test1"
        )


@given(
    plans=st.lists(
        st.sampled_from(["Basic", "Performance Small", "Performance Medium"]),
        min_size=0,
        max_size=5,
    )
)
def test_plan_on_day_is_never_empty(plans):
    """R1.5's Hypothesis property: whatever traffic history is given (including none),
    plan_on_day is never empty -- the direct guard on the P10 IndexError the synthetic
    seed exists to prevent."""
    rows = [
        _row(f"2026-01-{i + 1:02d}", visits=1, plan=plan)
        for i, plan in enumerate(plans)
    ]
    window = psh.traffic.build_traffic_window(
        rows, START, END, "Basic", "its-wws-test1"
    )
    assert window.plan_on_day != {}
