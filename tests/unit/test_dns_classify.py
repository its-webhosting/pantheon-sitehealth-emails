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
