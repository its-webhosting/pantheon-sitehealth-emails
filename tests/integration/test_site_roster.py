"""Integration tier: psh.cli.resolve_site_roster, main()'s org:site:list fetch + the
--resume-from filter (development/2026-08-07-main-extraction/SPEC.md section 5.4 -- B14).

Seam (SPEC section 6 row 4): psh.gateway.run_terminus (the `gateway` conftest fixture) --
terminus_data("org:site:list", ...) reaches it through psh.gateway's OWN terminus(), so the
gateway fixture is sufficient (no psh.cli-side binding to double-patch here, unlike row 2's
gather_framework).  sc.options.resume_from is driven through
`reset_sc.options = psh.parse_args([...])`, never a direct attribute poke.  The resume banner
is read back through `recording_console(monkeypatch, sc, width=80)` -- CLAUDE.md's rich
gotcha: sc.console is a bare Console() that hard-wraps at 80 columns on a non-tty, which is
how every real --all run is launched, so a test at the library's wide default would not have
caught the wrapped-resume-command defect that motivated this seam rule in the first place.

The single most important assertion in this file is
test_site_count_is_the_pre_filter_total_not_len_site_names (SPEC R5.4.3): --resume-from
requires --all, and --all is in tests/conftest.py's FORBIDDEN_FLAGS, so this whole region is
UNREACHABLE at the subprocess tier by design (SPEC section 1.2) -- nothing in the suite before
this file would go red if site_count were "tidied" to len(site_names).
"""
import json

import pytest
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

ORG_ID = "test-org-id"

SITES_PAYLOAD = {
    "id-a": {"id": "id-a", "name": "aaa-site"},
    "id-b": {"id": "id-b", "name": "bbb-site"},
    "id-c": {"id": "id-c", "name": "ccc-site"},
}


def _install_fake_roster(monkeypatch, gateway, payload=SITES_PAYLOAD, *, fatal=False):
    def fake(command, input_data=None):
        if "org:site:list" in command:
            return (json.dumps(payload), "", fatal)
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(gateway, "run_terminus", fake)


# ── happy path ────────────────────────────────────────────────────────────────────────
def test_returns_roster_sorted_and_unfiltered_when_no_resume(psh, reset_sc, gateway, monkeypatch):
    _install_fake_roster(monkeypatch, gateway)
    reset_sc.options = psh.parse_args([])  # resume_from defaults to None

    roster = psh.resolve_site_roster(ORG_ID)

    assert roster.sites == SITES_PAYLOAD
    assert roster.name_to_id == {"aaa-site": "id-a", "bbb-site": "id-b", "ccc-site": "id-c"}
    assert roster.site_names == ["aaa-site", "bbb-site", "ccc-site"]
    assert roster.site_count == 3


# ── R5.4.3: site_count is len(sites) BEFORE the filter, never len(site_names) ──────────
def test_site_count_is_the_pre_filter_total_not_len_site_names(
    psh, reset_sc, gateway, monkeypatch
):
    _install_fake_roster(monkeypatch, gateway)
    # Resume from the middle site: site_names narrows to a 2-element suffix, but site_count
    # -- the banner/finish_run denominator -- MUST stay the full pre-filter total of 3.
    reset_sc.options = psh.parse_args(["--all", "--resume-from", "bbb-site"])

    roster = psh.resolve_site_roster(ORG_ID)

    assert roster.site_names == ["bbb-site", "ccc-site"]
    assert len(roster.site_names) == 2
    assert roster.site_count == 3  # NOT len(roster.site_names)


# ── shadow: nil -- a fatal org:site:list aborts the run ────────────────────────────────
def test_fatal_org_site_list_exits_with_named_message(psh, reset_sc, gateway, monkeypatch):
    _install_fake_roster(monkeypatch, gateway, fatal=True)
    reset_sc.options = psh.parse_args([])

    with pytest.raises(SystemExit) as exc:
        psh.resolve_site_roster(ORG_ID)
    assert "Could not list organization sites" in str(exc.value)


# ── shadow: empty -- zero-site org, no resume banner ────────────────────────────────────
def test_empty_org_returns_empty_roster_with_zero_count(psh, reset_sc, gateway, monkeypatch):
    _install_fake_roster(monkeypatch, gateway, payload={})
    reset_sc.options = psh.parse_args([])

    roster = psh.resolve_site_roster(ORG_ID)

    assert roster.sites == {}
    assert roster.name_to_id == {}
    assert roster.site_names == []
    assert roster.site_count == 0


# ── shadow: upstream error -- an unknown --resume-from name is fatal, count in message ──
def test_unknown_resume_from_exits_with_named_message_and_count(
    psh, reset_sc, gateway, monkeypatch
):
    _install_fake_roster(monkeypatch, gateway)
    reset_sc.options = psh.parse_args(["--all", "--resume-from", "no-such-site"])

    with pytest.raises(SystemExit) as exc:
        psh.resolve_site_roster(ORG_ID)
    message = str(exc.value)
    assert "--resume-from: site 'no-such-site' was not found among the 3 sites" in message
    assert ORG_ID in message


# ── resume banner, at PRODUCTION's non-tty console width ────────────────────────────────
def test_resume_banner_reports_remaining_of_total(psh, reset_sc, gateway, monkeypatch):
    _install_fake_roster(monkeypatch, gateway)
    console = recording_console(monkeypatch, reset_sc, width=80)
    reset_sc.options = psh.parse_args(["--all", "--resume-from", "bbb-site"])

    roster = psh.resolve_site_roster(ORG_ID)

    assert roster.site_count == 3
    assert len(roster.site_names) == 2
    output = console.export_text()
    assert "Resuming from" in output
    assert "bbb-site" in output
    assert "2 of 3 sites remaining" in output


def test_no_resume_banner_printed_without_resume_from(psh, reset_sc, gateway, monkeypatch):
    _install_fake_roster(monkeypatch, gateway)
    console = recording_console(monkeypatch, reset_sc, width=80)
    reset_sc.options = psh.parse_args([])

    psh.resolve_site_roster(ORG_ID)

    assert "Resuming" not in console.export_text()
