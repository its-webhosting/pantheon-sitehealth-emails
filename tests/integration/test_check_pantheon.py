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
