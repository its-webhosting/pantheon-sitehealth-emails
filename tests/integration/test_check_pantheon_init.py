"""check/pantheon registration + [Check.pantheon] gating (campaign I8, SPEC D-i8-6).

Default is ENABLED: relocating code must not silently disable a check that ran
unconditionally before (CAMPAIGN.md section 5)."""
import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration


def test_registers_hooks_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "pantheon", "pantheon_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_pre"]] == [
        "check.pantheon.frozen.check_frozen_site",
        "check.pantheon.live_env.check_live_env",
    ]


def test_declarations_match_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"Check": {"pantheon": {"enabled": True}}}
    load_check_package(psh, "pantheon", "pantheon_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_pre"]}
    assert hooks["check.pantheon.frozen.check_frozen_site"]["consumes"] == []
    assert hooks["check.pantheon.live_env.check_live_env"]["consumes"] == ["envs"]
    assert all(h["produces"] == [] for h in hooks.values())


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"pantheon": {"enabled": False}}}
    load_check_package(psh, "pantheon", "pantheon_off_probe", request)
    assert not reset_sc.hooks.get("site_pre")
    assert "Skipping check.pantheon" in console.export_text()
