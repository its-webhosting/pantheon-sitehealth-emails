"""check/drupal registration + [Check.drupal] gating (campaign I10, SPEC D-i10-5).

Default is ENABLED: relocating code must not silently disable a check that ran
unconditionally before (CAMPAIGN.md section 5) -- the D-i8-6/D-i9-5 shape."""
import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

EXPECTED_DNS_NAMES = ["check.drupal.multisite.check_multisite"]
EXPECTED_GATHER_NAMES = [
    "check.drupal.papc.check_papc",
    "check.drupal.d7_eol.check_d7_eol",
]


def test_registers_hooks_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "drupal", "drupal_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_dns"]] == EXPECTED_DNS_NAMES
    assert [h["name"] for h in reset_sc.hooks["site_post_gather"]] == EXPECTED_GATHER_NAMES


def test_registers_hooks_when_explicitly_enabled(psh, reset_sc, request):
    reset_sc.config = {"Check": {"drupal": {"enabled": True}}}
    load_check_package(psh, "drupal", "drupal_on_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_dns"]] == EXPECTED_DNS_NAMES
    assert [h["name"] for h in reset_sc.hooks["site_post_gather"]] == EXPECTED_GATHER_NAMES


def test_declarations_match_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"Check": {"drupal": {"enabled": True}}}
    load_check_package(psh, "drupal", "drupal_decl_probe", request)
    dns_hooks = {h["name"]: h for h in reset_sc.hooks["site_post_dns"]}
    gather_hooks = {h["name"]: h for h in reset_sc.hooks["site_post_gather"]}
    multisite = dns_hooks["check.drupal.multisite.check_multisite"]
    assert multisite["consumes"] == ["custom_domains", "primary_domain"]
    assert multisite["produces"] == ["drupal_multisite", "drupal_multisite_smell"]
    papc = gather_hooks["check.drupal.papc.check_papc"]
    assert papc["consumes"] == ["framework", "drupal_modules"]
    assert papc["produces"] == []
    d7_eol = gather_hooks["check.drupal.d7_eol.check_d7_eol"]
    assert d7_eol["consumes"] == ["framework", "drupal_version", "drupal_modules"]
    assert d7_eol["produces"] == []


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"drupal": {"enabled": False}}}
    load_check_package(psh, "drupal", "drupal_off_probe", request)
    assert not reset_sc.hooks.get("site_post_dns")
    assert not reset_sc.hooks.get("site_post_gather")
    assert "Skipping check.drupal" in console.export_text()
