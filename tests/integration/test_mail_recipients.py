"""psh.mail.resolve_recipients: the B49 recipient/contact resolution (campaign I12).

Seam: psh.gateway.run_terminus via the gateway fixture (generic branch); sc.config via
reset_sc (U-M branch).  The fatal-fetch path returns None (main() continues) -- the
D-i6-1 return-value pattern.
"""
import json

import pytest

from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration


def _site(name):
    return {"name": name}


def _umich_config(owner_group):
    return {"UMich": {"enabled": True, "portal": {"sites": {
        "its-wws-test1": {"owner_group": owner_group}}}}}


def test_umich_recipients_owner_group_and_owners_alias(psh, reset_sc):
    import psh.mail
    reset_sc.config = _umich_config("web team")
    got = psh.mail.resolve_recipients(_site("its-wws-test1"), "SITE_ID")
    assert got == ("web.team@umich.edu, web.team-owners@umich.edu", "web.team@umich.edu")


def test_umich_special_case_sites_get_single_recipient(psh, reset_sc):
    import psh.mail
    reset_sc.config = {"UMich": {"enabled": True, "portal": {"sites": {
        "lsa-disko-project": {"owner_group": "disko group"}}}}}
    got = psh.mail.resolve_recipients(_site("lsa-disko-project"), "SITE_ID")
    assert got == ("disko.group@umich.edu", "disko.group@umich.edu")


def test_generic_recipients_from_site_team_list(psh, reset_sc, gateway, monkeypatch):
    import psh.mail
    reset_sc.config = {}
    team = {"m1": {"email": "a@example.edu"}, "m2": {"email": "b@example.edu"}}
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps(team), "", False))
    got = psh.mail.resolve_recipients(_site("s"), "SITE_ID")
    assert got == ("a@example.edu, b@example.edu", "a@example.edu b@example.edu")


def test_generic_fatal_team_fetch_returns_none_and_prints(psh, reset_sc, gateway, monkeypatch):
    import psh.mail
    reset_sc.config = {}
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: ("", "boom", True))
    assert psh.mail.resolve_recipients(_site("s"), "SITE_ID") is None
    assert "could not fetch team for s" in console.export_text()
