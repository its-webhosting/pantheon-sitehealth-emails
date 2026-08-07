"""Integration tier: psh.gather.gather_framework, the framework-gather DISPATCH extracted
from main()'s per-site loop (development/2026-08-07-main-extraction/SPEC.md section 5.2 --
B33, B34 (residue), B35 (residue), B36).  It dispatches to gather_wordpress / gather_drupal
by site["framework"], or falls back to the unknown-framework results_entry (and its
ATTENTION console print, which SPEC section 5.2 keeps INSIDE the helper -- CLAUDE.md's
precedent from build_traffic_window, per the task brief).

Seams (SPEC section 6 row 2): psh.gateway.run_terminus (the gateway fixture -- CLAUDE.md
"Two mock seams") for the wp()/wp_eval()/drush() wrapper calls gather_wordpress/
gather_drupal make, PLUS psh.gather.run_terminus for gather_drupal's D8+ composer
dry-run, which calls run_terminus directly and so resolves it in psh.gather's OWN
namespace (see tests/integration/test_gather_drupal.py's docstring).  A test patching
only the gateway fixture would make REAL Terminus subprocess calls on the composer path --
_install_fake below always patches both bindings.

gather_framework touches NO RunState (CAMPAIGN.md section 3.4's parallel-ready criterion,
D8) -- main() performs the run_state.site_results write from the returned results_entry.
test_gather_framework_works_with_no_run_state_bound is the first mechanical check of that
criterion (SPEC R2.6): CAMPAIGN.md section 3.4 has stated it since I2 with nothing to make
it go red before this test existed.
"""
import json

import pytest

import psh.gather
from psh.gather import gather_framework

pytestmark = pytest.mark.integration

SITE_WP = {
    "id": "test-site-id",
    "name": "its-wws-test1",
    "framework": "wordpress",
    "plan_name": "Basic",
}
SITE_DRUPAL = {**SITE_WP, "framework": "drupal9"}
SITE_UNKNOWN = {**SITE_WP, "framework": "nodejs"}
LIVE = "test-site-id.live"

OK_VERSION = ("6.9.4", "", False)
OK_PLUGINS = (json.dumps([]), "", False)
OK_THEMES = (json.dumps([]), "", False)
CORE_STATUS_OK = (json.dumps({"drupal-version": "9.5.10"}), "", False)
PMLIST_OK = (json.dumps({}), "", False)
DRYRUN_NO_MATCH = ("nothing to upgrade\n", "", False)
AUDIT_EMPTY = (json.dumps({}), "", False)


def _ctx(reset_sc, site):
    return reset_sc.SiteContext(dict(site))


def _install_fake(monkeypatch, gateway, *, version=OK_VERSION, plugins=OK_PLUGINS,  # noqa: PLR0913 -- fake installer; keyword-only params are the distinct command-shape responses it dispatches
                   themes=OK_THEMES, core_status=CORE_STATUS_OK, pmlist=PMLIST_OK,
                   dryrun=DRYRUN_NO_MATCH, audit=AUDIT_EMPTY):
    """Dispatch run_terminus results by command shape -- see the module docstring for why
    BOTH bindings are patched."""
    responses = (
        ("core-status", core_status),
        ("pm:list", pmlist),
        ("audit", audit),
        ("eval", version),
        ("plugin", plugins),
        ("theme", themes),
    )

    def fake(command, input_data=None):
        if "update" in command and "--dry-run" in command:
            return dryrun
        for needle, response in responses:
            if needle in command:
                return response
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(gateway, "run_terminus", fake)
    # psh.gather's OWN name binding (from psh.gateway import run_terminus) is a separate
    # copy the composer dry-run resolves directly -- see the module docstring (S1).
    monkeypatch.setattr(psh.gather, "run_terminus", fake)


# ── WordPress dispatch ───────────────────────────────────────────────────────────────
def test_wordpress_framework_dispatches_to_gather_wordpress(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, version=("6.9.4", "", False))
    result = gather_framework(SITE_WP, LIVE, _ctx(reset_sc, SITE_WP))
    assert result.wordpress_version == "6.9.4"
    assert result.plugins == []
    assert result.drupal_version is None
    assert result.modules is None
    assert result.add_on_updates == []
    assert result.results_entry == {
        "framework": "wordpress",
        "version": "6.9.4",
        "plan_name": "Basic",
    }


def test_wordpress_smell_is_a_delta_not_merged(gateway, reset_sc, monkeypatch):
    # A dirty wp_eval stderr becomes the returned wp_smell verbatim; the OTHER two smell
    # fields stay "" (R2.2: gather_framework never receives -- and so cannot merge with --
    # a caller's current smell).
    _install_fake(monkeypatch, gateway, version=("6.9.4", "stderr junk", False))
    result = gather_framework(SITE_WP, LIVE, _ctx(reset_sc, SITE_WP))
    assert result.wp_smell == "stderr junk"
    assert result.drush_smell == ""
    assert result.composer_smell == ""


# ── Drupal dispatch ──────────────────────────────────────────────────────────────────
def test_drupal_framework_dispatches_to_gather_drupal(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_OK)
    result = gather_framework(SITE_DRUPAL, LIVE, _ctx(reset_sc, SITE_DRUPAL))
    assert result.drupal_version == "9.5.10"
    assert result.wordpress_version is None
    assert result.plugins is None
    assert result.modules == {}
    assert result.results_entry == {
        "framework": "drupal9",
        "version": "9.5.10",
        "plan_name": "Basic",
    }


