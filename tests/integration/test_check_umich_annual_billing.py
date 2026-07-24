"""check/umich annual-billing hook (campaign I12, from B50; B51 deleted I14a).

The billing notice is a HOOK-PRODUCED site_context key (CAMPAIGN.md §4, the I10
drupal_multisite precedent), NOT an add_notice call: main()'s sort_notices_and_subject pins
it to the front of the *rendered* list and it never enters site_context["notices"] -- so
no -notices.csv rows, the pre-campaign behavior (SPEC I12 §2.2).  This file is the
runtime cover LEDGER I1 required for the previously-untested umich-only call sites.
"""
import datetime

import pytest
from helpers.checkload import load_check_module, load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"

CONFIG = {
    "UMich": {"enabled": True, "portal": {"sites": {
        SITE: {"shortcode": "SC123", "id": 42, "owner_group": "web team"}}}},
    "Pantheon": {"plan_info": {"Performance Small": {"cost": 500}}},
}


@pytest.fixture
def billing(psh, request):
    return load_check_module(psh, "umich", "annual_billing", "umich_billing_probe", request)


def _ctx(reset_sc, *, end_date):
    ctx = reset_sc.SiteContext({"name": SITE, "plan_name": "Performance Small"})
    ctx["end_date"] = end_date
    ctx["current_plan"] = "Performance Small"
    return ctx


def _wire_facade(psh, monkeypatch, reset_sc):
    # reset_sc does not restore runtime-exposed sc callables; monkeypatch, never assign
    # (the recorded reset_sc escape_url lesson).
    monkeypatch.setattr(reset_sc, "contract_year_end", psh.contract_year_end, raising=False)


# --- registration ------------------------------------------------------------------

def test_umich_enabled_registers_exactly_the_upcoming_hook(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_billing_reg_probe", request)
    names = [h["name"] for h in reset_sc.hooks.get("site_pre_render", [])
             if h["name"].startswith("check.umich.annual_billing.")]
    assert names == ["check.umich.annual_billing.check_annual_bill_upcoming"]


def test_billing_declarations(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_billing_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_pre_render"]}
    up = hooks["check.umich.annual_billing.check_annual_bill_upcoming"]
    assert up["consumes"] == ["end_date", "current_plan"] and up["produces"] == ["annual_bill_upcoming"]


def test_umich_disabled_registers_no_billing_hooks(psh, reset_sc, request, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"UMich": {"enabled": False}}
    load_check_package(psh, "umich", "umich_billing_reg_off_probe", request)
    assert not reset_sc.hooks.get("site_pre_render")


# --- upcoming (B50 window) ---------------------------------------------------------

@pytest.mark.parametrize(("day", "expected"), [(15, False), (16, True), (29, True), (30, False)])
def test_upcoming_produced_only_inside_contract_year_end_window(  # noqa: PLR0913 -- parametrized test; args are fixtures + parametrize values injected by name
        psh, reset_sc, billing, monkeypatch, day, expected):
    reset_sc.config = CONFIG
    _wire_facade(psh, monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, end_date=datetime.date(2026, 6, day))
    billing.check_annual_bill_upcoming(ctx)
    assert ("annual_bill_upcoming" in ctx) is expected


def test_upcoming_notice_content_comes_from_config(psh, reset_sc, billing, monkeypatch):
    reset_sc.config = CONFIG
    _wire_facade(psh, monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, end_date=datetime.date(2026, 6, 20))
    billing.check_annual_bill_upcoming(ctx)
    n = ctx["annual_bill_upcoming"]
    assert n["csv"] == f"{SITE},annual-bill,500.0,SC123"
    assert "/sites/42/plan/" in n["message"]
    assert ctx["notices"] == []          # produced key, never a notice (SPEC §2.2)
