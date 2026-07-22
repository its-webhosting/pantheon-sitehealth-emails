"""Integration tier: the psh.gather Drupal gather core extracted from main()'s per-site
loop at campaign I10 (SPEC D-i10-2) -- gather_drupal (the B35 gather core: core-status
version fetch, pm:list module fetch, D7 pm:updatestatus add-on collection OR D8+ composer
dry-run + composer-audit add-on collection, the results_entry for site_results).

Seams: psh.gateway.run_terminus (the gateway fixture -- CLAUDE.md "Two mock seams") for
the drush()/terminus() calls, which resolve run_terminus in psh.gateway's own namespace;
PLUS psh.gather.run_terminus for the composer dry-run's DIRECT `run_terminus(command)`
call (SPEC D-i10-2 -- dry-run output is composer's human-readable text, not JSON, so it
cannot go through the JSON-decoding terminus() wrapper).  `from psh.gateway import
run_terminus` in psh/gather.py (SPEC-mandated import shape) binds a SEPARATE name in
psh.gather's own namespace at import time, so monkeypatching psh.gateway.run_terminus
alone does not intercept that direct call (the same "two mock seams" gotcha CLAUDE.md
documents for wrappers, discovered here to also apply to a direct in-module call) --
_install_fake below patches BOTH bindings to the same fake dispatcher.

D-i10-7 pin: this file is also the RED/GREEN vehicle for the named `type in u` fix (the
`test_d7_type_field_uses_dict_value_not_builtin` test below is run once against the OLD
verbatim expression -- captured RED in the task report -- then again after the one-token
fix, captured GREEN)."""
import json

import pytest

import psh.gather
from helpers.dnsfake import recording_console
from psh.gather import gather_drupal

pytestmark = pytest.mark.integration

SITE_D8 = {
    "id": "test-site-id",
    "name": "its-wws-test1",
    "framework": "drupal9",
    "plan_name": "Basic",
}
SITE_D7 = {**SITE_D8, "framework": "drupal7"}
LIVE = "test-site-id.live"

CORE_STATUS_D8_OK = (json.dumps({"drupal-version": "9.5.10"}), "", False)
CORE_STATUS_D7_OK = (json.dumps({"drupal-version": "7.4"}), "", False)
PMLIST_OK = (json.dumps({"pantheon_advanced_page_cache": {"status": "Enabled"}}), "", False)
DRYRUN_NO_MATCH = ("nothing to upgrade\n", "", False)
AUDIT_EMPTY = (json.dumps({}), "", False)


def _ctx(reset_sc):
    return reset_sc.SiteContext({"name": "its-wws-test1"})


def _install_fake(monkeypatch, gateway, *, core_status, pmlist=PMLIST_OK,
                   updatestatus=None, dryrun=DRYRUN_NO_MATCH, audit=AUDIT_EMPTY):
    """Dispatch run_terminus results by command shape: drush()/terminus() wrappers append
    --format=json, the composer dry-run call goes through bare run_terminus()."""
    def fake(command, input_data=None):
        if "core-status" in command:
            return core_status
        if "pm:updatestatus" in command:
            return updatestatus
        if "pm:list" in command:
            return pmlist
        if "audit" in command:
            return audit
        if "update" in command and "--dry-run" in command:
            return dryrun
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(gateway, "run_terminus", fake)
    # psh.gather's OWN name binding (from psh.gateway import run_terminus) is a separate
    # copy -- the direct composer dry-run call resolves it there, not in gateway's
    # namespace (see the module docstring).
    monkeypatch.setattr(psh.gather, "run_terminus", fake)


# ── D8+ happy path (composer dry-run + audit) ───────────────────────────────────────
def test_d8_version_and_modules_passthrough(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK)
    result = gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    assert result.drupal_version == "9.5.10"
    assert result.modules == {"pantheon_advanced_page_cache": {"status": "Enabled"}}
    assert result.results_entry == {
        "framework": "drupal9",
        "version": "9.5.10",
        "plan_name": "Basic",
    }


