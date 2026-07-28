"""Offline tests for the find-platform-domains-dns utility (SPEC section 10).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone check/plugin modules (tests/integration/test_plugin_aws.py).  It is
loaded FRESH PER TEST so no module-level state leaks between tests.

Seams (SPEC section 9): `resolve` is monkeypatched on the loaded module; the API getter is
INJECTED as a parameter, never patched; httpx.MockTransport backs the ApiSession tests.
"""
import importlib.util
import struct
from importlib.machinery import SourceFileLoader
from pathlib import Path

import dns.resolver
import pytest
from helpers.dnsfake import make_resolver

pytestmark = pytest.mark.unit

# EVERY import for EVERY task in this file belongs in this block.  Later tasks append tests, not
# imports: ruff's E402 (module-level import not at top of file) is not in the tests/** ignore
# list, so an `import httpx` half way down the file fails the gate.

SCRIPT = Path(__file__).resolve().parent.parent.parent / "find-platform-domains-dns"


@pytest.fixture
def fpd():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs no sweep."""
    loader = SourceFileLoader("find_platform_domains_dns_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def patch_dns(monkeypatch, fpd, zone, calls=None):
    """Point the script's own `resolve` seam at a fake zone (helpers.dnsfake shape)."""
    monkeypatch.setattr(fpd, "resolve", make_resolver(zone, calls))


def test_normalize_and_is_platform_domain(fpd):
    assert fpd.normalize("  LIVE-X.PantheonSite.io. ") == "live-x.pantheonsite.io"
    assert fpd.is_platform_domain("LIVE-X.PantheonSite.io.") is True
    # A name that merely CONTAINS the suffix is not a platform domain.  BOTH forms matter:
    # the first has no leading dot, so it defeats only a naive endswith("pantheonsite.io");
    # the second embeds ".pantheonsite.io" exactly, so it is the one that catches a suffix
    # check wrongly written as a substring check.  This pair is the Task 1 red-proof target.
    assert fpd.is_platform_domain("pantheonsite.io.evil.example") is False
    assert fpd.is_platform_domain("x.pantheonsite.io.evil.example") is False
    assert fpd.is_platform_domain("fe.cfp2c.edge.pantheon.io") is False


def test_direct_hit_reports_the_custom_domain_as_the_dns_record(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd,
              {("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."]})
    assert fpd.walk("occb.bus.umich.edu") == fpd.WalkResult(
        "occb.bus.umich.edu", "live-bus-occb.pantheonsite.io", "")


def test_mid_chain_hit_reports_the_owner_of_the_hitting_record(fpd, monkeypatch):
    # THE point of the dns_record column: the record to rewrite is alias.umich.edu, not the
    # custom domain the site owner connected.
    patch_dns(monkeypatch, fpd, {
        ("www.example.umich.edu", "CNAME"): ["alias.umich.edu."],
        ("alias.umich.edu", "CNAME"): ["live-y.pantheonsite.io."],
    })
    assert fpd.walk("www.example.umich.edu") == fpd.WalkResult(
        "alias.umich.edu", "live-y.pantheonsite.io", "")


def test_no_cname_is_a_clean_no_hit(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {})          # absent key -> NoAnswer, the healthy shape
    assert fpd.walk("apex.umich.edu") == fpd.WalkResult("", "", "")


def test_nxdomain_is_a_clean_no_hit(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {("gone.umich.edu", "CNAME"): dns.resolver.NXDOMAIN()})
    assert fpd.walk("gone.umich.edu") == fpd.WalkResult("", "", "")


def test_migrated_domain_is_a_no_hit(fpd, monkeypatch):
    # Verified live: a migrated domain CNAMEs to the NEW CDN, which is not *.pantheonsite.io.
    patch_dns(monkeypatch, fpd,
              {("wws-test1.cdn-dev.it.umich.edu", "CNAME"): ["fe.cfp2c.edge.pantheon.io."]})
    assert fpd.walk("wws-test1.cdn-dev.it.umich.edu") == fpd.WalkResult("", "", "")


