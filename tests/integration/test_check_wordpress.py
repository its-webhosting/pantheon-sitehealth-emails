"""check/wordpress hook seams (campaign I9): each module loaded standalone, driven with a
real SiteContext + the gateway fixture -- the check/pantheon test pattern.

sc.wp_eval/sc.wp_error resolve run_terminus in psh.gateway's namespace, so the gateway
fixture (monkeypatch of psh.gateway.run_terminus) is the seam for the OCP/favicon probes."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "its-wws-test1"
LIVE = f"{SITE_ID}.live"


def _ctx(reset_sc, *, framework="wordpress", plugins=None, fqdns=None, wp_smell=""):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["framework"] = framework
    ctx["wordpress_plugins"] = plugins
    ctx["fqdns_not_behind_cloudflare"] = [] if fqdns is None else fqdns
    ctx["wp_smell"] = wp_smell
    return ctx


def _fake_run_terminus(result):
    calls = []

    def fake(command, input_data=None):
        calls.append(command)
        return result

    fake.calls = calls
    return fake


# ── papc / sessions (delegate to sc.check_wordpress_plugin) ──────────────────────────
@pytest.fixture
def papc_mod(psh, request):
    return load_check_module(psh, "wordpress", "papc", "wp_papc_probe", request)


@pytest.fixture
def sessions_mod(psh, request):
    return load_check_module(psh, "wordpress", "sessions", "wp_sessions_probe", request)


def test_papc_missing_plugin_warns(papc_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, plugins=[])
    papc_mod.check_papc(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [
        f"{SITE_NAME},not-installed,pantheon-advanced-page-cache"]


def test_papc_active_plugin_no_notice(papc_mod, reset_sc):
    ctx = _ctx(reset_sc, plugins=[
        {"name": "pantheon-advanced-page-cache", "status": "active"}])
    papc_mod.check_papc(ctx)
    assert ctx["notices"] == []


def test_papc_non_wordpress_framework_does_nothing(papc_mod, reset_sc):
    ctx = _ctx(reset_sc, framework="drupal", plugins=[])
    papc_mod.check_papc(ctx)
    assert ctx["notices"] == []


def test_papc_none_plugins_early_returns_in_builder(papc_mod, reset_sc):
    # sc.check_wordpress_plugin's own non-list early return handles the contract's None.
    ctx = _ctx(reset_sc, plugins=None)
    papc_mod.check_papc(ctx)
    assert ctx["notices"] == []


def test_sessions_missing_plugin_warns(sessions_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, plugins=[])
    sessions_mod.check_native_php_sessions(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [
        f"{SITE_NAME},not-installed,wp-native-php-sessions"]


def test_sessions_non_wordpress_framework_does_nothing(sessions_mod, reset_sc):
    ctx = _ctx(reset_sc, framework="drupal", plugins=[])
    sessions_mod.check_native_php_sessions(ctx)
    assert ctx["notices"] == []


# ── ocp ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def ocp_mod(psh, request):
    return load_check_module(psh, "wordpress", "ocp", "wp_ocp_probe", request)


def test_ocp_no_matching_plugin_makes_no_gateway_call(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("true", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=[{"name": "akismet", "status": "active"}])
    ocp_mod.check_ocp_config(ctx)
    assert fake.calls == []
    assert ctx["notices"] == []


def test_ocp_inactive_plugin_is_not_probed(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("true", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=[{"name": "object-cache-pro", "status": "inactive"}])
    ocp_mod.check_ocp_config(ctx)
    assert fake.calls == []
    assert ctx["notices"] == []


def test_ocp_misconfigured_active_plugin_alerts(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("true", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=[{"name": "object-cache-pro", "status": "active"}])
    ocp_mod.check_ocp_config(ctx)
    assert fake.calls[0][1] == LIVE       # probed the live environment
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},ocp-config-fix-needed"]
    assert ctx["notices"][0]["type"] == "alert"


def test_ocp_correctly_configured_active_plugin_no_notice(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("false", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=[{"name": "object-cache-pro", "status": "active"}])
    ocp_mod.check_ocp_config(ctx)
    assert ctx["notices"] == []


def test_ocp_fatal_probe_adds_error_notice(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("", "boom", True))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=[{"name": "object-cache-pro", "status": "active"}])
    ocp_mod.check_ocp_config(ctx)
    assert ctx["notices"][0]["csv"].startswith(f"{SITE_NAME},wp-error,ocp-config-check")


def test_ocp_stderr_rebinds_wp_smell(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("false", "deprecation spew", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=[{"name": "object-cache-pro", "status": "active"}])
    ocp_mod.check_ocp_config(ctx)
    assert ctx["wp_smell"] == "deprecation spew"


def test_ocp_none_plugins_early_returns(ocp_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("true", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, plugins=None)
    ocp_mod.check_ocp_config(ctx)
    assert fake.calls == []
    assert ctx["notices"] == []


# ── favicon ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def favicon_mod(psh, request):
    return load_check_module(psh, "wordpress", "favicon", "wp_favicon_probe", request)


def test_favicon_absent_with_exposed_fqdns_warns(favicon_mod, reset_sc, gateway, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    fake = _fake_run_terminus(("false", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, fqdns=["www.example.com"])
    favicon_mod.check_favicon(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},no-favicon"]
    assert ctx["notices"][0]["type"] == "warning"


def test_favicon_present_no_notice(favicon_mod, reset_sc, gateway, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    fake = _fake_run_terminus(("true", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, fqdns=["www.example.com"])
    favicon_mod.check_favicon(ctx)
    assert ctx["notices"] == []


def test_favicon_absent_but_all_behind_cloudflare_no_notice(favicon_mod, reset_sc, gateway, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    fake = _fake_run_terminus(("false", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, fqdns=[])
    favicon_mod.check_favicon(ctx)
    assert ctx["notices"] == []


def test_favicon_fatal_probe_adds_error_notice(favicon_mod, reset_sc, gateway, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    fake = _fake_run_terminus(("", "boom", True))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, fqdns=["www.example.com"])
    favicon_mod.check_favicon(ctx)
    assert ctx["notices"][0]["csv"].startswith(f"{SITE_NAME},wp-error,favicon-check")


def test_favicon_non_wordpress_makes_no_call(favicon_mod, reset_sc, gateway, monkeypatch):
    fake = _fake_run_terminus(("false", "", False))
    monkeypatch.setattr(gateway, "run_terminus", fake)
    ctx = _ctx(reset_sc, framework="drupal", fqdns=["www.example.com"])
    favicon_mod.check_favicon(ctx)
    assert fake.calls == []
    assert ctx["notices"] == []


# ── D-i9-4 precedence pin ─────────────────────────────────────────────────────────────
def test_ocp_stderr_beats_earlier_theme_smell_when_favicon_clean(
        ocp_mod, favicon_mod, reset_sc, gateway, monkeypatch):
    """SPEC D-i9-4 (CAMPAIGN.md section 8 amendment): after the split the wp_smell order is
    version -> plugins -> themes (gather) -> OCP -> favicon (hooks).  When the theme-list
    stderr is already stuffed and the OCP probe also emits stderr while favicon is clean,
    the FINAL site_context["wp_smell"] is OCP's -- the deliberate new precedence.  Before I9
    the theme-list value won (OCP ran before themes inline)."""
    recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc,
               plugins=[{"name": "object-cache-pro", "status": "active"}],
               fqdns=["www.example.com"],
               wp_smell="theme-stderr")               # as stuffed by main() from the theme fetch
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus(("false", "ocp-stderr", False)))
    ocp_mod.check_ocp_config(ctx)
    monkeypatch.setattr(gateway, "run_terminus", _fake_run_terminus(("true", "", False)))
    favicon_mod.check_favicon(ctx)
    assert ctx["wp_smell"] == "ocp-stderr"
