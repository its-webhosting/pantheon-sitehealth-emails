"""Integration tier: psh.plans.resolve_site_plan, main()'s per-site plan resolution --
the resolve_plan_name call site, the Sandbox skip, and the unknown-plan guard
(development/2026-08-07-main-extraction/SPEC.md section 5.5 -- B17 (residue), the
Sandbox half of B18, and B20).

Seam (SPEC section 6 row 5): psh.gateway.run_terminus (the `gateway` conftest fixture)
for the Elite-SKU plan:info call inside resolve_plan_name; a non-Elite site makes NO
subprocess call at all. sc.config["Pantheon"]["plan_sku_to_name"] comes from reset_sc.

The single sentinel `None` covers TWO distinct skip reasons -- a transient plan:info
failure and the Sandbox plan (SPEC R5.5.2) -- collapsing them is safe because each path
prints its own operator message before returning; that message is asserted per-path
below via recording_console."""
import json

import pytest
from helpers.dnsfake import recording_console

import script_context as sc
from psh.plans import resolve_site_plan

pytestmark = pytest.mark.integration

PLAN_NAMES = ["Basic", "Performance Small", "Performance Medium"]


# ── happy path: non-Elite passthrough, no terminus call ───────────────────────────────
def test_non_elite_plan_returned_and_written_in_place(psh, gateway, monkeypatch, reset_sc):
    def boom(*a, **k):
        raise AssertionError("terminus must not run for non-Elite plans")
    monkeypatch.setattr(gateway, "run_terminus", boom)

    site = {"name": "t1", "plan_name": "Basic"}
    assert resolve_site_plan(site, PLAN_NAMES) == "Basic"
    assert site["plan_name"] == "Basic"


# ── happy path: Elite SKU resolves through terminus plan:info ─────────────────────────
def test_elite_plan_resolves_and_is_written_in_place(psh, gateway, monkeypatch, reset_sc):
    sc.config = {"Pantheon": {"plan_sku_to_name": {"plan-elite-x": "Performance Medium"}}}
    monkeypatch.setattr(
        gateway, "run_terminus",
        lambda *a, **k: (json.dumps({"sku": "plan-elite-x"}), "", False),
    )
    site = {"name": "t1", "plan_name": "Elite"}
    assert resolve_site_plan(site, PLAN_NAMES) == "Performance Medium"
    assert site["plan_name"] == "Performance Medium"  # in-place write, R5.5.5


# ── skip sentinel #1: transient plan:info failure ──────────────────────────────────────
def test_elite_transient_failure_returns_none_and_prints_own_message(
    psh, gateway, monkeypatch, reset_sc
):
    monkeypatch.setattr(
        gateway, "run_terminus", lambda *a, **k: ("", "boom [warning]", True)
    )
    console = recording_console(monkeypatch, sc)
    assert resolve_site_plan({"name": "t1", "plan_name": "Elite"}, PLAN_NAMES) is None
    out = console.export_text()
    assert "could not fetch plan info for t1" in out


# ── skip sentinel #2: Sandbox plan ──────────────────────────────────────────────────────
def test_sandbox_plan_returns_none_and_prints_own_message(psh, gateway, monkeypatch, reset_sc):
    def boom(*a, **k):
        raise AssertionError("terminus must not run for a non-Elite Sandbox site")
    monkeypatch.setattr(gateway, "run_terminus", boom)
    console = recording_console(monkeypatch, sc)

    site = {"name": "t1", "plan_name": "Sandbox"}
    assert resolve_site_plan(site, PLAN_NAMES) is None
    assert site["plan_name"] == "Sandbox"  # still written in place before the skip
    out = console.export_text()
    assert "t1 is on the Sandbox plan, skipping it." in out


# ── postcondition: an unknown plan is fatal ─────────────────────────────────────────────
def test_unknown_plan_exits(psh, gateway, monkeypatch, reset_sc):
    def boom(*a, **k):
        raise AssertionError("terminus must not run for a non-Elite unknown-plan site")
    monkeypatch.setattr(gateway, "run_terminus", boom)

    site = {"name": "t1", "plan_name": "Enterprise"}
    with pytest.raises(SystemExit, match="Bailing out."):  # noqa: RUF043 -- match is a substring regex; the literal SystemExit message is "Bailing out." and escaping would change the assertion's pattern semantics
        resolve_site_plan(site, PLAN_NAMES)
    assert site["plan_name"] == "Enterprise"  # written in place before the exit (R5.5.5)


# ── shadow: empty plan_names -- every plan is unknown ───────────────────────────────────
def test_empty_plan_names_makes_every_plan_unknown(psh, gateway, monkeypatch, reset_sc):
    def boom(*a, **k):
        raise AssertionError("terminus must not run for a non-Elite site")
    monkeypatch.setattr(gateway, "run_terminus", boom)

    with pytest.raises(SystemExit, match="Bailing out."):  # noqa: RUF043 -- match is a substring regex; the literal SystemExit message is "Bailing out." and escaping would change the assertion's pattern semantics
        resolve_site_plan({"name": "t1", "plan_name": "Basic"}, [])


# ── shadow: upstream error -- an Elite site whose plan:info is fatal skips, not aborts ──
def test_elite_fatal_plan_info_skips_not_aborts(psh, gateway, monkeypatch, reset_sc):
    monkeypatch.setattr(
        gateway, "run_terminus", lambda *a, **k: ("", "connection reset", True)
    )
    recording_console(monkeypatch, sc)
    assert resolve_site_plan({"name": "t1", "plan_name": "Elite"}, PLAN_NAMES) is None