def test_transient_error_is_indeterminate_and_retried_once(fpd, monkeypatch):
    calls = []
    patch_dns(monkeypatch, fpd, {("x.umich.edu", "CNAME"): dns.resolver.Timeout()}, calls)
    result = fpd.walk("x.umich.edu")
    assert result.dns_record == ""
    assert "transient DNS error at x.umich.edu" in result.problem
    assert calls == [("x.umich.edu", "CNAME"), ("x.umich.edu", "CNAME")]  # retried exactly once


def test_no_nameservers_is_indeterminate_and_retried_once(fpd, monkeypatch):
    # The NoNameservers sibling of the test above (SPEC section 9's DNS_RETRY_SLEEP row): the
    # Timeout test above never executes the NoNameservers branch (:113-115) at all, so without
    # this test that branch -- including its retry -- has no coverage (PD#14).
    monkeypatch.setattr(fpd, "DNS_RETRY_SLEEP", 0)  # the suite must never actually sleep
    calls = []
    patch_dns(monkeypatch, fpd, {("y.umich.edu", "CNAME"): dns.resolver.NoNameservers()}, calls)
    result = fpd.walk("y.umich.edu")
    assert result.dns_record == ""
    assert "transient DNS error at y.umich.edu" in result.problem
    assert calls == [("y.umich.edu", "CNAME"), ("y.umich.edu", "CNAME")]  # retried exactly once


class _RetrySleepSpy:
    """A drop-in for DNS_RETRY_SLEEP that RECORDS being used as a sleep duration, without
    patching `time.sleep` itself (SPEC section 9: "there is no patching of time.sleep").

    CPython's time.sleep() converts its argument via `__index__` before falling back to a float
    conversion (verified empirically: a plain object implementing only `__index__` is accepted
    and the method is called). A spy that returns 0 from `__index__` is therefore observed on
    every call it participates in, and nothing actually sleeps -- so the assertion is on which
    branch asked to sleep, never on wall-clock time.
    """

    def __init__(self):
        self.times_slept = 0

    def __index__(self):
        self.times_slept += 1
        return 0


def test_transient_delay_asymmetry_only_no_nameservers_sleeps(fpd, monkeypatch):
    # SPEC section 6.2's asymmetry, pinned: a Timeout has already spent dnspython's own ~5s
    # lifetime, so it retries with NO added delay; NoNameservers comes back in ~0.3s, so it is
    # the one that gets DNS_RETRY_SLEEP before its retry.  Swapping which branch sleeps (the
    # mutation this test is red-capable against) would silently turn a burst of SERVFAILs back
    # into an immediate re-fire into the same rate limit (SPEC section 6.2).
    timeout_spy = _RetrySleepSpy()
    monkeypatch.setattr(fpd, "DNS_RETRY_SLEEP", timeout_spy)
    patch_dns(monkeypatch, fpd, {("timeout.umich.edu", "CNAME"): dns.resolver.Timeout()})
    fpd.walk("timeout.umich.edu")
    assert timeout_spy.times_slept == 0

    nns_spy = _RetrySleepSpy()
    monkeypatch.setattr(fpd, "DNS_RETRY_SLEEP", nns_spy)
    patch_dns(monkeypatch, fpd, {("nns.umich.edu", "CNAME"): dns.resolver.NoNameservers()})
    fpd.walk("nns.umich.edu")
    assert nns_spy.times_slept == 1


def test_malformed_name_is_indeterminate_not_a_crash(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd,
              {("a..b", "CNAME"): fpd.MalformedNameError("a..b: EmptyLabel")})
    assert "not a valid DNS name" in fpd.walk("a..b").problem


def test_cname_loop_is_indeterminate(fpd, monkeypatch):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["b.umich.edu."],
        ("b.umich.edu", "CNAME"): ["a.umich.edu."],
    })
    assert "loops at" in fpd.walk("a.umich.edu").problem


