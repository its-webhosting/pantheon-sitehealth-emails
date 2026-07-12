import dns.resolver
import pytest

from helpers.checkload import load_check_module
from helpers.dnsfake import patch_resolve

pytestmark = pytest.mark.unit


@pytest.fixture
def chain(psh, reset_sc, request):
    return load_check_module(psh, "pantheon_cdn_change", "chain", "pcc_chain_probe", request)


def test_normalize_and_predicates(chain):
    assert chain.normalize("LIVE-X.PantheonSite.io.") == "live-x.pantheonsite.io"
    assert chain.is_legacy_gcdn("LIVE-X.PantheonSite.io.") is True
    assert chain.is_legacy_gcdn("x.cdn.cloudflare.net") is False
    # A name that merely CONTAINS the string is not a legacy-GCDN name.
    assert chain.is_legacy_gcdn("pantheonsite.io.evil.example") is False
    assert chain.is_hostname("live-x.pantheonsite.io") is True
    assert chain.is_hostname("23.185.0.4") is False
    assert chain.is_hostname("2620:12a:8000::4") is False


def test_start_is_already_legacy_gcdn_no_queries(chain, monkeypatch):
    calls = []
    patch_resolve(monkeypatch, {}, calls)
    assert chain.walk("live-x.pantheonsite.io") == chain.ChainResult(
        "live-x.pantheonsite.io", False)
    assert calls == []          # a hit at depth 0 issues NO DNS query


def test_hit_at_depth_one(chain, monkeypatch):
    patch_resolve(monkeypatch,
                  {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]})
    assert chain.walk("occb.bus.umich.edu") == chain.ChainResult(
        "live-bus-occb.pantheonsite.io", False)


def test_hit_at_depth_three(chain, monkeypatch):
    patch_resolve(monkeypatch, {
        ("a.example.org", "CNAME"): ["b.example.org."],
        ("b.example.org", "CNAME"): ["c.example.org."],
        ("c.example.org", "CNAME"): ["live-x.pantheonsite.io."],
    })
    assert chain.walk("a.example.org").target == "live-x.pantheonsite.io"


def test_no_cname_is_no_hit(chain, monkeypatch):
    patch_resolve(monkeypatch, {})                       # missing key -> NoAnswer
    assert chain.walk("a.example.org") == chain.ChainResult("", False)


def test_nxdomain_is_no_hit(chain, monkeypatch):
    patch_resolve(monkeypatch, {("a.example.org", "CNAME"): dns.resolver.NXDOMAIN()})
    assert chain.walk("a.example.org") == chain.ChainResult("", False)


def test_chain_ending_off_pantheon_is_no_hit(chain, monkeypatch):
    # The real backstage.its.umich.edu shape: public DNS shows only the Cloudflare CNAME.
    patch_resolve(monkeypatch, {
        ("backstage.its.umich.edu", "CNAME"): ["backstage.its.umich.edu.cdn.cloudflare.net."],
    })
    assert chain.walk("backstage.its.umich.edu") == chain.ChainResult("", False)


@pytest.mark.parametrize("exc", [dns.resolver.Timeout(), dns.resolver.NoNameservers()])
def test_transient_is_unknown_not_a_hit(chain, monkeypatch, exc):
    patch_resolve(monkeypatch, {("a.example.org", "CNAME"): exc})
    assert chain.walk("a.example.org") == chain.ChainResult("", True)


def test_malformed_name_is_no_hit_and_does_not_raise(chain, monkeypatch):
    # F10: the named exception from the dns_classify seam (Task 2) must not escape the check.
    import dns_classify
    patch_resolve(monkeypatch,
                  {("a..b", "CNAME"): dns_classify.MalformedNameError("a..b: EmptyLabel")})
    assert chain.walk("a..b") == chain.ChainResult("", False)


def test_loop_is_no_hit_and_terminates(chain, monkeypatch):
    patch_resolve(monkeypatch, {
        ("a.example.org", "CNAME"): ["b.example.org."],
        ("b.example.org", "CNAME"): ["a.example.org."],
    })
    assert chain.walk("a.example.org") == chain.ChainResult("", False)


def test_depth_cap_is_no_hit_and_terminates(chain, monkeypatch):
    zone = {(f"h{i}.example.org", "CNAME"): [f"h{i + 1}.example.org."] for i in range(20)}
    patch_resolve(monkeypatch, zone)
    assert chain.walk("h0.example.org") == chain.ChainResult("", False)


def test_chain_does_not_resolve_addresses(chain):
    # SPEC §4.1: replacement addresses come from Pantheon (domain:dns), NEVER from resolving the
    # legacy-GCDN name -- a stale target belongs to a DIFFERENT Pantheon site.  Guard the rule.
    assert not hasattr(chain, "addresses")
