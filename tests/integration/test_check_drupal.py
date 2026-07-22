"""check/drupal hook seams (campaign I10): each module loaded standalone, driven with a
real SiteContext + the gateway fixture -- the check/wordpress/check/umich test pattern.

sc.drush_php_script/sc.drush_error resolve run_terminus in psh.gateway's namespace, so the
gateway fixture (monkeypatch of psh.gateway.run_terminus) is the seam for the multisite
probe (CLAUDE.md "Two mock seams"). papc/d7_eol delegate to the real sc.check_drupal_module
(still defined in psh/_legacy.py until Task 4 -- resolves through the sc facade either
way), so they are driven with real module dicts rather than a further mock.
"""
import json

import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "its-wws-test1"
LIVE = f"{SITE_ID}.live"


def _ctx(reset_sc, *, framework="drupal9", custom_domains=None, primary_domain="",
         drupal_modules=None, drupal_version="9.5"):
    # "framework" lives in TWO places: site_context["site"]["framework"] is the raw
    # Pantheon site record, available from SiteContext construction -- what the
    # site_post_dns multisite hook reads (the site_post_gather "framework" contract
    # key does not exist yet at that phase).  site_context["framework"] is the
    # site_post_gather contract key that papc/d7_eol read.  Both are set here so one
    # fixture serves all three modules' tests.
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID, "framework": framework})
    ctx["framework"] = framework
    ctx["custom_domains"] = [] if custom_domains is None else custom_domains
    ctx["primary_domain"] = primary_domain
    ctx["drupal_modules"] = drupal_modules
    ctx["drupal_version"] = drupal_version
    return ctx


def _fake_run_terminus(output, errors="", fatal=False, record=None):
    def run_terminus(command, input_data=None):
        if record is not None:
            record["command"] = command
            record["input"] = input_data
        return (output, errors, fatal)

    return run_terminus


# ── multisite ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def multisite_mod(psh, request):
    return load_check_module(psh, "drupal", "multisite", "drupal_multisite_probe", request)


def test_single_custom_domain_makes_no_probe_call(multisite_mod, reset_sc, gateway, monkeypatch):
    record = {}
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus("{}", record=record))
    ctx = _ctx(reset_sc, custom_domains=["a.example.com"])
    multisite_mod.check_multisite(ctx)
    assert record == {}
    assert "drupal_multisite" not in ctx
    assert "drupal_multisite_smell" not in ctx


def test_primary_domain_set_makes_no_probe_call(multisite_mod, reset_sc, gateway, monkeypatch):
    record = {}
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus("{}", record=record))
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"],
               primary_domain="a.example.com")
    multisite_mod.check_multisite(ctx)
    assert record == {}
    assert "drupal_multisite" not in ctx
    assert "drupal_multisite_smell" not in ctx


def test_non_drupal_framework_makes_no_probe_call(multisite_mod, reset_sc, gateway, monkeypatch):
    record = {}
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus("{}", record=record))
    ctx = _ctx(reset_sc, framework="wordpress",
               custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert record == {}
    assert "drupal_multisite" not in ctx
    assert "drupal_multisite_smell" not in ctx


def test_probe_true_result_sets_multisite_true(multisite_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus(json.dumps({"result": True}))
    )
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert ctx["drupal_multisite"] is True
    assert ctx["drupal_multisite_smell"] == ""


def test_probe_false_result_sets_multisite_false(multisite_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus(json.dumps({"result": False}))
    )
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert ctx["drupal_multisite"] is False


def test_junk_result_sets_multisite_false(multisite_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus(json.dumps({"unexpected": "shape"}))
    )
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert ctx["drupal_multisite"] is False


def test_fatal_probe_adds_notice_and_still_produces_keys(multisite_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus("", errors="boom", fatal=True)
    )
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE_NAME},drush-error,multisite-check,")
    assert ctx["drupal_multisite"] is False
    assert ctx["drupal_multisite_smell"] == ""


def test_nonfatal_stderr_becomes_the_smell(multisite_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway,
        "run_terminus",
        _fake_run_terminus(json.dumps({"result": True}), errors="a warning"),
    )
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert ctx["drupal_multisite_smell"] == "a warning"


def test_probe_prints_unconditionally(multisite_mod, reset_sc, gateway, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus(json.dumps({"result": True}))
    )
    ctx = _ctx(reset_sc, custom_domains=["a.example.com", "b.example.com"])
    multisite_mod.check_multisite(ctx)
    assert f"{SITE_NAME} is a Drupal multisite:" in console.export_text()


# ── papc ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def papc_mod(psh, request):
    return load_check_module(psh, "drupal", "papc", "drupal_papc_probe", request)


def test_papc_missing_module_warns(papc_mod, reset_sc):
    ctx = _ctx(reset_sc, drupal_modules={})
    papc_mod.check_papc(ctx)
    assert [n["csv"] for n in ctx["notices"]] == \
        [f"{SITE_NAME},not-installed,pantheon_advanced_page_cache"]


def test_papc_enabled_module_no_notice(papc_mod, reset_sc):
    ctx = _ctx(reset_sc, drupal_modules={
        "pantheon_advanced_page_cache": {"status": "Enabled"}})
    papc_mod.check_papc(ctx)
    assert ctx["notices"] == []


def test_papc_non_drupal_framework_does_nothing(papc_mod, reset_sc):
    ctx = _ctx(reset_sc, framework="wordpress", drupal_modules={})
    papc_mod.check_papc(ctx)
    assert ctx["notices"] == []


def test_papc_none_modules_early_returns_in_builder(papc_mod, reset_sc):
    # sc.check_drupal_module's own non-dict early return handles the contract's None.
    ctx = _ctx(reset_sc, drupal_modules=None)
    papc_mod.check_papc(ctx)
    assert ctx["notices"] == []


# ── d7_eol ────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def d7_eol_mod(psh, request):
    return load_check_module(psh, "drupal", "d7_eol", "drupal_d7_eol_probe", request)


def test_drupal_7_gets_eol_alert_and_tag1_delegation(d7_eol_mod, reset_sc):
    ctx = _ctx(reset_sc, drupal_version="7.1", drupal_modules={})
    d7_eol_mod.check_d7_eol(ctx)
    codes = [n["csv"] for n in ctx["notices"]]
    assert f"{SITE_NAME},drupal7-eol" in codes
    assert f"{SITE_NAME},not-installed,tag1_d7es" in codes


def test_drupal_10_gets_nothing(d7_eol_mod, reset_sc):
    ctx = _ctx(reset_sc, drupal_version="10.2", drupal_modules={})
    d7_eol_mod.check_d7_eol(ctx)
    assert ctx["notices"] == []


def test_unknown_version_gets_nothing(d7_eol_mod, reset_sc):
    ctx = _ctx(reset_sc, drupal_version="unknown", drupal_modules={})
    d7_eol_mod.check_d7_eol(ctx)
    assert ctx["notices"] == []


def test_non_drupal_framework_does_nothing(d7_eol_mod, reset_sc):
    ctx = _ctx(reset_sc, framework="wordpress", drupal_version="7.1", drupal_modules={})
    d7_eol_mod.check_d7_eol(ctx)
    assert ctx["notices"] == []
