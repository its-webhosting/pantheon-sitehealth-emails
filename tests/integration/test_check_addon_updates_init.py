"""check/addon_updates registration + [Check.addon_updates] gating (campaign I10, SPEC
D-i10-5).

Default is ENABLED: relocating code must not silently disable a notice that rendered
unconditionally before (CAMPAIGN.md section 5) -- the D-i8-6/D-i9-5/D-i10-5 shape."""
import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

EXPECTED_GATHER_NAMES = ["check.addon_updates.table.check_add_on_updates"]


def test_registers_hook_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "addon_updates", "addon_updates_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_gather"]] == EXPECTED_GATHER_NAMES


def test_registers_hook_when_explicitly_enabled(psh, reset_sc, request):
    reset_sc.config = {"Check": {"addon_updates": {"enabled": True}}}
    load_check_package(psh, "addon_updates", "addon_updates_on_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_gather"]] == EXPECTED_GATHER_NAMES


def test_declarations_match_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"Check": {"addon_updates": {"enabled": True}}}
    load_check_package(psh, "addon_updates", "addon_updates_decl_probe", request)
    gather_hooks = {h["name"]: h for h in reset_sc.hooks["site_post_gather"]}
    table = gather_hooks["check.addon_updates.table.check_add_on_updates"]
    assert table["consumes"] == ["add_on_updates"]
    assert table["produces"] == []


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"addon_updates": {"enabled": False}}}
    load_check_package(psh, "addon_updates", "addon_updates_off_probe", request)
    assert not reset_sc.hooks.get("site_post_gather")
    assert "Skipping check.addon_updates" in console.export_text()
