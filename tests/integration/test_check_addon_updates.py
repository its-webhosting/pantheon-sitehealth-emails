"""check/addon_updates.table hook seam (campaign I10, SPEC D-i10-5/D-i10-12): the B39
add-on updates table notice as a site_post_gather hook.  Reads site_context["add_on_updates"]
-- the SAME list object the I9 stuffer publishes (test_contract_registry.py pins the
stuffer side; here we pin that the hook reads live, not a snapshot)."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "its-wws-test1"


def _ctx(reset_sc, add_on_updates):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["add_on_updates"] = add_on_updates
    return ctx


@pytest.fixture
def table_mod(psh, request):
    return load_check_module(psh, "addon_updates", "table", "addon_updates_table_probe", request)


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
    "new_version_url": "https://example.com/advisory?id=1&x=2",
}


def test_empty_list_no_notice_no_print(table_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, [])
    table_mod.check_add_on_updates(ctx)
    assert ctx["notices"] == []
    assert console.export_text() == ""


def test_plugin_and_theme_rows_emit_warning_with_csv_and_plural_short(table_mod, reset_sc):
    ctx = _ctx(reset_sc, [PLUGIN_ROW, THEME_ROW])
    table_mod.check_add_on_updates(ctx)
    assert len(ctx["notices"]) == 1
    n = ctx["notices"][0]
    assert n["type"] == "warning"
    assert n["csv"] == f"{SITE_NAME},updates-addons,2"
    assert n["short"] == "2 pending add-on updates"
    assert '<div class="rt-data rt-plan">Plugin A</div>' in n["message"]
    assert '<div class="rt-data rt-plan">Theme B</div>' in n["message"]


def test_single_row_gets_singular_short(table_mod, reset_sc):
    ctx = _ctx(reset_sc, [PLUGIN_ROW])
    table_mod.check_add_on_updates(ctx)
    n = ctx["notices"][0]
    assert n["csv"] == f"{SITE_NAME},updates-addons,1"
    assert n["short"] == "1 pending add-on update"


def test_row_backgrounds_alternate(table_mod, reset_sc):
    ctx = _ctx(reset_sc, [PLUGIN_ROW, THEME_ROW, AUDIT_ROW])
    table_mod.check_add_on_updates(ctx)
    message = ctx["notices"][0]["message"]
    first = message.index('background-color: #fff;')
    second = message.index('background-color: #CCCFCA;')
    third = message.index('background-color: #fff;', first + 1)
    assert first < second < third


def test_audit_shaped_row_joins_list_name_and_links_new_version_url(table_mod, reset_sc):
    ctx = _ctx(reset_sc, [AUDIT_ROW])
    table_mod.check_add_on_updates(ctx)
    message = ctx["notices"][0]["message"]
    assert "Package C vulnerability, (HIGH)" in message
    assert "Package C second finding, (MODERATE)" in message
    assert '<a href="https://example.com/advisory?id=1&x=2">1.1</a>' in message


def test_same_object_read_reflects_mutation_after_stuffing(table_mod, reset_sc):
    """The stuffer publishes the SAME list main() accumulated (I9); mutating it after
    stuffing but before the hook runs must show up in the table -- proves the hook
    reads site_context["add_on_updates"] live, not a snapshot taken at construction."""
    addons = [PLUGIN_ROW]
    ctx = _ctx(reset_sc, addons)
    addons.append(THEME_ROW)  # mutate the SAME object post-stuffing, pre-invocation
    table_mod.check_add_on_updates(ctx)
    n = ctx["notices"][0]
    assert n["csv"] == f"{SITE_NAME},updates-addons,2"
    assert '<div class="rt-data rt-plan">Theme B</div>' in n["message"]


def test_verbose_preamble_prints_via_recording_console(table_mod, reset_sc, psh, monkeypatch, capsys):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.options = psh.parse_args(["--date", "2026-03-31", "-vvv"])
    ctx = _ctx(reset_sc, [PLUGIN_ROW])
    table_mod.check_add_on_updates(ctx)
    # sc.console.print() (banner) goes through the recording_console seam.
    assert f"Add-on updates for {SITE_NAME}" in console.export_text()
    # pprint() (the verbose dump) always builds its own bare Console (the I8
    # check/pantheon/updates.py precedent) and so writes to real stdout, not
    # sc.console -- capsys is the seam for that half.
    assert "plugin-a" in capsys.readouterr().out
