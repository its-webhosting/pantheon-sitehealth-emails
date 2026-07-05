"""Integration tier: DNS classification distinguishes transient from definitive (P4).

Before P4, a resolver Timeout was caught, printed, and then -- because both address counts
stayed 0 -- reported identically to a genuinely-unregistered hostname ("not in DNS"), and
nothing became a structured report notice.  classify_hostname_dns() now separates transient
(Timeout / NoNameservers) from definitive (NXDOMAIN / NoAnswer) outcomes and emits a warning
notice for the transient case; main() keeps transient hosts out of the aggregated
"not in DNS" list.
"""
import ipaddress

import pytest

pytestmark = pytest.mark.integration


class _RData:
    def __init__(self, address):
        self.address = address


def test_nxdomain_is_definitive_not_transient(psh, monkeypatch):
    monkeypatch.setattr(
        psh.dns.resolver, "resolve",
        lambda hostname, rrtype: (_ for _ in ()).throw(psh.dns.resolver.NXDOMAIN),
    )
    cf, elsewhere, notices, transient = psh.classify_hostname_dns(
        "example.org", "its-wws-test1", False, [], []
    )
    # Both counts 0 and NOT transient -> main() will add it to not_in_dns (the aggregated
    # "not in DNS" notice), which is the correct, unchanged behavior for a missing domain.
    assert (cf, elsewhere) == (0, 0)
    assert notices == []
    assert transient is False


def test_timeout_is_transient_with_warning_notice(psh, monkeypatch):
    monkeypatch.setattr(
        psh.dns.resolver, "resolve",
        lambda hostname, rrtype: (_ for _ in ()).throw(psh.dns.resolver.Timeout),
    )
    cf, elsewhere, notices, transient = psh.classify_hostname_dns(
        "example.org", "its-wws-test1", False, [], []
    )
    assert (cf, elsewhere) == (0, 0)
    assert transient is True                       # NOT reported as "not in DNS"
    assert len(notices) == 1
    assert notices[0]["type"] == "warning"
    assert "its-wws-test1" in notices[0]["csv"]    # every notice needs a csv field
    assert "example.org" in notices[0]["message"]


def test_cloudflare_ip_is_counted(psh, monkeypatch):
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("104.16.0.1")]
        raise psh.dns.resolver.NoAnswer

    monkeypatch.setattr(psh.dns.resolver, "resolve", fake)
    cf, elsewhere, notices, transient = psh.classify_hostname_dns(
        "example.org", "s", True, [ipaddress.ip_network("104.16.0.0/12")], []
    )
    assert cf == 1
    assert elsewhere == 0
    assert transient is False


def test_non_cloudflare_ip_counts_as_elsewhere(psh, monkeypatch):
    def fake(hostname, rrtype):
        if rrtype == "A":
            return [_RData("203.0.113.5")]
        raise psh.dns.resolver.NoAnswer

    monkeypatch.setattr(psh.dns.resolver, "resolve", fake)
    cf, elsewhere, notices, transient = psh.classify_hostname_dns(
        "example.org", "s", True, [ipaddress.ip_network("104.16.0.0/12")], []
    )
    assert cf == 0
    assert elsewhere == 1


def test_transient_notice_routes_through_add_notice(psh, reset_sc, monkeypatch):
    # main() adds each returned notice via site_context.add_notice; verify it gains icon +
    # text defaults and lands in the list (the canonical SiteContext.add_notice path, P4).
    monkeypatch.setattr(
        psh.dns.resolver, "resolve",
        lambda hostname, rrtype: (_ for _ in ()).throw(psh.dns.resolver.Timeout),
    )
    _cf, _el, notices, _t = psh.classify_hostname_dns("h.example", "s", False, [], [])
    site_context = reset_sc.SiteContext({"name": "s"})
    for n in notices:
        site_context.add_notice(n)
    assert len(site_context["notices"]) == 1
    assert site_context["notices"][0]["icon"]   # filled from 'type'
    assert site_context["notices"][0]["text"]   # filled via html2text
