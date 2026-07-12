import datetime
import re

import pytest

from helpers.checkload import load_check_package
from helpers.dnsfake import patch_resolve, recording_console

pytestmark = pytest.mark.integration

FQDN_RE = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)

# Production site ids are UUIDs (pantheon-sitehealth-emails:1540 builds `<id>.live`); use one, so
# the tests do not bake in a false mental model.
SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
SITE_NAME = "bus-occb"

ZONE = {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]}
DNS_ROWS = [
    {"domain": "occb.bus.umich.edu", "type": "A", "value": "23.185.0.4"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8000::4"},
    {"domain": "occb.bus.umich.edu", "type": "AAAA", "value": "2620:12a:8001::4"},
]


@pytest.fixture
def check(psh, reset_sc, request, monkeypatch):
    patch_resolve(monkeypatch, ZONE)
    monkeypatch.setattr(reset_sc, "cloudflare_enabled", lambda: True)
    monkeypatch.setattr(reset_sc, "umich_enabled", lambda: True)
    monkeypatch.setattr(reset_sc, "fqdn_re", FQDN_RE)
    monkeypatch.setattr(reset_sc, "terminus", lambda *args: (DNS_ROWS, "", False))
    reset_sc.plugin_context["plugin.cloudflare"] = {"proxied_fqdns": {}}
    return load_check_package(psh, "pantheon_cdn_change", "pcc_init_probe", request)


def _ctx(reset_sc, custom_domains):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["custom_domains"] = custom_domains
    return ctx


def test_registers_one_hook_unconditionally(psh, reset_sc, request):
    reset_sc.config = {}                       # no [Cloudflare], no [UMich]
    load_check_package(psh, "pantheon_cdn_change", "pcc_reg_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_post_dns"]] == \
        ["check.pantheon_cdn_change.hook.check_pantheon_cdn_change"]


def test_hook_adds_exactly_one_notice(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    ctx = _ctx(reset_sc, ["occb.bus.umich.edu"])
    check.hook.check_pantheon_cdn_change(ctx)
    assert len(ctx["notices"]) == 1
    notice = ctx["notices"][0]
    assert notice["type"] == "info"
    assert notice["csv"] == "bus-occb,pantheon-cdn-change,occb.bus.umich.edu"
    assert notice["icon"] == reset_sc.icon["info"]      # add_notice fills the magnifying glass
    assert "23.185.0.4" in notice["message"]           # Pantheon's answer reached the notice
    assert "ITS will make these changes for you" in notice["message"]   # U-M, before the cutoff


def test_terminus_is_called_with_the_live_environment_of_the_site_id(check, reset_sc, monkeypatch):
    # The command takes the UUID, not the site name (core: live_site = site["id"] + ".live").
    calls = []
    monkeypatch.setattr(reset_sc, "terminus",
                        lambda *args: (calls.append(args), (DNS_ROWS, "", False))[1])
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    check.hook.check_pantheon_cdn_change(_ctx(reset_sc, ["occb.bus.umich.edu"]))
    assert calls == [("domain:dns", f"{SITE_ID}.live")]


def test_on_or_after_cutoff_umich_gets_the_generic_instruction(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 9, 15))  # cutoff DAY
    ctx = _ctx(reset_sc, ["occb.bus.umich.edu"])
    check.hook.check_pantheon_cdn_change(ctx)
    assert "ITS will make these changes" not in ctx["notices"][0]["message"]
    assert "Please replace each CNAME record above" in ctx["notices"][0]["message"]


def test_no_custom_domains_no_notice(check, reset_sc, monkeypatch):
    # Assert against the SiteContext the hook actually ran on -- a freshly built one would have an
    # empty notices list no matter what the hook did, which asserts nothing.
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    ctx = _ctx(reset_sc, [])
    check.hook.check_pantheon_cdn_change(ctx)
    assert ctx["notices"] == []


def test_clean_site_no_notice(check, reset_sc, monkeypatch):
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    ctx = _ctx(reset_sc, ["clean.example.org"])        # no CNAME in ZONE -> NoAnswer -> no hit
    check.hook.check_pantheon_cdn_change(ctx)
    assert ctx["notices"] == []


def test_missing_plugin_context_does_not_raise(check, reset_sc, monkeypatch):
    # F6: [Cloudflare] enabled but the plugin bag absent.
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    reset_sc.plugin_context.pop("plugin.cloudflare", None)
    ctx = _ctx(reset_sc, ["occb.bus.umich.edu"])
    check.hook.check_pantheon_cdn_change(ctx)
    assert len(ctx["notices"]) == 1                    # the DNS source still works


def test_findings_are_announced_at_verbosity_zero(check, reset_sc, monkeypatch):
    # Observability (SPEC §9): -notices.csv is only written under --all, so on a single-site run
    # the console is the operator's ONLY channel.  The message names the SITE, not the UUID.
    console = recording_console(monkeypatch, reset_sc)
    monkeypatch.setattr(check.hook, "today", lambda: datetime.date(2026, 8, 1))
    check.hook.check_pantheon_cdn_change(_ctx(reset_sc, ["occb.bus.umich.edu"]))
    out = console.export_text()
    assert "ATTENTION" in out and SITE_NAME in out
    assert SITE_ID not in out
