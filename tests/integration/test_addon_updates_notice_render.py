"""Syrupy pins of the check/addon_updates notice body -- the forward byte-identity guard
for the verbatim B39 move (campaign I10; move-time evidence is the extracted-block diff in
the task report, the I2 precedent).  Covers a plugin/theme pair AND an audit-shaped
(D7/D8+ composer-audit) row, per SPEC section 7."""
import pytest

from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "its-wws-test1"


def _ctx(reset_sc, add_on_updates):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["add_on_updates"] = add_on_updates
    return ctx


@pytest.fixture
def table_mod(psh, request):
    return load_check_module(psh, "addon_updates", "table", "addon_updates_render_probe", request)


PLUGIN_ROW = {
    "slug": "plugin-a",
    "name": "Plugin A",
    "type": "plugin",
    "current_version": "1.0",
    "new_version": "1.1",
}
THEME_ROW = {
    "slug": "theme-b",
    "name": "Theme B",
    "type": "theme",
    "current_version": "2.0",
    "new_version": "2.1",
}
AUDIT_ROW = {
    "slug": "package-c",
    "name": [
        {"title": "Package C vulnerability", "severity": "high"},
        {"title": "Package C second finding", "severity": "moderate"},
    ],
    "type": "library",
    "current_version": "1.0",
    "new_version": "1.1",
    "new_version_url": "https://example.com/advisory",
}


def test_plugin_theme_pair_snapshot(table_mod, reset_sc, snapshot):
    ctx = _ctx(reset_sc, [PLUGIN_ROW, THEME_ROW])
    table_mod.check_add_on_updates(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
    assert n["csv"] == snapshot


def test_audit_shaped_row_snapshot(table_mod, reset_sc, snapshot):
    ctx = _ctx(reset_sc, [AUDIT_ROW])
    table_mod.check_add_on_updates(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
    assert n["csv"] == snapshot
