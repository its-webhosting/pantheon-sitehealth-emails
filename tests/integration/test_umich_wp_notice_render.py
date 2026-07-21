"""Syrupy pins of the relocated check/umich WordPress-plugin notice bodies -- the forward
byte-identity guard for the verbatim move (campaign I9; move-time evidence is the
extracted-block diff in the task report, the I2 precedent)."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"


def _ctx(reset_sc, *, plugins):
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx["framework"] = "wordpress"
    ctx["wordpress_plugins"] = plugins
    return ctx


def _plugin(name, *, status="active", version="1.2.0"):
    return {"name": name, "status": status, "version": version,
            "update": "none", "update_version": "", "title": name}


def test_oidc_reinstall_notice_snapshot(psh, reset_sc, request, snapshot):
    mod = load_check_module(psh, "umich", "oidc_login", "umich_oidc_snap", request)
    ctx = _ctx(reset_sc, plugins=[_plugin("umich-oidc-login", version="1.2.0")])
    mod.check_oidc_login(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_hummingbird_alert_notice_snapshot(psh, reset_sc, request, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "umich", "hummingbird", "umich_hb_alert_snap", request)
    ctx = _ctx(reset_sc, plugins=[_plugin("hummingbird-performance", version="3.1.0-umich")])
    mod.check_hummingbird_fork(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_hummingbird_info_notice_snapshot(psh, reset_sc, request, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "umich", "hummingbird", "umich_hb_info_snap", request)
    ctx = _ctx(reset_sc, plugins=[
        _plugin("hummingbird-performance", status="inactive", version="3.1.0-umich")])
    mod.check_hummingbird_fork(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
