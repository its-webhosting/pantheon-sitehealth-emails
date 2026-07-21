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


import datetime
import types


class _FrozenNow(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 1, 12, 0, tzinfo=tz)


@pytest.mark.parametrize("iso,variant", [
    ("2026-06-28T00:00:00+00:00", "info"),
    ("2026-06-15T00:00:00+00:00", "warning"),
    ("2026-05-01T00:00:00+00:00", "alert"),
])
def test_updates_notice_snapshots(psh, reset_sc, request, monkeypatch, snapshot, iso, variant):
    recording_console(monkeypatch, reset_sc)
    mod = load_check_module(psh, "pantheon", "updates", f"pantheon_upd_snap_{variant}", request)
    monkeypatch.setattr(mod, "datetime", types.SimpleNamespace(
        datetime=_FrozenNow, UTC=datetime.UTC))
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: (
        [{"datetime": iso, "message": "Update WordPress to 6.6", "author": "Pantheon"}],
        "", False))
    ctx = reset_sc.SiteContext({"name": SITE, "id": "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"})
    mod.check_upstream_updates(ctx)
    n = _notice(reset_sc, lambda c: None, ctx)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


@pytest.mark.parametrize("version,variant", [("8.1", "warning"), ("8.0", "alert")])
def test_php_eol_notice_snapshots(psh, reset_sc, request, snapshot, version, variant):
    mod = load_check_module(psh, "pantheon", "php_eol", f"pantheon_php_snap_{variant}", request)
    n = mod.build_php_eol_notice(SITE, version)
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
