"""check/wordpress registration + [Check.wordpress] gating (campaign I9, SPEC D-i9-5).

Default is ENABLED: relocating code must not silently disable a check that ran
unconditionally before (CAMPAIGN.md section 5)."""
import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

EXPECTED_NAMES = [
    "check.wordpress.papc.check_papc",
    "check.wordpress.sessions.check_native_php_sessions",
    "check.wordpress.ocp.check_ocp_config",
    "check.wordpress.favicon.check_favicon",
]


def test_registers_hooks_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "wordpress", "wordpress_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_gather"]] == EXPECTED_NAMES


def test_registers_hooks_when_explicitly_enabled(psh, reset_sc, request):
    reset_sc.config = {"Check": {"wordpress": {"enabled": True}}}
    load_check_package(psh, "wordpress", "wordpress_on_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_gather"]] == EXPECTED_NAMES


def test_declarations_match_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"Check": {"wordpress": {"enabled": True}}}
    load_check_package(psh, "wordpress", "wordpress_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_post_gather"]}
    assert hooks["check.wordpress.papc.check_papc"]["consumes"] == [
        "framework", "wordpress_plugins"]
    assert hooks["check.wordpress.sessions.check_native_php_sessions"]["consumes"] == [
        "framework", "wordpress_plugins"]
    assert hooks["check.wordpress.ocp.check_ocp_config"]["consumes"] == [
        "framework", "wordpress_plugins"]
    assert hooks["check.wordpress.favicon.check_favicon"]["consumes"] == [
        "framework", "fqdns_not_behind_cloudflare"]
    assert all(h["produces"] == [] for h in hooks.values())


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"wordpress": {"enabled": False}}}
    load_check_package(psh, "wordpress", "wordpress_off_probe", request)
    assert not reset_sc.hooks.get("site_post_gather")
    assert "Skipping check.wordpress" in console.export_text()
