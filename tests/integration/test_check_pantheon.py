"""check/pantheon hook seams (campaign I8): each module loaded standalone, driven with a
real SiteContext -- the check/pantheon_cdn_change test pattern."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "bus-occb"


def _ctx(reset_sc, **site_extra):
    return reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID, **site_extra})


@pytest.fixture
def frozen_mod(psh, request):
    return load_check_module(psh, "pantheon", "frozen", "pantheon_frozen_probe", request)


@pytest.fixture
def live_env_mod(psh, request):
    return load_check_module(psh, "pantheon", "live_env", "pantheon_live_probe", request)


def test_frozen_site_gets_the_alert(frozen_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, frozen=True)
    frozen_mod.check_frozen_site(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},frozen"]
    assert ctx["notices"][0]["type"] == "alert"
    assert "is frozen!" in console.export_text()


def test_unfrozen_site_gets_nothing(frozen_mod, reset_sc):
    ctx = _ctx(reset_sc, frozen=False)
    frozen_mod.check_frozen_site(ctx)
    assert ctx["notices"] == []


def test_uninitialized_live_env_gets_the_alert(live_env_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": False}}
    live_env_mod.check_live_env(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},no-live-env-but-paid-plan"]
    assert ctx["notices"][0]["type"] == "alert"
    assert "live environment is not initialized" in console.export_text()


def test_initialized_live_env_gets_nothing(live_env_mod, reset_sc):
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True, "php_version": "8.2"}}
    live_env_mod.check_live_env(ctx)
    assert ctx["notices"] == []


import datetime


def _update(days_ago, now):
    dt = now - datetime.timedelta(days=days_ago)
    return {"datetime": dt.isoformat(), "message": "Update WordPress to 6.6",
            "author": "Pantheon"}


@pytest.fixture
def updates_mod(psh, request):
    return load_check_module(psh, "pantheon", "updates", "pantheon_updates_probe", request)


@pytest.fixture
def php_eol_mod(psh, request):
    return load_check_module(psh, "pantheon", "php_eol", "pantheon_phpeol_probe", request)


def test_no_updates_no_notice(updates_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: ([], "", False))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert ctx["notices"] == []


def test_fetches_the_live_environment_of_the_site_id(updates_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    calls = []
    monkeypatch.setattr(reset_sc, "terminus",
                        lambda *a: (calls.append(a), ([], "", False))[1])
    updates_mod.check_upstream_updates(_ctx(reset_sc))
    assert calls == [("upstream:updates:list", f"{SITE_ID}.live")]


@pytest.mark.parametrize("days_ago,code,severity", [
    (4, "updates-info", "info"),
    (20, "updates-warning", "warning"),
    (45, "updates-alert", "alert"),
])
def test_age_tiers(updates_mod, reset_sc, monkeypatch, days_ago, code, severity):
    recording_console(monkeypatch, reset_sc)
    now = datetime.datetime.now(datetime.UTC)
    data = [_update(days_ago, now), _update(2, now)]   # the OLDEST update sets the tier
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: (data, "", False))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},{code},2,{days_ago}"]
    assert ctx["notices"][0]["type"] == severity


def test_single_old_update_short_is_interpolated(updates_mod, reset_sc, monkeypatch):
    # RED on the verbatim-moved body (D-i8-5): the alert branch's singular arm lacked
    # its f-prefix and rendered the literal "{oldest_update_days} days old".
    recording_console(monkeypatch, reset_sc)
    now = datetime.datetime.now(datetime.UTC)
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: ([_update(45, now)], "", False))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert ctx["notices"][0]["short"] == "needs maintenance: 1 Pantheon update, 45 days old"


def test_unfetchable_updates_prints_error_and_adds_nothing(updates_mod, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(reset_sc, "terminus", lambda *a: (None, "boom", True))
    ctx = _ctx(reset_sc)
    updates_mod.check_upstream_updates(ctx)
    assert ctx["notices"] == []
    assert "unable to check updates" in console.export_text()


def test_eol_php_adds_the_warning(php_eol_mod, reset_sc):
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True, "php_version": "8.1"}}
    php_eol_mod.check_php_eol(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},php-eol-warning"]


def test_current_php_adds_nothing(php_eol_mod, reset_sc):
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True, "php_version": "8.2"}}
    php_eol_mod.check_php_eol(ctx)
    assert ctx["notices"] == []


def test_missing_php_version_adds_nothing_and_does_not_raise(php_eol_mod, reset_sc):
    # RED against the old call-site semantics (D-i8-4.2): envs["live"]["php_version"]
    # was an unguarded KeyError that aborted the whole run as "fatal".
    ctx = _ctx(reset_sc)
    ctx["envs"] = {"live": {"initialized": True}}
    php_eol_mod.check_php_eol(ctx)
    assert ctx["notices"] == []
