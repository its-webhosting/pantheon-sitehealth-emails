"""Integration tier: the psh.gather WordPress gather core extracted from main()'s per-site
loop at campaign I9 (SPEC D-i9-2) -- wordpress_network_url (B32) and gather_wordpress (the
B34 gather core: version fetch + plugin list + add-on collection + must-use print + theme
list).

Seams: psh.gateway.run_terminus (the gateway fixture -- CLAUDE.md section "Two mock seams";
psh.gather's wp/wp_eval resolve run_terminus in psh.gateway's namespace) + sc.SiteContext.
Loop control stays in main(): these functions return their results (a WordPressGather /
a (url, smell) pair) and main() threads them into its locals per SPEC D-i9-2, preserving
the last-wins smell semantics (a later empty smell never clears an earlier one).

NOTE two deliberate divergences from SPEC section 7's predicted expectations, verbatim
behavior preserved (PD#14 -- the prediction is corrected in the task report, not the code):
through the run_terminus seam wp_eval ALWAYS returns a str (GatewayResult.output is decoded
stdout), so the "unknown" fallback and wordpress_network_url's non-str None return are
unreachable defensive branches -- a fatal fetch with empty stdout yields "" (still
notice-carrying, entry still written), not "unknown"/None.
"""
import json

import pytest

from psh.gather import gather_wordpress, wordpress_network_url

pytestmark = pytest.mark.integration

SITE = {
    "id": "test-site-id",
    "name": "its-wws-test1",
    "framework": "wordpress",
    "plan_name": "Basic",
}
LIVE = "test-site-id.live"

PLUGIN_ROWS = [
    {"name": "a-plugin", "title": "Plugin A", "status": "active", "update": "available",
     "version": "1.0", "update_version": "2.0"},
    {"name": "b-plugin", "title": "Plugin B", "status": "inactive", "update": "available",
     "version": "3.0", "update_version": "3.1"},
    {"name": "c-plugin", "title": "Plugin C", "status": "active", "update": "none",
     "version": "9.9", "update_version": ""},
]
THEME_ROWS = [
    {"name": "the-theme", "title": "The Theme", "status": "active", "update": "available",
     "version": "0.1", "update_version": "0.2"},
]

OK_VERSION = ("6.9.4", "", False)
OK_PLUGINS = (json.dumps(PLUGIN_ROWS), "", False)
OK_THEMES = (json.dumps(THEME_ROWS), "", False)


def _ctx(reset_sc):
    return reset_sc.SiteContext(dict(SITE))


def _install_fake(monkeypatch, gateway, *, version=OK_VERSION, plugins=OK_PLUGINS,
                  themes=OK_THEMES):
    """Dispatch run_terminus results by wrapper: wp_eval commands carry "eval", the two
    wp() list fetches carry "plugin" / "theme".  Each value is a (stdout, stderr, fatal)
    triple; the plugin/theme stdout is the JSON text wp() decodes."""
    calls = []

    def fake(command, input_data=None):
        calls.append(command)
        if "eval" in command:
            return version
        if "plugin" in command:
            return plugins
        assert "theme" in command
        return themes

    monkeypatch.setattr(gateway, "run_terminus", fake)
    return calls


# ── gather_wordpress ─────────────────────────────────────────────────────────────────
def test_gather_happy_path_collects_addons_in_order(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway)
    result = gather_wordpress(SITE, LIVE, _ctx(reset_sc))
    assert result.wordpress_version == "6.9.4"
    assert result.plugins == PLUGIN_ROWS      # raw list passed through for the contract
    assert [u["slug"] for u in result.add_on_updates] == ["a-plugin", "b-plugin", "the-theme"]
    assert result.add_on_updates[0] == {
        "slug": "a-plugin",
        "name": "Plugin A",
        "type": "plugin",
        "current_version": "1.0",
        "new_version": "2.0",
    }
    assert result.add_on_updates[2]["type"] == "theme"
    assert result.wp_smell == ""
    assert result.results_entry == {
        "framework": "wordpress",
        "version": "6.9.4",
        "plan_name": "Basic",
    }


