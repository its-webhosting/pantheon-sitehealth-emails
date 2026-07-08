"""Integration tests for check/umich/cloudflare_cms.py (the relocated U-M Cloudflare
CMS-integration checks, now a site_post_gather hook).

The module reads the site_post_dns/site_post_gather data-contract keys from the
SiteContext and calls the sc-exposed helpers (sc.check_wordpress_plugin /
sc.check_drupal_module); the tests install recorders on sc to observe the calls.
"""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"


@pytest.fixture
def cms(psh):
    path = Path(psh.__file__).parent / "check" / "umich" / "cloudflare_cms.py"
    loader = SourceFileLoader("umich_cloudflare_cms_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def recorders(reset_sc, monkeypatch):
    sc = reset_sc
    calls = {"wp": [], "drupal": []}
    monkeypatch.setattr(
        sc, "check_wordpress_plugin",
        lambda site, plugins, name, *a, **k: calls["wp"].append(name) or [],
        raising=False)
    monkeypatch.setattr(
        sc, "check_drupal_module",
        lambda site, mods, name, *a, **k: calls["drupal"].append(name) or [],
        raising=False)
    return calls


def _ctx(reset_sc, *, framework, fqdns, plugins=None, mods=None, drupal_version=None):
    ctx = reset_sc.SiteContext({"name": SITE, "framework": framework})
    ctx["framework"] = framework
    ctx["fqdns_behind_cloudflare"] = fqdns
    ctx["wordpress_plugins"] = plugins
    ctx["drupal_modules"] = mods
    ctx["drupal_version"] = drupal_version
    return ctx


def test_wordpress_with_plugins_checks_umich_cloudflare(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="wordpress", fqdns=["www.example.edu"],
               plugins=[{"name": "akismet"}])
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["wp"] == ["umich-cloudflare"]
    assert recorders["drupal"] == []


def test_empty_fqdns_is_a_noop(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="wordpress", fqdns=[], plugins=[{"name": "x"}])
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["wp"] == [] and recorders["drupal"] == []


def test_wordpress_gather_failure_is_a_noop(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="wordpress", fqdns=["www.example.edu"], plugins=None)
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["wp"] == []


def test_drupal_runs_all_four_module_checks_in_order(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="drupal10", fqdns=["www.example.edu"],
               mods={"views": {"status": "Enabled"}}, drupal_version="10.2.1")
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["drupal"] == [
        "cloudflare", "cloudflarepurger", "purge_processor_lateruntime", "purge_processor_cron"]
    assert recorders["wp"] == []


def test_drupal7_d7es_is_skipped(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="drupal", fqdns=["www.example.edu"],
               mods={"views": {"status": "Enabled"}}, drupal_version="7.99")
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["drupal"] == []


def test_drupal_gather_failure_is_a_noop(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="drupal10", fqdns=["www.example.edu"],
               mods=None, drupal_version="10.2.1")
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["drupal"] == []


def test_unknown_framework_is_a_noop(cms, reset_sc, recorders):
    ctx = _ctx(reset_sc, framework="unknown", fqdns=["www.example.edu"])
    cms.check_cloudflare_cms_integrations(ctx)
    assert recorders["wp"] == [] and recorders["drupal"] == []


def test_notices_from_helpers_reach_the_site_context(cms, reset_sc, monkeypatch):
    sc = reset_sc
    notice = {"type": "warning", "message": "<p>x</p>", "csv": f"{SITE},not-installed,umich-cloudflare"}
    monkeypatch.setattr(sc, "check_wordpress_plugin",
                        lambda *a, **k: [dict(notice)], raising=False)
    ctx = _ctx(sc, framework="wordpress", fqdns=["www.example.edu"], plugins=[])
    cms.check_cloudflare_cms_integrations(ctx)
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE},not-installed")


def test_real_drupal_helper_accepts_the_dict_shape_end_to_end(cms, psh, reset_sc):
    """Regression (code review): drush pm:list returns a DICT keyed by module name, and
    main() must stuff it as-is (isinstance(mods, dict)).  This test uses the REAL
    sc.check_drupal_module (exposed by the main script) so a list-shaped fixture -- the
    mistake that masked the original bug -- would silently produce zero notices here."""
    ctx = _ctx(reset_sc, framework="drupal10", fqdns=["www.example.edu"],
               mods={"views": {"status": "Enabled"}}, drupal_version="10.2.1")
    cms.check_cloudflare_cms_integrations(ctx)
    # None of the four U-M Cloudflare modules are installed -> four notices
    # (3 warning + 1 info for purge_processor_cron), all "not-installed".
    assert len(ctx["notices"]) == 4
    assert all(",not-installed," in n["csv"] for n in ctx["notices"])
    assert sorted(n["type"] for n in ctx["notices"]) == ["info", "warning", "warning", "warning"]