def test_wordpress_fatal_version_fetch_still_returns_cleanly(gateway, reset_sc, monkeypatch):
    # R2.5 shadow path: a WordPress site whose version fetch was fatal.  gather_wordpress
    # already covers this at its own seam (test_gather_wordpress.py); this pins that the
    # DISPATCH threads it through unchanged -- no exception, "" version (not "unknown" --
    # unreachable through the gateway per gather_wordpress's own docstring), and the
    # wp_error notice lands on the SAME site_context gather_framework was given.
    _install_fake(monkeypatch, gateway, version=("", "boom", True))
    ctx = _ctx(reset_sc, SITE_WP)
    result = gather_framework(SITE_WP, LIVE, ctx)
    assert result.wordpress_version == ""
    assert any(
        n["csv"] == "its-wws-test1,wp-error,version-check,\"boom\"" for n in ctx["notices"]
    )


def test_drupal_fatal_pmlist_still_returns_cleanly(gateway, reset_sc, monkeypatch):
    # R2.5 shadow path: a Drupal site whose pm:list was fatal.
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_OK, pmlist=("", "boom", True))
    ctx = _ctx(reset_sc, SITE_DRUPAL)
    result = gather_framework(SITE_DRUPAL, LIVE, ctx)
    assert result.modules is None
    # fix_drush_output/json.loads("") append the decode error to "boom", so match the
    # notice's stable prefix rather than its full (parser-version-dependent) text.
    assert any(
        n["csv"].startswith("its-wws-test1,drush-error,pm-list,") for n in ctx["notices"]
    )


def test_drupal_composer_dry_run_uses_the_gather_module_binding(gateway, reset_sc, monkeypatch):
    # S1: if only the gateway fixture were patched, the direct run_terminus(command) call
    # inside gather_drupal's D8+ composer dry-run would fall through to the REAL binding
    # (a live subprocess call -- see the module docstring) instead of this fake, and the
    # composer_smell it captures would come from that live call, not from `dryrun` below.
    # Patching BOTH bindings is what makes composer_smell observable and deterministic.
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_OK,
                  dryrun=("stale-lock warning\n", "composer dry-run stderr junk", False))
    result = gather_framework(SITE_DRUPAL, LIVE, _ctx(reset_sc, SITE_DRUPAL))
    assert result.composer_smell == "composer dry-run stderr junk"


# ── Unknown framework ────────────────────────────────────────────────────────────────
def test_unknown_framework_returns_the_fallback_entry_and_prints_attention(
    gateway, reset_sc, monkeypatch
):
    calls = []
    monkeypatch.setattr(gateway, "run_terminus",
                         lambda command, input_data=None: calls.append(command) or (None, "", True))
    monkeypatch.setattr(psh.gather, "run_terminus",
                         lambda command, input_data=None: calls.append(command) or (None, "", True))
    result = gather_framework(SITE_UNKNOWN, LIVE, _ctx(reset_sc, SITE_UNKNOWN))
    assert calls == []  # unknown framework: no Terminus/WP/Drush call at all
    assert result.wordpress_version is None
    assert result.plugins is None
    assert result.drupal_version is None
    assert result.modules is None
    assert result.add_on_updates == []
    assert result.wp_smell == ""
    assert result.drush_smell == ""
    assert result.composer_smell == ""
    assert result.results_entry == {
        "framework": "nodejs",
        "version": "unknown",
        "plan_name": "Basic",
    }


def test_unknown_framework_prints_attention_to_the_console(reset_sc, monkeypatch):
    # The ATTENTION print stays INSIDE the helper (task brief, following build_traffic_window's
    # precedent) rather than moving back into main() -- assert it directly against the
    # recording console rather than trusting main() to still print it.
    from helpers.dnsfake import recording_console
    console = recording_console(monkeypatch, reset_sc, width=80)
    gather_framework(SITE_UNKNOWN, LIVE, _ctx(reset_sc, SITE_UNKNOWN))
    output = console.export_text()
    assert "unknown framework for its-wws-test1: nodejs" in output


# ── R2.4: the SAME add_on_updates list object, not a copy ──────────────────────────────
def test_add_on_updates_is_the_same_object_the_gather_returned(reset_sc, monkeypatch):
    sentinel = [{"slug": "x"}]
    fake_result = psh.gather.WordPressGather(
        wordpress_version="1.0", plugins=[], add_on_updates=sentinel, wp_smell="",
        results_entry={"framework": "wordpress", "version": "1.0", "plan_name": "Basic"},
    )
    monkeypatch.setattr(psh.gather, "gather_wordpress", lambda site, live, ctx: fake_result)
    result = gather_framework(SITE_WP, LIVE, _ctx(reset_sc, SITE_WP))
    assert result.add_on_updates is sentinel


# ── R2.6: the D8 parallel-ready mechanical check ────────────────────────────────────────
@pytest.mark.parametrize("site", [SITE_WP, SITE_DRUPAL, SITE_UNKNOWN], ids=["wordpress", "drupal", "unknown"])
def test_gather_framework_works_with_no_run_state_bound(site, gateway, reset_sc, monkeypatch):
    """CAMPAIGN.md section 3.4's parallel-ready criterion (D8): per-site work is a function
    of (site, config, db_session, site_context) and touches no RunState.  Until this test,
    that has been a review criterion with no mechanical check anywhere (SPEC R2.6).  Run
    across all three dispatch branches -- deleting sc.run_state entirely is what would
    surface an AttributeError from ANY of them, not just the one exercised."""
    import script_context as sc
    _install_fake(monkeypatch, gateway)
    monkeypatch.delattr(sc, "run_state", raising=False)
    result = gather_framework(site, LIVE, _ctx(reset_sc, site))
    assert result.results_entry["framework"] == site["framework"]
