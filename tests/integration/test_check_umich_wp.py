"""check/umich WordPress-plugin hook seams + registration (campaign I9, from B34).

The umich-oidc-login reinstall check and the UMich Hummingbird fork check moved out of
main()'s inline B34 region into check/umich/, now behind the [UMich].enabled gate
(D-i9-6, a deliberate gating change).  Each module is loaded standalone and driven with a
real SiteContext -- the check/pantheon test pattern.
"""
import pytest

from helpers.checkload import load_check_module, load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"


def _ctx(reset_sc, *, framework="wordpress", plugins):
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx["framework"] = framework
    ctx["wordpress_plugins"] = plugins
    return ctx


# --- registration (the D-i9-6 gating-change proof) ---------------------------------


def test_umich_enabled_registers_both_wp_checks_after_cloudflare_cms(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_wp_reg_on_probe", request)
    names = [h["name"] for h in reset_sc.hooks["site_post_gather"]]
    # campaign I10 registers check.umich.drupal_ua after hummingbird (D-i10-6) --
    # see tests/integration/test_check_umich_drupal_ua.py for its own registration pin.
    assert names == [
        "check.umich.cloudflare_cms.check_cloudflare_cms_integrations",
        "check.umich.oidc_login.check_oidc_login",
        "check.umich.hummingbird.check_hummingbird_fork",
        "check.umich.drupal_ua.check_drupal_ua",
    ]


def test_wp_check_declarations_match_the_spec_table(psh, reset_sc, request):
    reset_sc.config = {"UMich": {"enabled": True}}
    load_check_package(psh, "umich", "umich_wp_decl_probe", request)
    hooks = {h["name"]: h for h in reset_sc.hooks["site_post_gather"]}
    for name in ("check.umich.oidc_login.check_oidc_login",
                 "check.umich.hummingbird.check_hummingbird_fork"):
        assert hooks[name]["consumes"] == ["framework", "wordpress_plugins"]
        assert hooks[name]["produces"] == []


def test_umich_disabled_registers_neither_wp_check(psh, reset_sc, request, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"UMich": {"enabled": False}}
    load_check_package(psh, "umich", "umich_wp_reg_off_probe", request)
    names = [h["name"] for h in reset_sc.hooks.get("site_post_gather", [])]
    assert "check.umich.oidc_login.check_oidc_login" not in names
    assert "check.umich.hummingbird.check_hummingbird_fork" not in names


# --- oidc_login seam ---------------------------------------------------------------


@pytest.fixture
def oidc_mod(psh, request):
    return load_check_module(psh, "umich", "oidc_login", "umich_oidc_probe", request)


def _plugin(name, *, status="active", version="1.2.0"):
    return {"name": name, "status": status, "version": version,
            "update": "none", "update_version": "", "title": name}


def test_oidc_active_old_version_gets_the_reinstall_warning(oidc_mod, reset_sc):
    ctx = _ctx(reset_sc, plugins=[_plugin("umich-oidc-login", version="1.2.99")])
    oidc_mod.check_oidc_login(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE},umich-oidc-login-reinstall"]
    assert ctx["notices"][0]["type"] == "warning"


def test_oidc_current_version_gets_nothing(oidc_mod, reset_sc):
    ctx = _ctx(reset_sc, plugins=[_plugin("umich-oidc-login", version="1.3.0")])
    oidc_mod.check_oidc_login(ctx)
    assert ctx["notices"] == []


def test_oidc_inactive_gets_nothing(oidc_mod, reset_sc):
    ctx = _ctx(reset_sc, plugins=[_plugin("umich-oidc-login", status="inactive", version="1.2.0")])
    oidc_mod.check_oidc_login(ctx)
    assert ctx["notices"] == []


def test_oidc_none_plugins_gets_nothing(oidc_mod, reset_sc):
    ctx = _ctx(reset_sc, plugins=None)
    oidc_mod.check_oidc_login(ctx)
    assert ctx["notices"] == []


def test_oidc_non_wordpress_framework_gets_nothing(oidc_mod, reset_sc):
    ctx = _ctx(reset_sc, framework="drupal10",
               plugins=[_plugin("umich-oidc-login", version="1.2.0")])
    oidc_mod.check_oidc_login(ctx)
    assert ctx["notices"] == []


# --- hummingbird seam --------------------------------------------------------------


@pytest.fixture
def hb_mod(psh, request):
    return load_check_module(psh, "umich", "hummingbird", "umich_hb_probe", request)


def test_hummingbird_active_umich_fork_gets_the_alert(hb_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, plugins=[_plugin("hummingbird-performance", version="3.1.0-umich")])
    hb_mod.check_hummingbird_fork(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [
        f"{SITE},unsupported,hummingbird-performance"]
    assert ctx["notices"][0]["type"] == "alert"


def test_hummingbird_inactive_umich_fork_gets_the_info(hb_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, plugins=[
        _plugin("hummingbird-performance", status="inactive", version="3.1.0-umich")])
    hb_mod.check_hummingbird_fork(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [
        f"{SITE},unsupported-turned-off,hummingbird-performance"]
    assert ctx["notices"][0]["type"] == "info"


def test_hummingbird_upstream_version_gets_nothing(hb_mod, reset_sc, monkeypatch):
    recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, plugins=[_plugin("hummingbird-performance", version="3.1.0")])
    hb_mod.check_hummingbird_fork(ctx)
    assert ctx["notices"] == []


def test_hummingbird_attention_line_prints_site_name_not_the_dict(hb_mod, reset_sc, monkeypatch):
    # D-i9-10 pin: the ATTENTION console print interpolated the whole site dict; the moved
    # hummingbird.py uses site['name'].
    console = recording_console(monkeypatch, reset_sc)
    ctx = _ctx(reset_sc, plugins=[_plugin("hummingbird-performance", version="3.1.0-umich")])
    hb_mod.check_hummingbird_fork(ctx)
    text = console.export_text()
    assert SITE in text
    assert "{'name':" not in text


def test_hummingbird_non_wordpress_framework_gets_nothing(hb_mod, reset_sc):
    ctx = _ctx(reset_sc, framework="drupal10",
               plugins=[_plugin("hummingbird-performance", version="3.1.0-umich")])
    hb_mod.check_hummingbird_fork(ctx)
    assert ctx["notices"] == []
