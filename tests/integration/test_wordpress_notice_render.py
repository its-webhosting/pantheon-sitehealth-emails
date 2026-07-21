"""Syrupy pins of the check/wordpress notice bodies -- the forward byte-identity guard for
the verbatim move (campaign I9; move-time evidence is the extracted-block diff in the task
report, the I2 precedent)."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console
from psh.gather import check_wordpress_plugin

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE = "its-wws-test1"


def _ctx(reset_sc, *, plugins=None, fqdns=None):
    ctx = reset_sc.SiteContext({"name": SITE, "id": SITE_ID})
    ctx["framework"] = "wordpress"
    ctx["wordpress_plugins"] = plugins
    ctx["fqdns_not_behind_cloudflare"] = [] if fqdns is None else fqdns
    ctx["wp_smell"] = ""
    return ctx


def _fake_run_terminus(result):
    def fake(command, input_data=None):
        return result
    return fake


def test_ocp_alert_snapshot(psh, reset_sc, request, gateway, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "wordpress", "ocp", "wp_ocp_snap", request)
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus(("true", "", False)))
    ctx = _ctx(reset_sc, plugins=[{"name": "object-cache-pro", "status": "active"}])
    mod.check_ocp_config(ctx)
    assert len(ctx["notices"]) == 1
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_no_favicon_warning_snapshot(psh, reset_sc, request, gateway, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "wordpress", "favicon", "wp_favicon_snap", request)
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus(("false", "", False)))
    ctx = _ctx(reset_sc, fqdns=["www.example.com"])
    mod.check_favicon(ctx)
    assert len(ctx["notices"]) == 1
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


# ── check_wordpress_plugin builder variants (moved to psh.gather at I9, Task 4) ───────
# Pinned with the real PAPC arguments (check/wordpress/papc.py) so the snapshots are the
# bodies production renders.
PAPC_ARGS = (
    "pantheon-advanced-page-cache",
    "Pantheon Advanced Page Cache",
    "https://docs.pantheon.io/guides/wordpress-configurations/wordpress-cache-plugin",
    "Needed for automatically clearing Pantheon's caches (not Cloudflare's) when content is updated.",
)


def test_papc_builder_not_installed_snapshot(reset_sc, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    notices = check_wordpress_plugin(SITE, [], *PAPC_ARGS)
    assert [n["csv"] for n in notices] == [f"{SITE},not-installed,pantheon-advanced-page-cache"]
    assert notices[0]["type"] == "warning"
    assert notices[0]["message"] == snapshot
    assert notices[0]["text"] == snapshot
    assert notices[0]["short"] == snapshot


def test_papc_builder_multiple_installed_snapshot(reset_sc, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    plugins = [
        {"name": "pantheon-advanced-page-cache", "status": "active"},
        {"name": "pantheon-advanced-page-cache", "status": "active"},
    ]
    notices = check_wordpress_plugin(SITE, plugins, *PAPC_ARGS)
    assert [n["csv"] for n in notices] == [
        f"{SITE},multiple-installed,pantheon-advanced-page-cache"]
    assert notices[0]["type"] == "info"
    assert notices[0]["message"] == snapshot
    assert notices[0]["text"] == snapshot
    assert notices[0]["short"] == snapshot


def test_papc_builder_turned_off_snapshot(reset_sc, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    plugins = [{"name": "pantheon-advanced-page-cache", "status": "inactive"}]
    notices = check_wordpress_plugin(SITE, plugins, *PAPC_ARGS)
    assert [n["csv"] for n in notices] == [f"{SITE},turned-off,pantheon-advanced-page-cache"]
    assert notices[0]["type"] == "warning"
    assert notices[0]["message"] == snapshot
    assert notices[0]["text"] == snapshot
    assert notices[0]["short"] == snapshot


def test_papc_builder_active_plugin_returns_nothing(reset_sc):
    plugins = [{"name": "pantheon-advanced-page-cache", "status": "active"}]
    assert check_wordpress_plugin(SITE, plugins, *PAPC_ARGS) == []


def test_papc_builder_non_list_input_returns_nothing(reset_sc):
    assert check_wordpress_plugin(SITE, None, *PAPC_ARGS) == []
