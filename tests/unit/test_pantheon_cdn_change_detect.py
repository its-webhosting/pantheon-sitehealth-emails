import re

import dns.resolver
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import patch_resolve, recording_console

pytestmark = pytest.mark.unit

FQDN_RE = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)   # core's regex (:89)

OCCB_ZONE = {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]}
BACKSTAGE_ZONE = {
    ("backstage.its.umich.edu", "CNAME"): ["backstage.its.umich.edu.cdn.cloudflare.net."],
}
BACKSTAGE_PROXIED = {
    "backstage.its.umich.edu": {
        "zone_id": "1f39", "origins": ["live-its-backstage.pantheonsite.io"]},
}


@pytest.fixture
def detect(psh, reset_sc, request, monkeypatch):
    monkeypatch.setattr(reset_sc, "fqdn_re", FQDN_RE)
    return load_check_module(
        psh, "pantheon_cdn_change", "detect", "pcc_detect_probe", request)


def _pantheon_says(detect, monkeypatch, mapping, calls=None):
    """Patch pantheon.required_records on the module `detect` actually imported.

    `mapping` is {fqdn: (a, aaaa, cname)}.
    """
    def _required(site_id, site_name=""):
        if calls is not None:
            calls.append(site_id)
        return {fqdn: detect.pantheon.Required(a, aaaa, cname)
                for fqdn, (a, aaaa, cname) in mapping.items()}
    monkeypatch.setattr(detect.pantheon, "required_records", _required)


def test_dns_only_finding(detect, monkeypatch):
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {
        "occb.bus.umich.edu": (["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], [])})
    assert detect.find_findings(
        "uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True) == [
            detect.Finding("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
                           ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], [])]


def test_cloudflare_only_finding(detect, monkeypatch):
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {
        "backstage.its.umich.edu": (["23.185.0.2"], ["2620:12a:8000::2"], [])})
    findings = detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], BACKSTAGE_PROXIED, True)
    assert findings[0].where == "cloudflare"
    assert findings[0].a == ["23.185.0.2"]         # Pantheon's answer, not a resolved target


def test_both_sources_same_target_is_one_row(detect, monkeypatch):
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {"occb.bus.umich.edu": (["23.185.0.4"], [], [])})
    proxied = {"occb.bus.umich.edu": {"origins": ["live-bus-occb.pantheonsite.io"]}}
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], proxied, True)
    assert len(findings) == 1
    assert findings[0].where == "both"


def test_split_targets_warn_but_emit_one_row(detect, reset_sc, monkeypatch):
    # F11: the two sources reach DIFFERENT legacy names.  Pantheon's per-domain answer is correct
    # for BOTH records, so it is one row -- but the disagreement is an operator signal.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, {("x.example.org", "CNAME"): ["live-aaa.pantheonsite.io."]})
    _pantheon_says(detect, monkeypatch, {"x.example.org": (["23.185.0.9"], [], [])})
    proxied = {"x.example.org": {"origins": ["live-bbb.pantheonsite.io"]}}
    findings = detect.find_findings("uuid", "s", ["x.example.org"], proxied, True)
    assert len(findings) == 1
    assert findings[0].where == "both"
    assert findings[0].a == ["23.185.0.9"]        # Pantheon's, NOT live-aaa's or live-bbb's
    out = console.export_text()
    assert "DIFFERENT" in out and "live-aaa" in out and "live-bbb" in out


def test_cname_only_finding_warns(detect, reset_sc, monkeypatch):
    # F14: Pantheon answers with a CNAME and no A/AAAA (an already-migrated site).  The finding
    # carries the CNAME, and the operator is told -- it must NOT look like a failed lookup.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch,
                   {"occb.bus.umich.edu": ([], [], ["fe.cfp2c.edge.pantheon.io"])})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].cname == ["fe.cfp2c.edge.pantheon.io"]
    assert findings[0].a == [] and findings[0].aaaa == []
    out = console.export_text()
    assert "no A/AAAA" in out and "fe.cfp2c.edge.pantheon.io" in out


def test_clean_site_makes_no_pantheon_call(detect, monkeypatch):
    # The domain:dns call is LAZY: a clean site must cost nothing on an --all run.
    calls = []
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {}, calls=calls)
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], {}, True) == []
    assert calls == []


def test_cloudflare_disabled_skips_source_two(detect, monkeypatch):
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], BACKSTAGE_PROXIED, False) == []