def test_gather_strips_version_whitespace(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, version=("6.9.4\n", "", False))
    result = gather_wordpress(SITE, LIVE, _ctx(reset_sc))
    assert result.wordpress_version == "6.9.4"


def test_gather_version_fatal_adds_notice_and_still_writes_entry(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, version=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_wordpress(SITE, LIVE, ctx)
    assert [n["csv"] for n in ctx["notices"] if "version-check" in n["csv"]] == [
        f"{SITE['name']},wp-error,version-check,\"boom\""
    ]
    # Through the gateway a fatal eval still yields a str stdout ("" here), so the
    # verbatim-moved isinstance/"unknown" fallback does not rewrite it (see module note).
    assert result.wordpress_version == ""
    assert result.results_entry == {
        "framework": "wordpress",
        "version": "",
        "plan_name": "Basic",
    }


def test_gather_plugin_list_fatal_adds_notice_and_skips_plugin_addons(
        gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, plugins=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_wordpress(SITE, LIVE, ctx)
    # wp() appends the JSON-decode detail to the captured stderr before the notice is
    # built, so pin the prefix (the test_check_wordpress.py pattern), not the whole csv.
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE['name']},wp-error,plugin-list,\"boom")
    assert result.plugins is None             # json.loads("") failed -> None (contract value)
    # Theme add-ons are still collected; the plugin loop was skipped entirely.
    assert [u["slug"] for u in result.add_on_updates] == ["the-theme"]


def test_gather_theme_fatal_adds_notice_and_keeps_plugin_addons(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, themes=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_wordpress(SITE, LIVE, ctx)
    # The theme-list failure notice reuses the "plugin-list" csv code (moved verbatim);
    # wp() appends the JSON-decode detail to the stderr, so pin the prefix.
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE['name']},wp-error,plugin-list,\"boom")
    assert [u["slug"] for u in result.add_on_updates] == ["a-plugin", "b-plugin"]


def test_gather_smell_is_last_wins_and_empty_never_clears(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway,
                  version=("6.9.4", "version-spew", False),
                  plugins=(json.dumps(PLUGIN_ROWS), "plugin-spew", False))
    result = gather_wordpress(SITE, LIVE, _ctx(reset_sc))
    # The clean theme fetch (stderr "") must NOT clear the plugin-list smell.
    assert result.wp_smell == "plugin-spew"


def test_gather_theme_smell_wins_when_last(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway,
                  version=("6.9.4", "version-spew", False),
                  themes=(json.dumps(THEME_ROWS), "theme-spew", False))
    result = gather_wordpress(SITE, LIVE, _ctx(reset_sc))
    assert result.wp_smell == "theme-spew"


# ── wordpress_network_url ────────────────────────────────────────────────────────────
def test_network_url_happy_path_returns_stripped_url(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway,
                  version=("https://net.example.edu/\n", "", False))
    ctx = _ctx(reset_sc)
    assert wordpress_network_url(SITE, LIVE, ctx) == ("https://net.example.edu/", "")
    assert ctx["notices"] == []


def test_network_url_fatal_adds_notice_and_no_smell(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, version=("", "boom", True))
    ctx = _ctx(reset_sc)
    url, smell = wordpress_network_url(SITE, LIVE, ctx)
    assert [n["csv"] for n in ctx["notices"]] == [
        f"{SITE['name']},wp-error,version-check,\"boom\""
    ]
    # Fatal stdout is still a str ("" here) through the gateway, so the verbatim
    # isinstance guard returns it stripped -- main()'s `is not None` thread then sets
    # site_url = "", exactly today's inline behavior (see module note).
    assert (url, smell) == ("", "")


def test_network_url_stderr_becomes_smell(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway,
                  version=("https://net.example.edu/", "deprecation spew", False))
    ctx = _ctx(reset_sc)
    assert wordpress_network_url(SITE, LIVE, ctx) == (
        "https://net.example.edu/", "deprecation spew")
    assert ctx["notices"] == []
