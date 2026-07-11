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
    assert facts.fqdns_not_behind_cloudflare == []      # classification skipped on transient


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
