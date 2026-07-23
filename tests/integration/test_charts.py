"""Seam tests for psh.charts.build_chart (campaign I11, SPEC section 4 Deliverable C).

Integration tier: real matplotlib (Agg backend -- conftest sets MPLBACKEND before any
import), real sc (the autouse reset_sc fixture provides sc.options, which sc.debug
reads).  The chart PNG is NOT pinned by the e2e goldens (the .eml has no byte golden),
so these tests are the permanent behavioral cover for the chart build; the increment's
move-time byte-preservation evidence was SPEC section 6's before/after payload-hash
comparison, recorded in the dev folder.
"""

import datetime
import struct

import matplotlib.pyplot as plt
import pytest

from psh.charts import build_chart

pytestmark = pytest.mark.integration

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# One plan spanning the whole window keeps the fixture minimal; upgrade_at 20,000
# puts the surge threshold at 30,000 (upgrade_at_max * 1.5).
PLAN_INFO = {
    "Basic": {"traffic_limit": 25000, "upgrade_at": 20000, "downgrade_to": None},
}
SURGE_SPIKE = 90_000  # far above the 30,000 threshold
MONTHS = [
    "2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01",
    "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
]


def png_size(png):
    """Width/height from the IHDR chunk (always first, big-endian uint32 at 16/20)."""
    return struct.unpack(">II", png[16:24])


def shaped_locals(spike=None):
    """The 13 build_chart kwargs, shaped like main()'s locals (SPEC D-i11-1).

    plan_on_day carries every month midpoint -- the documented precondition
    (SPEC D-i11-7): the clamp in the covered-visits loop must land on existing keys.
    """
    visits_by_month = {m: 1000 + 500 * i for i, m in enumerate(MONTHS)}
    if spike is not None:
        visits_by_month[MONTHS[5]] = spike
    dates = [datetime.date.fromisoformat(m + "-15") for m in MONTHS]
    plan_on_day = {d: "Basic" for d in dates}
    return {
        "site": {"name": "charts-test"},
        "site_url": "https://charts.example.edu",
        "visits_by_month": visits_by_month,
        "plan_on_day": plan_on_day,
        "plan_info": PLAN_INFO,
        "plan_over_time": [
            {"plan": "Basic", "start": dates[0], "end": datetime.date(2026, 7, 31)},
        ],
        "dates": dates,
        "estimate": 4200,
        "first_plan_day": dates[0],
        "last_plan_day": dates[-1],
        "start_date": datetime.date(2025, 8, 1),
        "end_date": datetime.date(2026, 7, 31),
        "plot_right_date": datetime.date(2026, 7, 31),
    }


def test_returns_png_bytes():
    png = build_chart(**shaped_locals())
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 1000


def test_surge_renders_taller_two_axes_figure():
    """The surge branch builds the 12x12 GridSpec figure vs the plain 12x9 one, so at
    equal dpi the surge PNG is strictly taller -- proves the branch ran, not just that
    some PNG came back."""
    plain = build_chart(**shaped_locals())
    surge = build_chart(**shaped_locals(spike=SURGE_SPIKE))
    plain_w, plain_h = png_size(plain)
    surge_w, surge_h = png_size(surge)
    assert plain_w == surge_w
    assert surge_h > plain_h


def test_estimate_changes_the_render():
    """estimate=-1 (month already over) must drop the estimate bars/labels.  Guards the
    estimates=[] prologue init (SPEC D-i11-4) against a regression that skips the
    estimate histogram entirely."""
    kwargs = shaped_locals()
    with_estimate = build_chart(**kwargs)
    kwargs["estimate"] = -1
    without_estimate = build_chart(**kwargs)
    assert with_estimate != without_estimate


def test_deterministic_bytes():
    """Two identical calls -> identical bytes: the property the .eml reproducibility
    and SPEC section 6's hash evidence rest on (PD#14: prove it, don't assume it)."""
    assert build_chart(**shaped_locals()) == build_chart(**shaped_locals())


def test_no_leaked_figures():
    """Guards the moved plt.close(fig): a leak is invisible until a 300-site --all run
    exhausts memory."""
    build_chart(**shaped_locals())
    build_chart(**shaped_locals(spike=SURGE_SPIKE))
    assert plt.get_fignums() == []
