"""Offline tests for the find-platform-domains-dns utility (SPEC section 10).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone check/plugin modules (tests/integration/test_plugin_aws.py).  It is
loaded FRESH PER TEST so no module-level state leaks between tests.

Seams (SPEC section 9): `resolve` is monkeypatched on the loaded module; the API getter is
INJECTED as a parameter, never patched; httpx.MockTransport backs the ApiSession tests.
"""
# csv/io/httpx are unused until later tasks (Task 4's CSV-mechanics/injected-stream tests, Task
# 2's ApiSession/MockTransport tests); front-loaded here (PLAN.md Task 1 Step 3) so no later
# task appends an import mid-file and trips E402 -- see the module docstring's import-block note.
import csv  # noqa: F401
import importlib.util
import io  # noqa: F401
import struct
from importlib.machinery import SourceFileLoader
from pathlib import Path

import dns.resolver
import httpx  # noqa: F401
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
# -- seam, so without these two the copied code is never executed -- and copied code with its
# -- safety net removed is exactly where a transcription slip ships green (PD#14).  Ported from
# -- tests/unit/test_dns_classify.py, which covers the original.

def test_resolve_converts_a_malformed_name_into_the_named_exception(fpd):
    # An out-of-range byte escape: dns.name.from_text raises the stdlib struct.error, which is
    # not a DNSException at all, so nothing downstream would catch it.
    with pytest.raises(fpd.MalformedNameError):
        fpd.resolve("\\300.com", "CNAME")


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
