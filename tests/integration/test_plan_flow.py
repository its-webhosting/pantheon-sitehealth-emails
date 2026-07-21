"""Integration tier: the psh.plans flow functions extracted from main()'s per-site loop at
campaign I7 (SPEC D-i7-3/D-i7-7) -- resolve_plan_name (B17) and recommend_plan (B47).

Seams: psh.gateway.run_terminus (the gateway fixture) and a temp sqlite DB (temp_db).
Loop control stays in main(): resolve_plan_name returns None for the skip path."""
import json

import pytest

import script_context as sc
from helpers.dnsfake import recording_console
from psh.plans import resolve_plan_name

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
