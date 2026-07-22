"""Syrupy pins of the check/drupal notice bodies -- the forward byte-identity guard for
the verbatim move (campaign I10; move-time evidence is the extracted-block diff in the
task report, the I2/I9 precedent).

check_drupal_module is still defined in psh/_legacy.py (moves to psh/gather.py at
Task 4) -- pinned here via the psh fixture so the snapshot is the body production
actually renders regardless of which module currently owns the def."""
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE = "its-wws-test1"

PAPC_ARGS = (
    "pantheon_advanced_page_cache",
    "Pantheon Advanced Page Cache",
    "https://www.drupal.org/project/pantheon_advanced_page_cache",
    "Necessary for automatically clearing Pantheon's caches (not Cloudflare's) when content is updated.",
)


# ── psh.check_drupal_module builder variants ─────────────────────────────────────────
def test_check_drupal_module_not_installed_snapshot(psh, reset_sc, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    notices = psh.check_drupal_module(SITE, {}, *PAPC_ARGS)
    assert [n["csv"] for n in notices] == \
        [f"{SITE},not-installed,pantheon_advanced_page_cache"]
    assert notices[0]["type"] == "warning"
    assert notices[0]["message"] == snapshot
    assert notices[0]["text"] == snapshot
    assert notices[0]["short"] == snapshot


def test_check_drupal_module_turned_off_snapshot(psh, reset_sc, monkeypatch, snapshot):
    recording_console(monkeypatch, reset_sc)
    modules = {"pantheon_advanced_page_cache": {"status": "Disabled"}}
    notices = psh.check_drupal_module(SITE, modules, *PAPC_ARGS)
    assert [n["csv"] for n in notices] == \
        [f"{SITE},turned-off,pantheon_advanced_page_cache"]
    assert notices[0]["type"] == "warning"
    assert notices[0]["message"] == snapshot
    assert notices[0]["text"] == snapshot
    assert notices[0]["short"] == snapshot


# ── drupal7-eol (check/drupal/d7_eol.py) ─────────────────────────────────────────────
def test_drupal7_eol_snapshot(psh, reset_sc, request, snapshot):
    mod = load_check_module(psh, "drupal", "d7_eol", "drupal_d7_eol_snap", request)
    ctx = reset_sc.SiteContext({"name": SITE, "id": SITE_ID})
    ctx["framework"] = "drupal7"
    ctx["drupal_version"] = "7.1"
    ctx["drupal_modules"] = {}
    mod.check_d7_eol(ctx)
    n = [n for n in ctx["notices"] if n["csv"] == f"{SITE},drupal7-eol"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


# ── multisite-check (check/drupal/multisite.py, fatal-probe path) ───────────────────
def test_multisite_check_fatal_snapshot(psh, reset_sc, request, gateway, monkeypatch, snapshot):
    mod = load_check_module(psh, "drupal", "multisite", "drupal_multisite_snap", request)
    monkeypatch.setattr(
        gateway, "run_terminus", lambda command, input_data=None: ("", "boom", True)
    )
    ctx = reset_sc.SiteContext({"name": SITE, "id": SITE_ID, "framework": "drupal9"})
    ctx["custom_domains"] = ["a.example.com", "b.example.com"]
    ctx["primary_domain"] = ""
    mod.check_multisite(ctx)
    n = ctx["notices"][0]
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot


# ── no-primary-domain (psh.no_primary_domain_notice, the D-i10-3 pure helper) ───────
def test_no_primary_domain_notice_snapshot(psh, snapshot):
    site = {"name": SITE, "id": SITE_ID, "framework": "drupal9"}
    notice = psh.no_primary_domain_notice(
        site, ["a.example.com", "b.example.com"], "", False)
    assert notice["message"] == snapshot
    assert notice["text"] == snapshot
    assert notice["short"] == snapshot