def test_chain_longer_than_the_hop_limit_is_indeterminate(fpd, monkeypatch):
    # patch_dns is NOT optional here: without it this test queries real DNS for h0.umich.edu,
    # returns a clean no-hit, and fails for a reason that has nothing to do with the hop limit.
    zone = {(f"h{i}.umich.edu", "CNAME"): [f"h{i + 1}.umich.edu."] for i in range(20)}
    patch_dns(monkeypatch, fpd, zone)
    assert "exceeds 8 hops" in fpd.walk("h0.umich.edu").problem


def test_custom_domain_that_is_itself_a_platform_domain_is_indeterminate(fpd, monkeypatch):
    calls = []
    patch_dns(monkeypatch, fpd, {}, calls)
    result = fpd.walk("live-x.pantheonsite.io")
    assert "itself a platform domain" in result.problem
    assert calls == []          # decided without a single DNS query


# -- The copied resolve() itself (SPEC section 10 item 9).  Every test above monkeypatches the
# -- seam, so without these three the copied code is never executed -- and copied code with its
# -- safety net removed is exactly where a transcription slip ships green (PD#14).  Ported from
# -- tests/unit/test_dns_classify.py, which covers the original.

def test_resolve_converts_a_malformed_name_into_the_named_exception(fpd):
    # An out-of-range byte escape: dns.name.from_text raises the stdlib struct.error, which is
    # not a DNSException at all, so nothing downstream would catch it.
    with pytest.raises(fpd.MalformedNameError):
        fpd.resolve("\\300.com", "CNAME")


def test_resolve_converts_a_real_idna_exception(fpd, monkeypatch):
    # dns.name.IDNAException derives from dns.exception.DNSException but NOT from SyntaxError, so
    # the resolve() clause that catches it (:61) is a SEPARATE except clause from the parse-time
    # one above -- deleting dns.name.IDNAException from that tuple leaves every other test here
    # green (ported from tests/unit/test_dns_classify.py::test_resolve_converts_a_real_idna_exception,
    # which found exactly that gap). IDNACodec.decode() raises it on an "xn--" label whose
    # punycode tail fails to decode -- a real, non-fabricated raise, confirmed by calling the
    # actual dnspython codec below -- but that decode() path is never reached by
    # dns.resolver.resolve(hostname, rrtype) for any hostname string (encoding a query name never
    # calls decode(); verified empirically against dnspython 2.8.0, which is what is pinned here).
    # So the underlying dns.resolver.resolve is monkeypatched to raise the SAME real exception
    # instance, to prove resolve()'s except clause converts it.
    real_exc = None
    try:
        fpd.dns.name.IDNA_2003_Practical.decode(b"xn--0")   # real raise, not hand-constructed
        pytest.fail("expected dns.name.IDNAException")
    except fpd.dns.name.IDNAException as e:
        real_exc = e   # exception-clause names are cleared on block exit -- rebind explicitly

    def boom(*_args, **_kwargs):
        raise real_exc

    monkeypatch.setattr(fpd.dns.resolver, "resolve", boom)
    with pytest.raises(fpd.MalformedNameError):
        fpd.resolve("xn--0.example.org", "A")


def test_wire_level_struct_error_is_transient_not_a_malformed_name(fpd, monkeypatch):
    # THE distinction SPEC section 6.3 calls load-bearing: dnspython also raises struct.error
    # from its TCP length-prefix unpack -- i.e. from garbled wire data on a perfectly valid
    # name.  Reporting that as "not a valid DNS name" would make the walk call it a definitive
    # answer, when it is a transient one.
    def boom(*_args, **_kwargs):
        raise struct.error("unpack requires a buffer of 2 bytes")

    monkeypatch.setattr(fpd.dns.resolver, "resolve", boom)
    with pytest.raises(dns.resolver.NoNameservers):
        fpd.resolve("valid.umich.edu", "CNAME")
