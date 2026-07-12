# tests/unit/test_dns_classify.py
import ipaddress

import dns.resolver
import pytest

import dns_classify

pytestmark = pytest.mark.unit


class _RData:
    def __init__(self, address):
        self.address = address


def _raise(exc):
    def _fn(hostname, rrtype):
        raise exc
    return _fn


def test_nxdomain_is_definitive_not_transient(reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _raise(dns.resolver.NXDOMAIN()))
    cf, elsewhere, transient = dns_classify.classify_hostname_dns("example.org", False, [], [])
    assert (cf, elsewhere) == (0, 0)
    assert transient is False


def test_timeout_is_transient(reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _raise(dns.resolver.Timeout()))
    cf, elsewhere, transient = dns_classify.classify_hostname_dns("example.org", False, [], [])
    assert (cf, elsewhere) == (0, 0)
    assert transient is True


def test_cloudflare_ip_counted(reset_sc, monkeypatch):
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("104.16.0.1")]
        raise dns.resolver.NoAnswer()
    monkeypatch.setattr(dns_classify, "resolve", fake)
    cf, elsewhere, transient = dns_classify.classify_hostname_dns(
        "example.org", True, [ipaddress.ip_network("104.16.0.0/12")], [])
    assert cf == 1 and elsewhere == 0 and transient is False


def test_non_cloudflare_ip_is_elsewhere(reset_sc, monkeypatch):
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("203.0.113.5")]
        raise dns.resolver.NoAnswer()
    monkeypatch.setattr(dns_classify, "resolve", fake)
    cf, elsewhere, transient = dns_classify.classify_hostname_dns(
        "example.org", True, [ipaddress.ip_network("104.16.0.0/12")], [])
    assert cf == 0 and elsewhere == 1


def _domains(spec):
    """spec: name -> (type, primary). Mirrors the terminus domain:list dict shape."""
    return {name: {"id": name, "type": t, "primary": p} for name, (t, p) in spec.items()}


def _resolver(mapping):
    """mapping: hostname -> "cf" | "elsewhere" | "missing" | "transient"."""
    def fake(hostname, rrtype):
        kind = mapping.get(hostname, "missing")
        if rrtype != "A":
            raise dns.resolver.NoAnswer()
        if kind == "cf":
            return [_RData("104.16.0.1")]
        if kind == "elsewhere":
            return [_RData("203.0.113.5")]
        if kind == "transient":
            raise dns.resolver.Timeout()
        raise dns.resolver.NXDOMAIN()
    return fake


CF_V4 = [ipaddress.ip_network("104.16.0.0/12")]


