"""check/umich Drupal user-agent check (campaign I10, from B35; U-M-gated since I10 --
D-i10-6).

Moved out of main()'s inline B35 D8+-branch region into check/umich/, now behind the
[UMich].enabled gate (the D-i9-6 precedent -- see test_check_umich_wp.py). Loaded
standalone (tests/helpers/checkload.py) and driven with a real SiteContext + the
`gateway` conftest fixture: sc.drush_php_script/sc.drush_error resolve run_terminus in
psh.gateway's namespace (CLAUDE.md "Two mock seams").
"""
import json

import pytest

from helpers.checkload import load_check_module, load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"
SITE_ID = "abc123"
COMPLIANT_UA = "Drupal (+https://drupal.org/); UMich; https://x.example.edu/"
TEMPLATE_UA = "Drupal (+https://drupal.org/); UMich; https://your-site.example.edu/"


def _ctx(reset_sc, *, framework="drupal10", drupal_version="10.1"):
    ctx = reset_sc.SiteContext({"name": SITE, "id": SITE_ID})
    ctx["framework"] = framework
    ctx["drupal_version"] = drupal_version
    return ctx


def _fake_run_terminus(output, errors="", fatal=False, record=None):
    def run_terminus(command, input_data=None):
        if record is not None:
            record["command"] = command
            record["input"] = input_data
        return (output, errors, fatal)

    return run_terminus


@pytest.fixture
def ua_mod(psh, request):
    return load_check_module(psh, "umich", "drupal_ua", "umich_drupal_ua_probe", request)


# --- gating on framework/version: no probe call at all ------------------------------


def test_non_drupal_framework_makes_no_probe_call(ua_mod, reset_sc, gateway, monkeypatch):
    record = {}
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus("{}", record=record))
    ctx = _ctx(reset_sc, framework="wordpress")
    ua_mod.check_drupal_ua(ctx)
    assert record == {}
    assert ctx["notices"] == []


def test_drupal_7_makes_no_probe_call(ua_mod, reset_sc, gateway, monkeypatch):
    record = {}
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus("{}", record=record))
    ctx = _ctx(reset_sc, drupal_version="7.4")
    ua_mod.check_drupal_ua(ctx)
    assert record == {}
    assert ctx["notices"] == []


# --- probe outcomes ------------------------------------------------------------------


def test_compliant_ua_gets_no_notice(ua_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus(json.dumps({"result": COMPLIANT_UA}))
    )
    ctx = _ctx(reset_sc)
    ua_mod.check_drupal_ua(ctx)
    assert ctx["notices"] == []


def test_template_ua_gets_the_drupal_ua_notice(ua_mod, reset_sc, gateway, monkeypatch):
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus(json.dumps({"result": TEMPLATE_UA}))
    )
    ctx = _ctx(reset_sc)
    ua_mod.check_drupal_ua(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE},drupal-ua,{TEMPLATE_UA}"]
    assert ctx["notices"][0]["type"] == "info"


def test_fatal_probe_gets_the_drupal_ua_check_notice(ua_mod, reset_sc, gateway, monkeypatch):
    # A fatal probe never parses to a dict either, so BOTH un-returning if-chains fire --
    # verbatim pre-existing behavior (no early return after the first notice), not
    # something this move changes.
    monkeypatch.setattr(
        gateway, "run_terminus", _fake_run_terminus("", errors="boom", fatal=True)
    )
    ctx = _ctx(reset_sc)
    ua_mod.check_drupal_ua(ctx)
    assert len(ctx["notices"]) == 2
    assert all(n["csv"].startswith(f"{SITE},drush-error,drupal-ua-check,") for n in ctx["notices"])
    assert all(n["type"] == "alert" for n in ctx["notices"])


def test_non_dict_result_gets_the_unexpected_result_notice(ua_mod, reset_sc, gateway, monkeypatch):
    # A well-formed JSON object (starts with "{", so the gateway's fix_drush_output does
    # not treat it as noise) whose "result" value is not a string -- reaches the
    # "Unexpected result" branch on its own, without also tripping the fatal-or-None
    # branch (the JSON-encoded-bare-string case does trip fix_drush_output's noise
    # heuristic, since it does not start with "{", and is not usable here).
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus(json.dumps({"result": 123})))
    ctx = _ctx(reset_sc)
    ua_mod.check_drupal_ua(ctx)
    assert len(ctx["notices"]) == 1
    assert "Unexpected result from drush php-script." in ctx["notices"][0]["text"]


def test_nonfatal_stderr_rebinds_drush_smell(ua_mod, reset_sc, gateway, monkeypatch):
    # D-i10-4 pin: the UA probe's non-fatal stderr rebinds site_context["drush_smell"]
    # in place -- the second sanctioned mutate-during-phase key (alongside wp_smell).
    monkeypatch.setattr(
        gateway,
        "run_terminus",
        _fake_run_terminus(json.dumps({"result": COMPLIANT_UA}), errors="a warning"),
    )
    ctx = _ctx(reset_sc)
    ctx["drush_smell"] = ""
    ua_mod.check_drupal_ua(ctx)
    assert ctx["drush_smell"] == "a warning"


# --- registration (the D-i9-6/D-i10-6 gating-change proof) --------------------------


def test_umich_enabled_registers_drupal_ua_after_hummingbird(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_drupal_ua_reg_on_probe", request)
    names = [h["name"] for h in reset_sc.hooks["site_post_gather"]]
    assert names == [
        "check.umich.cloudflare_cms.check_cloudflare_cms_integrations",
        "check.umich.oidc_login.check_oidc_login",
        "check.umich.hummingbird.check_hummingbird_fork",
        "check.umich.drupal_ua.check_drupal_ua",
    ]


def test_drupal_ua_hook_declaration_matches_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_drupal_ua_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_post_gather"]}
    h = hooks["check.umich.drupal_ua.check_drupal_ua"]
    assert h["consumes"] == ["framework", "drupal_version"]
    assert h["produces"] == []


def test_umich_disabled_registers_no_drupal_ua_check(psh, reset_sc, request, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"UMich": {"enabled": False}}
    load_check_package(psh, "umich", "umich_drupal_ua_reg_off_probe", request)
    names = [h["name"] for h in reset_sc.hooks.get("site_post_gather", [])]
    assert "check.umich.drupal_ua.check_drupal_ua" not in names