def test_d8_dry_run_parse_feeds_audit_current_and_new_version(gateway, reset_sc, monkeypatch):
    dryrun = ("- Upgrading drupal/admin_toolbar (3.4.2 => 3.5.3)\n", "", False)
    audit = (json.dumps({
        "advisories": {
            "drupal/admin_toolbar": {
                "GHSA-1": {
                    "title": "Some advisory title",
                    "severity": "moderate",
                    "link": "https://example.com/adv1",
                },
            },
        },
    }), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK, dryrun=dryrun, audit=audit)
    result = gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    (row,) = result.add_on_updates
    assert row["slug"] == "drupal/admin_toolbar"
    assert row["current_version"] == "3.4.2"
    assert row["new_version"] == "3.5.3"
    assert row["type"] == "package"
    assert "new_version_url" not in row
    assert row["name"] == [
        {"title": '<a href="https://example.com/adv1">Some advisory title</a>', "severity": "moderate"}
    ]


def test_d8_audit_severity_from_title_split(gateway, reset_sc, monkeypatch):
    # advisory["severity"] falsy + a 4-part " - " title -> severity comes from the title,
    # and the severity segment is stripped back out of the rendered title.
    audit = (json.dumps({
        "advisories": {
            "drupal/foo": {
                "GHSA-2": {
                    "title": "SA-1 - critical - XSS issue - CVE-2021-1234",
                    "severity": "",
                    "link": "https://example.com/adv2",
                },
            },
        },
    }), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK, audit=audit)
    result = gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    (row,) = result.add_on_updates
    assert row["name"] == [
        {"title": '<a href="https://example.com/adv2">SA-1 - XSS issue - CVE-2021-1234</a>',
         "severity": "critical"}
    ]


def test_d8_audit_advisory_link_fallback_for_unknown_new_version(gateway, reset_sc, monkeypatch):
    # The package is NOT in the dry-run parse, so current/new_version stay "unknown" and
    # the advisory-link fallback fires.
    audit = (json.dumps({
        "advisories": {
            "drupal/unmatched": {
                "GHSA-3": {
                    "title": "Some advisory",
                    "severity": "low",
                    "link": "https://example.com/adv3",
                },
            },
        },
    }), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK, audit=audit)
    result = gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    (row,) = result.add_on_updates
    assert row["current_version"] == "unknown"
    assert row["new_version"] == "See advisory"
    assert row["new_version_url"] == "https://example.com/adv3"