def test_classify_domains_skips_platform_and_invalid(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"www.example.org": "elsewhere"}))
    domains = _domains({
        "example.pantheonsite.io": ("platform", False),   # skipped
        "BAD HOST": ("custom", False),                     # fails fqdn_re -> skipped
        "www.example.org": ("custom", True),
    })
    facts = dns_classify.classify_domains(
        domains, False, [], [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.custom_domains == ["BAD HOST", "www.example.org"]  # keys, unfiltered (unchanged)
    assert facts.primary_domain == ["www.example.org"]
    assert facts.main_fqdn == "www.example.org"


def test_transient_excluded_from_not_in_dns_and_cf(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"t.example.org": "transient"}))
    domains = _domains({"t.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.dns_transient == ["t.example.org"]
    assert facts.not_in_dns == []                       # P4: transient != not-in-dns
    assert facts.fqdns_not_behind_cloudflare == []      # nothing resolved -> no CF classification


def test_bug1_zone_conflict_list_populated_when_all_behind_cloudflare(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"w.example.org": "cf"}))
    domains = _domains({"w.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [],
        proxied_fqdns={"w.example.org": {}},
        fqdn_zone_conflicts={"w.example.org": ["z1", "z2"]},
        fqdn_re=psh.fqdn_re)
    assert facts.fqdns_not_behind_cloudflare == []
    assert facts.fqdns_behind_cloudflare == ["w.example.org"]
    assert facts.proxied_in_multiple_zones == ["w.example.org"]


def test_not_in_dns_host_skips_cloudflare_checks(psh, reset_sc, monkeypatch):
    # A definitively-absent FQDN (NXDOMAIN both families) is an alert only; DNS points nowhere,
    # so it is NOT also flagged "not behind Cloudflare".
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"gone.example.org": "missing"}))
    domains = _domains({"gone.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.not_in_dns == ["gone.example.org"]
    assert facts.fqdns_not_behind_cloudflare == []        # not double-flagged
    assert facts.behind_cloudflare_not_proxied == []
    assert facts.dns_transient == []


def test_cf_record_runs_cloudflare_checks_despite_transient_sibling(psh, reset_sc, monkeypatch):
    # Any record pointing at Cloudflare -> run the CF checks even though the AAAA lookup was
    # transient; do not downgrade the host to "unknown / retry".
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("104.16.0.1")]         # Cloudflare
        raise dns.resolver.Timeout()              # AAAA transient
    monkeypatch.setattr(dns_classify, "resolve", fake)
    domains = _domains({"w.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.behind_cloudflare_not_proxied == ["w.example.org"]   # CF checks ran
    assert facts.dns_transient == []                                  # we resolved; not "unknown"
    assert facts.not_in_dns == []


def test_elsewhere_record_classified_despite_transient_sibling(psh, reset_sc, monkeypatch):
    # A definitive non-CF address yields "not behind Cloudflare" even if a sibling lookup timed out.
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("203.0.113.5")]        # non-Cloudflare
        raise dns.resolver.Timeout()              # AAAA transient
    monkeypatch.setattr(dns_classify, "resolve", fake)
    domains = _domains({"e.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.fqdns_not_behind_cloudflare == ["e.example.org"]
    assert facts.dns_transient == []
    assert facts.not_in_dns == []


def test_malformed_domain_entry_is_skipped_not_crashing(psh, reset_sc, monkeypatch):
    # A domain entry missing keys, or whose value is not a dict, must be skipped, never KeyError.
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"ok.example.org": "elsewhere"}))
    domains = {
        "ok.example.org": {"id": "ok.example.org", "type": "custom", "primary": True},
        "broken.example.org": {"id": "broken.example.org"},   # missing type/primary
        "no-id.example.org": {"type": "custom"},              # missing id
        "not-a-dict.example.org": "oops",                     # value not a dict
    }
    facts = dns_classify.classify_domains(              # must not raise
        domains, False, [], [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.main_fqdn == "ok.example.org"
    assert "ok.example.org" in facts.custom_domains


def test_non_dict_domains_returns_empty_facts(psh, reset_sc):
    facts = dns_classify.classify_domains(
        None, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts == dns_classify.DnsFacts([], [], "", [], [], [], [], [], [])


def test_stuff_dns_contract_maps_each_field(reset_sc):
    # Distinct sentinel per field: any facts.X -> site_context["Y"] value-swap fails here.
    facts = dns_classify.DnsFacts(
        custom_domains=["cd"], primary_domain=["pd"], main_fqdn="mf", not_in_dns=["nid"],
        fqdns_behind_cloudflare=["fbc"], fqdns_not_behind_cloudflare=["fnbc"],
        behind_cloudflare_not_proxied=["bcnp"], proxied_in_multiple_zones=["pmz"],
        dns_transient=["dt"])
    ctx = reset_sc.SiteContext({"name": "s"})
    dns_classify.stuff_dns_contract(ctx, {"raw": "domains"}, facts)
    assert ctx["domains"] == {"raw": "domains"}
    assert ctx["custom_domains"] == ["cd"]
    assert ctx["primary_domain"] == ["pd"]
    assert ctx["main_fqdn"] == "mf"
    assert ctx["fqdns_behind_cloudflare"] == ["fbc"]
    assert ctx["fqdns_not_behind_cloudflare"] == ["fnbc"]
    assert ctx["not_in_dns"] == ["nid"]
    assert ctx["behind_cloudflare_not_proxied"] == ["bcnp"]
    assert ctx["proxied_in_multiple_zones"] == ["pmz"]
    assert ctx["dns_transient"] == ["dt"]


from hypothesis import HealthCheck, given, settings, strategies as st


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(hosts=st.dictionaries(
    st.from_regex(r"[a-z]{1,6}\.example\.org", fullmatch=True),
    st.sampled_from(["cf", "elsewhere", "missing", "transient"]),
    max_size=6))
def test_property_transient_never_in_not_in_dns(psh, reset_sc, monkeypatch, hosts):
    monkeypatch.setattr(dns_classify, "resolve", _resolver(hosts))
    domains = _domains({h: ("custom", False) for h in hosts})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert set(facts.dns_transient).isdisjoint(facts.not_in_dns)


def test_elsewhere_host_lands_in_fqdns_not_behind_cloudflare(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"e.example.org": "elsewhere"}))
    domains = _domains({"e.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.fqdns_not_behind_cloudflare == ["e.example.org"]
    assert facts.fqdns_behind_cloudflare == []
    assert facts.behind_cloudflare_not_proxied == []


def test_cf_host_absent_from_proxied_lands_in_behind_cloudflare_not_proxied(psh, reset_sc, monkeypatch):
    monkeypatch.setattr(dns_classify, "resolve", _resolver({"c.example.org": "cf"}))
    domains = _domains({"c.example.org": ("custom", True)})
    facts = dns_classify.classify_domains(
        domains, True, CF_V4, [], proxied_fqdns={}, fqdn_zone_conflicts={}, fqdn_re=psh.fqdn_re)
    assert facts.behind_cloudflare_not_proxied == ["c.example.org"]
    assert facts.fqdns_behind_cloudflare == []
    assert facts.fqdns_not_behind_cloudflare == []


def test_resolve_converts_a_malformed_name_into_a_named_exception(psh, reset_sc):
    # F10: dns.name.EmptyLabel derives from dns.exception.SyntaxError, which no dns.resolver.*
    # except clause catches -- unconverted, it aborts the whole run from inside the per-site loop.
    import dns_classify
    with pytest.raises(dns_classify.MalformedNameError):
        dns_classify.resolve("a..b", "CNAME")
    with pytest.raises(dns_classify.MalformedNameError):
        dns_classify.resolve("x" * 70 + ".example.org", "A")


def test_resolve_converts_a_struct_error_from_an_out_of_range_byte_escape(psh, reset_sc):
    # A REAL dnspython gap, verified by execution: "\300.com" is a byte-escape sequence whose
    # value (300) is out of range for struct.pack("!B", ...) inside dns.name.from_text -- it
    # raises the stdlib struct.error, which is NOT a dns.exception.DNSException at all, so it
    # was NOT covered by the (SyntaxError, NameTooLong) except clause.  This is reachable through
    # an ordinary hostname string -- no monkeypatching -- e.g. via a Cloudflare `origins` value,
    # which is arbitrary remote content not gated by fqdn_re.
    import dns_classify
    with pytest.raises(dns_classify.MalformedNameError):
        dns_classify.resolve("\\300.com", "CNAME")


def test_resolve_converts_a_real_idna_exception(psh, reset_sc, monkeypatch):
    # dns.name.IDNAException derives from dns.exception.DNSException but NOT from SyntaxError, so
    # it also escaped the old except clause.  It is raised by IDNACodec.decode() on an "xn--"
    # label whose punycode tail fails to decode -- a real, non-fabricated raise, confirmed by
    # calling the actual dnspython codec below -- but that decode() path is never reached by
    # dns.resolver.resolve(hostname, rrtype) for any hostname string (encoding a query name never
    # calls decode(); verified empirically against dnspython 2.8.0, which is what is pinned here).
    # So the underlying dns.resolver.resolve is monkeypatched to raise the SAME real exception
    # instance, to prove resolve()'s except clause converts it -- the fix guards a real dnspython
    # exception class, even though nothing in this codebase's call pattern can trigger it today.
    import dns.name
    import dns_classify

    real_exc = None
    try:
        dns.name.IDNA_2003_Practical.decode(b"xn--0")   # real raise, not hand-constructed
        pytest.fail("expected dns.name.IDNAException")
    except dns.name.IDNAException as e:
        real_exc = e   # exception-clause names are cleared on block exit -- rebind explicitly

    def boom(hostname, rrtype):
        raise real_exc
    monkeypatch.setattr(dns.resolver, "resolve", boom)
    with pytest.raises(dns_classify.MalformedNameError):
        dns_classify.resolve("xn--0.example.org", "A")


def test_classify_hostname_dns_survives_a_malformed_name(psh, reset_sc, monkeypatch):
    # The caller must NOT see the exception: a bad domain id skips that host, it does not kill
    # the run.  A name that cannot exist in DNS is definitively unresolvable -> (0, 0, False),
    # which the caller aggregates into the existing not_in_dns alert (whose remedy -- "remove
    # these domains from the Pantheon live environment, or add them to DNS" -- is correct here).
    import dns_classify

    def boom(name, rrtype):
        raise dns_classify.MalformedNameError(f"{name}: EmptyLabel")

    monkeypatch.setattr(dns_classify, "resolve", boom)
    assert dns_classify.classify_hostname_dns("a..b", False, [], []) == (0, 0, False)


def test_malformed_domain_id_does_not_abort_classify_domains(psh, reset_sc, monkeypatch):
    # End of the shadow path: a malformed id in a real domain:list must not raise out of
    # classify_domains (which runs inside the per-site loop, which has no try/except).
    import re

    import dns_classify

    def boom(name, rrtype):
        raise dns_classify.MalformedNameError(f"{name}: EmptyLabel")

    monkeypatch.setattr(dns_classify, "resolve", boom)
    domains = {"a..b": {"id": "a..b", "type": "custom", "primary": True}}
    facts = dns_classify.classify_domains(
        domains, False, [], [], {}, {}, re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.I))
    assert facts.not_in_dns == ["a..b"]      # definitive: it cannot be in DNS
    assert facts.dns_transient == []
