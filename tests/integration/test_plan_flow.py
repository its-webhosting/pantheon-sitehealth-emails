"""Integration tier: the psh.plans flow functions extracted from main()'s per-site loop at
campaign I7 (SPEC D-i7-3/D-i7-7) -- resolve_plan_name (B17) and recommend_plan (B47).

Seams: psh.gateway.run_terminus (the gateway fixture) and a temp sqlite DB (temp_db).
Loop control stays in main(): resolve_plan_name returns None for the skip path."""
import datetime
import json

import pytest

import script_context as sc
from helpers.dnsfake import recording_console
from psh.plans import PlanCatalog, recommend_plan, resolve_plan_name

pytestmark = pytest.mark.integration


def test_non_elite_passthrough_no_terminus_call(psh, gateway, monkeypatch, reset_sc):
    def boom(*a, **k):
        raise AssertionError("terminus must not run for non-Elite plans")
    monkeypatch.setattr(gateway, "run_terminus", boom)
    assert resolve_plan_name({"name": "t1", "plan_name": "Basic"}) == "Basic"


def test_elite_sku_resolves_to_configured_name(psh, gateway, monkeypatch, reset_sc):
    sc.config = {"Pantheon": {"plan_sku_to_name": {"plan-elite-x": "Elite 1M"}}}
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps({"sku": "plan-elite-x"}), "", False))
    assert resolve_plan_name({"name": "t1", "plan_name": "Elite"}) == "Elite 1M"


def test_elite_transient_failure_returns_none(psh, gateway, monkeypatch, reset_sc):
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: ("", "boom [warning]", True))
    console = recording_console(monkeypatch, sc)
    assert resolve_plan_name({"name": "t1", "plan_name": "Elite"}) is None
    out = console.export_text()
    assert "could not fetch plan info for t1" in out
    assert "boom [warning]" in out  # Invariant 6: stderr escape()d, rich must not eat it


def test_elite_missing_sku_is_fatal(psh, gateway, monkeypatch, reset_sc):
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps({}), "", False))
    with pytest.raises(SystemExit, match="Bailing out."):
        resolve_plan_name({"name": "t1", "plan_name": "Elite"})


def test_elite_unknown_sku_is_fatal(psh, gateway, monkeypatch, reset_sc):
    sc.config = {"Pantheon": {"plan_sku_to_name": {}}}
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps({"sku": "plan-weird"}), "", False))
    with pytest.raises(SystemExit, match="Bailing out."):
        resolve_plan_name({"name": "t1", "plan_name": "Elite"})


PLAN_CONFIG = {
    "plan_info": {
        "Basic": {"cost": 300.0, "traffic_limit": 1000, "upgrade_at": 800,
                  "upgrade_to": "Performance Small", "downgrade_to": "-"},
        "Performance Small": {"cost": 1200.0, "traffic_limit": 5000, "upgrade_at": 4000,
                              "upgrade_to": "Performance Medium", "downgrade_to": "Basic"},
        "Performance Medium": {"cost": 3000.0, "traffic_limit": 10000, "upgrade_at": 8000,
                               "upgrade_to": "-", "downgrade_to": "Performance Small"},
    },
}
SIX_MONTHS = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
START = datetime.date(2025, 3, 1)
END = datetime.date(2026, 3, 31)
PLAN_START = datetime.date(2025, 10, 1)


def _recommend(temp_db, reset_sc, *, current_plan, visits, months=SIX_MONTHS):
    """Run recommend_plan against an empty overage-protection table.

    Cost model with this catalog, 6 x visits=3000 (overage 2000 on Basic -> 2 blocks x
    $100): cost_same/best Basic 2700, PS 1200, PM 3000.  With visits=100: Basic 300,
    PS 1200, PM 3000 (no overage anywhere).
    """
    catalog = PlanCatalog.from_config(
        {"plan_info": {k: dict(v) for k, v in PLAN_CONFIG["plan_info"].items()}},
        overage_block_size=1000, overage_block_cost=100.0)
    site = {"id": "s-id-1", "name": "t1", "plan_name": current_plan}
    site_context = reset_sc.SiteContext({"name": "t1"})
    rec = recommend_plan(
        temp_db.session(), site, catalog, dict.fromkeys(months, visits), PLAN_START,
        -1, START, END, 0, site_context,
    )
    return rec, site_context


def test_too_few_months_returns_defaults(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Basic", visits=3000,
                          months=SIX_MONTHS[:3])
    assert rec.months_until_recommendations == 2
    assert rec.median_visitors == 0
    assert rec.cost_same == {} and rec.cost_table_rows == {}
    assert rec.recommended_plan == "Basic" and rec.current_plan == "Basic"
    assert rec.current_plan_index == 0 and rec.recommended_plan_index == 0
    assert rec.savings == 0.0 and rec.savings_entry is None
    assert ctx["notices"] == []


def test_upgrade_adds_notice_and_savings_entry(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Basic", visits=3000)
    assert rec.recommended_plan == "Performance Small"
    assert (rec.current_plan_index, rec.recommended_plan_index) == (0, 1)
    assert rec.savings == 1500.0            # |cost_same[Basic] 2700 - best[PS] 1200|
    assert rec.savings_entry == {"site": "t1", "savings": 1500.0,
                                 "current_plan": "Basic",
                                 "recommended_plan": "Performance Small"}
    [notice] = ctx["notices"]
    assert notice["csv"] == "t1,its-recommends-plan,Basic,Performance Small,1500.00"


def test_non_basic_downgrade_gets_a_savings_entry(psh, temp_db, reset_sc):
    # RED against the verbatim extraction (D-i7-4): non-Basic downgrades used to
    # vanish from the operator's savings summary.  Still no owner notice (SPEC).
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Medium",
                          visits=3000)
    assert rec.recommended_plan == "Performance Small"
    assert rec.savings == 1800.0            # |cost_same[PM] 3000 - best[PS] 1200|
    assert rec.savings_entry == {"site": "t1", "savings": 1800.0,
                                 "current_plan": "Performance Medium",
                                 "recommended_plan": "Performance Small"}
    assert ctx["notices"] == []


def test_basic_downgrade_floors_at_performance_small(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Small", visits=100)
    assert rec.recommended_plan == "Performance Small"   # guardrail held at the floor
    assert rec.savings == 0.0
    assert rec.savings_entry == {"site": "t1", "savings": 0.0,
                                 "current_plan": "Performance Small",
                                 "recommended_plan": "Performance Small"}
    assert ctx["notices"] == []


def test_basic_downgrade_finds_better_intermediate_plan(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Medium",
                          visits=100)
    assert rec.recommended_plan == "Performance Small"   # alt between PM and Basic
    assert rec.savings == 1800.0            # |cost_same[PM] 3000 - best[PS] 1200|
    assert rec.savings_entry is not None and ctx["notices"] == []


def test_no_change_recommended(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Small",
                          visits=3000)
    assert rec.recommended_plan == "Performance Small"
    assert rec.savings == 0.0 and rec.savings_entry is None and ctx["notices"] == []
    assert "Recommended Plan" in rec.cost_table_rows["Performance Small"]["notes"]
    assert "Current Plan" in rec.cost_table_rows["Performance Small"]["notes"]
