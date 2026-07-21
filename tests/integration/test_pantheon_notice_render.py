"""Syrupy pins of the check/pantheon notice bodies -- the forward byte-identity guard for
the verbatim move (campaign I8; move-time evidence is the extracted-block diff in the
task report, the I2 precedent)."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "bus-occb"


def _notice(reset_sc, mod_func, ctx):
    mod_func(ctx)
    assert len(ctx["notices"]) == 1
    return ctx["notices"][0]


def test_frozen_notice_snapshot(psh, reset_sc, request, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "pantheon", "frozen", "pantheon_frozen_snap", request)
    ctx = reset_sc.SiteContext({"name": SITE, "frozen": True})
    n = _notice(reset_sc, mod.check_frozen_site, ctx)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


def test_no_live_env_notice_snapshot(psh, reset_sc, request, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "pantheon", "live_env", "pantheon_live_snap", request)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx["envs"] = {"live": {"initialized": False}}
    n = _notice(reset_sc, mod.check_live_env, ctx)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