def test_transient_dns_is_never_a_finding(detect, monkeypatch):
    patch_resolve(monkeypatch, {("a.example.org", "CNAME"): dns.resolver.Timeout()})
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings("uuid", "s", ["a.example.org"], {}, True) == []


def test_legacy_array_form_of_fqdns_json(detect, monkeypatch):
    patch_resolve(monkeypatch, BACKSTAGE_ZONE)
    _pantheon_says(detect, monkeypatch, {"backstage.its.umich.edu": (["23.185.0.2"], [], [])})
    proxied = {"backstage.its.umich.edu": ["live-its-backstage.pantheonsite.io"]}   # old format
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], proxied,
        True)[0].where == "cloudflare"


def test_ip_origin_is_skipped_without_a_query(detect, monkeypatch):
    calls = []
    patch_resolve(monkeypatch, BACKSTAGE_ZONE, calls)
    _pantheon_says(detect, monkeypatch, {})
    proxied = {"backstage.its.umich.edu": {"origins": ["23.185.0.2", "2620:12a:8000::2"]}}
    assert detect.find_findings(
        "uuid", "its-backstage", ["backstage.its.umich.edu"], proxied, True) == []
    assert ("23.185.0.2", "CNAME") not in calls    # an IP literal is never resolved


def test_finding_without_records_still_reported(detect, monkeypatch):
    # F4: domain:dns failed (or has no row for this FQDN).  The CNAME still has to be fixed.
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].where == "dns"
    assert findings[0].a == [] and findings[0].aaaa == [] and findings[0].cname == []


def test_expected_target_is_the_sites_own_live_name(detect):
    assert detect.expected_target("bus-occb") == "live-bus-occb.pantheonsite.io"


def test_no_warning_when_the_target_is_the_sites_own_live_name(detect, reset_sc, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)          # occb -> live-bus-occb.pantheonsite.io
    _pantheon_says(detect, monkeypatch, {})
    detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert "not at this site's own" not in console.export_text()


def test_a_target_belonging_to_another_pantheon_site_is_announced(detect, reset_sc, monkeypatch):
    # The CNAME points at ANOTHER site's legacy name (a renamed site, a stale Cloudflare origin, a
    # domain moved between sites).  The owner is still shown the real target -- telling them it
    # points at X when it points at Y would be worse -- but a human needs to look at the site.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch,
                  {("occb.bus.umich.edu", "CNAME"): ["live-someone-else.pantheonsite.io."]})
    _pantheon_says(detect, monkeypatch, {})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].target == "live-someone-else.pantheonsite.io"    # reported as it IS
    out = console.export_text()
    assert "ATTENTION" in out
    assert "live-someone-else.pantheonsite.io" in out
    assert "live-bus-occb.pantheonsite.io" in out                       # what it SHOULD be
    assert "occb.bus.umich.edu" in out


def test_one_warning_per_wrong_target_not_one_per_domain(detect, reset_sc, monkeypatch):
    # Ten domains on one wrong target must produce ONE line, not ten.
    console = recording_console(monkeypatch, reset_sc)
    domains = [f"d{i}.bus.umich.edu" for i in range(10)]
    patch_resolve(monkeypatch,
                  {(d, "CNAME"): ["live-someone-else.pantheonsite.io."] for d in domains})
    _pantheon_says(detect, monkeypatch, {})
    detect.find_findings("uuid", "bus-occb", domains, {}, True)
    assert console.export_text().count("not at this site's own") == 1


def test_fqdn_absent_from_a_successful_answer_is_announced(detect, reset_sc, monkeypatch):
    # The call succeeded and answered for OTHER domains, but has no row for this one.  The owner
    # will be told "unavailable", so the operator has to hear about it.  Detected by MEMBERSHIP,
    # not by `records is pantheon.EMPTY`: an identity check against the shared sentinel would
    # silently stop firing the day required_records returns an equal-but-distinct Required([],[],[]).
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {"someone.else.example.org": (["1.2.3.4"], [], [])})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].a == []                       # still reported, records empty
    out = console.export_text()
    assert "ATTENTION" in out and "no required records" in out
    assert "occb.bus.umich.edu" in out


def test_no_per_domain_noise_when_the_whole_call_failed(detect, reset_sc, monkeypatch):
    # required_records already printed its own ATTENTION for the failure; a second line per domain
    # would be noise.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {})          # {} == the call failed / nothing usable
    detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert "no required records" not in console.export_text()