def test_d8_abandoned_packages_are_printed(gateway, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    audit = (json.dumps({"abandoned": {"some/package": {}}}), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK, audit=audit)
    gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    assert "Abandoned packages:" in console.export_text()


def test_d8_composer_dry_run_fatal_adds_alert_and_no_smell(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK,
                  dryrun=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_drupal(SITE_D8, LIVE, ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_D8['name']},composer-update"]
    assert result.composer_smell == ""


def test_d8_composer_stderr_becomes_composer_smell_not_drush_smell(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK,
                  dryrun=("nothing to upgrade\n", "composer warning", False))
    result = gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    assert result.composer_smell == "composer warning"
    assert result.drush_smell == ""


# ── D7 happy path (pm:updatestatus) ─────────────────────────────────────────────────
def test_d7_fallback_chain_and_none_status(gateway, reset_sc, monkeypatch):
    updatestatus = (json.dumps({
        "candidate_pkg": {
            "existing_version": "7.x-1.0", "candidate_version": "7.x-1.1",
            "project_status": "not-supported", "type": "module", "title": "Candidate Mod",
        },
        "recommended_pkg": {
            "existing_version": "7.x-2.0", "recommended": "7.x-2.1",
            "project_status": "not-supported", "type": "module", "title": "Recommended Mod",
        },
        "latest_pkg": {
            "existing_version": "7.x-3.0", "latest_version": "7.x-3.1",
            "project_status": "not-supported", "type": "theme", "title": "Latest Theme",
        },
        "none_pkg": {
            "existing_version": "7.x-4.0", "project_status": "unsupported",
            "type": "module", "title": "None Pkg",
        },
    }), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D7_OK, updatestatus=updatestatus)
    result = gather_drupal(SITE_D7, LIVE, _ctx(reset_sc))
    by_slug = {row["slug"]: row for row in result.add_on_updates}
    assert by_slug["candidate_pkg"]["new_version"] == "7.x-1.1"
    assert by_slug["recommended_pkg"]["new_version"] == "7.x-2.1"
    assert by_slug["latest_pkg"]["new_version"] == "7.x-3.1"
    assert by_slug["none_pkg"]["new_version"] == "none: unsupported"


def test_d7_type_field_uses_dict_value_not_builtin(gateway, reset_sc, monkeypatch):
    # D-i10-7: the moved expression must be `"type" in u`, not `type in u` (the type
    # BUILTIN tested for dict membership -- always False, so every row rendered
    # "package" regardless of what Drupal actually reported).
    updatestatus = (json.dumps({
        "mod-1": {
            "existing_version": "1.0", "project_status": "not-supported",
            "type": "module", "title": "Mod One",
        },
    }), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D7_OK, updatestatus=updatestatus)
    result = gather_drupal(SITE_D7, LIVE, _ctx(reset_sc))
    (row,) = result.add_on_updates
    assert row["type"] == "module"


def test_d7_link_present_renders_anchor(gateway, reset_sc, monkeypatch):
    updatestatus = (json.dumps({
        "mod-1": {
            "existing_version": "1.0", "candidate_version": "1.1",
            "project_status": "not-supported", "type": "module", "title": "Mod One",
            "link": "https://example.com/mod-1",
        },
    }), "", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D7_OK, updatestatus=updatestatus)
    result = gather_drupal(SITE_D7, LIVE, _ctx(reset_sc))
    (row,) = result.add_on_updates
    assert row["name"] == '<a href="https://example.com/mod-1">Mod One</a>'


def test_d7_fatal_updatestatus_adds_notice_and_no_rows(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D7_OK,
                  updatestatus=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_drupal(SITE_D7, LIVE, ctx)
    # drush() appends the JSON-decode failure detail to the captured stderr before the
    # notice is built (fix_drush_output/json.loads("") on empty stdout), so pin the
    # prefix (the test_gather_wordpress.py pattern), not the whole csv.
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE_D7['name']},drush-error,pm-updatestatus,\"boom")
    assert result.add_on_updates == []


def test_d7_updatestatus_stderr_is_not_captured_as_a_smell(gateway, reset_sc, monkeypatch):
    updatestatus = (json.dumps({}), "verbose progress spew", False)
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D7_OK, updatestatus=updatestatus)
    result = gather_drupal(SITE_D7, LIVE, _ctx(reset_sc))
    assert result.drush_smell == ""


# ── Fatal core-status / pm:list ──────────────────────────────────────────────────────
def test_fatal_core_status_adds_notice_and_unknown_version(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_drupal(SITE_D8, LIVE, ctx)
    # drush() appends the JSON-decode failure detail to the captured stderr (empty
    # stdout json.loads fails), so pin the prefix, not the whole csv.
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE_D8['name']},drush-error,core-status,\"boom")
    assert result.drupal_version == "unknown"
    assert result.results_entry == {
        "framework": "drupal9",
        "version": "unknown",
        "plan_name": "Basic",
    }


def test_fatal_pmlist_adds_notice(gateway, reset_sc, monkeypatch):
    _install_fake(monkeypatch, gateway, core_status=CORE_STATUS_D8_OK,
                  pmlist=("", "boom", True))
    ctx = _ctx(reset_sc)
    result = gather_drupal(SITE_D8, LIVE, ctx)
    # drush() appends the JSON-decode failure detail to the captured stderr (empty
    # stdout json.loads fails), so pin the prefix, not the whole csv.
    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["csv"].startswith(f"{SITE_D8['name']},drush-error,pm-list,\"boom")
    assert result.modules is None


def test_smell_is_last_wins_core_status_then_pmlist(gateway, reset_sc, monkeypatch):
    _install_fake(
        monkeypatch, gateway,
        core_status=(json.dumps({"drupal-version": "9.5.10"}), "cs warning", False),
        pmlist=(json.dumps({}), "pm warning", False),
    )
    result = gather_drupal(SITE_D8, LIVE, _ctx(reset_sc))
    assert result.drush_smell == "pm warning"