def test_absent_fqdn_in_successful_answer_warns_operator(detect, reset_sc, monkeypatch):
    # The call SUCCEEDED (Pantheon answered for at least one domain) but has no row for THIS
    # candidate.  The owner is about to be emailed "unavailable" -- the operator must be told,
    # or a "contact us" email goes out with nobody the wiser.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {"other.example.org": (["1.2.3.4"], [], [])})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].a == [] and findings[0].aaaa == [] and findings[0].cname == []
    out = console.export_text()
    assert "no required records" in out and "occb.bus.umich.edu" in out


def test_total_call_failure_does_not_duplicate_the_attention(detect, reset_sc, monkeypatch):
    # A total domain:dns failure already prints its own ATTENTION inside
    # pantheon.required_records (mocked away here); find_findings must NOT print a second,
    # per-domain ATTENTION on top of it -- that would be noise.
    console = recording_console(monkeypatch, reset_sc)
    patch_resolve(monkeypatch, OCCB_ZONE)
    _pantheon_says(detect, monkeypatch, {})
    findings = detect.find_findings("uuid", "bus-occb", ["occb.bus.umich.edu"], {}, True)
    assert findings[0].a == [] and findings[0].aaaa == [] and findings[0].cname == []
    out = console.export_text()
    assert "no required records" not in out


def test_is_safe_domain_id(detect):
    # F13 is a CSV-integrity guard.  fqdn_re REJECTS a comma (that is the one that matters), but
    # it ACCEPTS a..b and a trailing newline -- hence the explicit control-character reject.
    assert detect.is_safe_domain_id("occb.bus.umich.edu") is True
    assert detect.is_safe_domain_id("has,comma.example.org") is False
    assert detect.is_safe_domain_id("trailing.newline.example.org\n") is False
    assert detect.is_safe_domain_id("with space.example.org") is False


def test_invalid_domain_id_skipped(detect, monkeypatch):
    # A comma in a domain id would shift every column of -notices.csv (no escaping there).
    calls = []
    patch_resolve(monkeypatch, {}, calls)
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings(
        "uuid", "s", ["has,comma.example.org", "bad.example.org\n"], {}, True) == []
    assert calls == []            # never even resolved


def test_order_follows_custom_domains(detect, monkeypatch):
    zone = dict(OCCB_ZONE)
    zone[("aaa.bus.umich.edu", "CNAME")] = ["live-bus-occb.pantheonsite.io."]
    patch_resolve(monkeypatch, zone)
    _pantheon_says(detect, monkeypatch, {})
    findings = detect.find_findings(
        "uuid", "bus-occb", ["occb.bus.umich.edu", "aaa.bus.umich.edu"], {}, True)
    assert [f.fqdn for f in findings] == ["occb.bus.umich.edu", "aaa.bus.umich.edu"]


def test_no_custom_domains(detect, monkeypatch):
    patch_resolve(monkeypatch, {})
    _pantheon_says(detect, monkeypatch, {})
    assert detect.find_findings("uuid", "s", [], {}, True) == []


def test_cloudflare_origins_rejects_non_list_origins(detect):
    # A corrupted or future-format fqdns.json could carry a non-list `origins` value.  Must be []
    # -- never a TypeError (which would abort the whole --all run) and never a silent iteration
    # over the wrong thing (e.g. the characters of a string, or a dict's keys).
    assert detect.cloudflare_origins(
        "x.example.org", {"x.example.org": {"origins": 42}}) == []
    assert detect.cloudflare_origins(
        "x.example.org", {"x.example.org": {"origins": "abc"}}) == []
    assert detect.cloudflare_origins(
        "x.example.org", {"x.example.org": {"origins": {"a": 1}}}) == []


def test_find_findings_survives_non_list_origins(detect, monkeypatch):
    # Same corruption, exercised through find_findings: must not raise, and with no other
    # candidate source it must yield no finding (not a crashed --all run).
    patch_resolve(monkeypatch, {})
    _pantheon_says(detect, monkeypatch, {})
    proxied_int = {"x.example.org": {"origins": 42}}
    assert detect.find_findings("uuid", "s", ["x.example.org"], proxied_int, True) == []
    proxied_str = {"x.example.org": {"origins": "abc"}}
    assert detect.find_findings("uuid", "s", ["x.example.org"], proxied_str, True) == []
