"""Offline tests for the find-platform-domains-dns utility (SPEC section 10).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone check/plugin modules (tests/integration/test_plugin_aws.py).  It is
loaded FRESH PER TEST so no module-level state leaks between tests.

Seams (SPEC section 9): `resolve` is monkeypatched on the loaded module; the API getter is
INJECTED as a parameter, never patched; httpx.MockTransport backs the ApiSession tests.
"""
import csv
import importlib.util
import io
import signal
import struct
from importlib.machinery import SourceFileLoader
from pathlib import Path

import dns.resolver
import httpx
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


@pytest.fixture(autouse=True)
def _restore_sigint_handler():
    """Fix round 2, N1 (Critical).  report_stop() calls the REAL `signal.signal(SIGINT,
    SIG_IGN)` for a real reason (m5, fix round 1) -- but a process's signal handler is global and
    outlives the test that set it.  Only the dedicated m5 test replaces the seam
    (`fpd.signal.signal`) with a recording stub that never touches the real handler; the other
    ten tests that reach report_stop() (directly or via main()) call the real one, so SIG_IGN
    leaked into the REST of the pytest session -- measured: still SIG_IGN after the whole --fast
    suite finished, 312 tests after the last leaking one.  This is a repo-wide test-isolation
    guard, not a per-test concern, so it is autouse and restores whatever handler was in place
    BEFORE this test ran, regardless of what the test itself (or the code under test) did to
    it -- it does not need to know about `fpd.signal.signal` at all, only about the process-level
    handler `signal.signal`/`signal.getsignal` observe.  Session-scoped would not work here: it
    would capture the ORIGINAL handler once, at the first test, and restore it only once, at the
    very end -- masking a leak between any two tests in between, which is exactly the shape of
    this defect.
    """
    original = signal.getsignal(signal.SIGINT)
    yield
    signal.signal(signal.SIGINT, original)


@pytest.fixture(scope="session", autouse=True)
def _sigint_handler_is_never_left_ignored_at_session_end():
    """Fix round 2, N1: the instrument that would have caught the leak the fixture above fixes.

    Deliberately SEPARATE from `_restore_sigint_handler` (which is function-scoped, restoring
    after each test): this one is session-scoped, so its teardown runs exactly once, at the very
    end of the WHOLE pytest session -- reproducing the shape the leak was actually measured in
    ("still SIG_IGN after the whole --fast suite finished"), not just "after the last test in
    this file." A per-test check would have passed throughout the leak's lifetime, since each
    individual leaking test finished with SIG_IGN still set and simply never got asked about it;
    the defect was only visible in the SESSION's final state, which is what this asserts on.
    """
    yield
    handler = signal.getsignal(signal.SIGINT)
    assert handler is not signal.SIG_IGN, (
        f"SIGINT is still SIG_IGN at the end of the pytest session ({handler!r}) -- something "
        "called the real signal.signal(SIGINT, SIG_IGN) (report_stop()'s m5 guard) without it "
        "being restored; see _restore_sigint_handler above")


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


# -- Task 2: Pantheon API session (SPEC section 9's ApiSession/retry/re-auth seams).

def make_session(fpd, handler, notify=None):
    """An ApiSession whose transport is a MockTransport running `handler`.

    No `import httpx` here -- it is in the import block at the top of the file (Task 1).
    """
    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)
    return fpd.ApiSession(client, "fake-machine-token", notify=notify)


def test_session_authenticates_once_at_construction(fpd):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"session": "sess-1"})

    session = make_session(fpd, handler)
    assert session.token == "sess-1"
    assert seen == ["https://api.pantheon.io/v0/authorize/machine-token"]


def test_get_returns_decoded_json(fpd):
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess-1"})
        assert request.headers["Authorization"] == "Bearer sess-1"
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler).get("/sites/abc") == {"ok": True}


def test_401_reauthenticates_once_then_succeeds(fpd):
    calls = []
    auth_headers_seen = []   # Fix round 1, I4: pin that the RETRIED request uses the NEW token

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": f"sess-{calls.count('/v0/authorize/machine-token')}"})
        auth_headers_seen.append(request.headers["Authorization"])
        if calls.count("/v0/sites/abc") == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    session = make_session(fpd, handler)
    assert session.get("/sites/abc") == {"ok": True}
    assert calls.count("/v0/authorize/machine-token") == 2   # re-authenticated exactly once
    assert session.token == "sess-2"
    assert auth_headers_seen == ["Bearer sess-1", "Bearer sess-2"]   # retry used the new token


def test_reauthentication_does_not_consume_the_transport_retry_budget(fpd, monkeypatch):
    # Fix round 1, I3: SPEC section 7.1 / the ApiSession docstring both say "a re-auth does
    # NOT consume the transport retry".  Sequence: 401 (re-auth) -> 500 (should still get its
    # own, unconsumed, transport retry) -> 200.  If a re-auth wrongly incremented
    # transport_attempts, the following 500 would look like the SECOND transport failure and
    # raise immediately instead of retrying -- exactly what the class docstring warns a
    # session expiring mid-sweep would silently do to the next real failure.
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    site_calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess-2"})
        site_calls.append(1)
        n = len(site_calls)
        if n == 1:
            return httpx.Response(401, json={"error": "expired"})
        if n == 2:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler).get("/sites/abc") == {"ok": True}
    assert len(site_calls) == 3


def test_401_twice_raises_session_expired_not_a_plain_api_error(fpd):
    # SPEC G7a.  It must NOT be a PantheonApiError: the sweep catches those per site, so a
    # revoked token would otherwise turn into ~400 indeterminates instead of an abort.
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(401, json={"error": "nope"})

    with pytest.raises(fpd.SessionExpiredError, match="expired or revoked"):
        make_session(fpd, handler).get("/sites/abc")
    assert not issubclass(fpd.SessionExpiredError, fpd.PantheonApiError)


def test_failure_to_reauthenticate_is_also_session_expired(fpd):
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            calls.append(1)
            # The first (constructor) authentication succeeds; the mid-sweep one fails.
            return httpx.Response(200, json={"session": "sess"}) if len(calls) == 1 \
                else httpx.Response(403, text="revoked")
        return httpx.Response(401, json={"error": "expired"})

    with pytest.raises(fpd.SessionExpiredError, match="could not re-authenticate"):
        make_session(fpd, handler).get("/sites/abc")


def test_reauthentication_notifies_the_caller(fpd):
    # SPEC section 8: the G7 note is the operator's only sign that the session expired.
    notes = []
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": f"sess-{calls.count('/v0/authorize/machine-token')}"})
        if calls.count("/v0/sites/abc") == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler, notify=notes.append).get("/sites/abc") == {"ok": True}
    assert notes == ["session expired; re-authenticated"]


def test_500_is_retried_once_then_succeeds(fpd, monkeypatch):
    # Fix round 1, I2: a plain `0` proves only "the suite doesn't sleep" -- it cannot tell
    # apart a retry that sleeps RETRY_SLEEP from one that was deleted outright.  The spy
    # (reused from Task 1, not re-invented) records whether RETRY_SLEEP was actually consumed
    # as a sleep duration.
    spy = _RetrySleepSpy()
    monkeypatch.setattr(fpd, "RETRY_SLEEP", spy)
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"ok": True})

    assert make_session(fpd, handler).get("/sites/abc") == {"ok": True}
    assert len(calls) == 2
    assert spy.times_slept == 1


def test_500_twice_raises_named_error(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    calls = []  # Fix round 1, I1: pin the retry COUNT, not just that it eventually raises.

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        return httpx.Response(500, text="boom")

    with pytest.raises(fpd.PantheonApiError, match="500"):
        make_session(fpd, handler).get("/sites/abc")
    assert len(calls) == 2   # exactly one retry, not a widened/unbounded attempt count


def test_429_is_retried_like_a_5xx(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        return httpx.Response(429 if len(calls) == 1 else 200, json={"ok": True})

    assert make_session(fpd, handler).get("/x") == {"ok": True}
    assert len(calls) == 2


def test_connect_error_is_retried_once_then_raises_named_error(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    calls = []

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        calls.append(1)
        raise httpx.ConnectError("no route")

    with pytest.raises(fpd.PantheonApiError, match="no route"):
        make_session(fpd, handler).get("/x")
    assert len(calls) == 2


def test_undecodable_body_raises_named_error(fpd):
    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(fpd.PantheonApiError):
        make_session(fpd, handler).get("/x")


def test_neither_token_nor_response_body_ever_leaks_into_error_text(fpd, monkeypatch):
    # Fix round 1, C1 (extended in fix round 2 to add the undecodable-body case the round-1
    # version substituted a generic-status case for instead).  SPEC section 3's threat model,
    # property (a): neither the machine token nor the session token, nor any response body, is
    # ever visible in an exception's message or its chained cause.  Instrumented here (PD#14),
    # not asserted in prose, at THIS task's own ApiSession seam -- no main() is needed, and
    # SPEC section 10 item 12's main()-driven G7a/G5 version is still owed by Task 5; this does
    # not discharge it.  Covers the FOUR message-construction sites a mutation could slip a
    # response body into: the auth non-200 branch, the 5xx-exhausted branch, the generic (not
    # 401/429/5xx/200) GET-status branch, and the undecodable-(as JSON)-body branch -- the
    # shape SPEC section 8's cleartext-credential warning describes.  Also pins property (b):
    # the machine token travels in the POST body, never on the URL.
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    machine_token_sentinel = "MACHINE-TOKEN-sentinel"
    body_sentinel = "OTHER-PEOPLES-PASSWORD-sentinel"

    def assert_sentinels_absent(exc):
        assert machine_token_sentinel not in str(exc)
        assert body_sentinel not in str(exc)
        if exc.__cause__ is not None:
            assert machine_token_sentinel not in repr(exc.__cause__)
            assert body_sentinel not in repr(exc.__cause__)

    # -- auth non-200: the token exchange itself fails.
    auth_requests = []

    def auth_failure_handler(request):
        auth_requests.append(request)
        return httpx.Response(403, text=f"forbidden: {body_sentinel}")

    client = httpx.Client(transport=httpx.MockTransport(auth_failure_handler), timeout=1.0)
    with pytest.raises(fpd.PantheonApiError) as excinfo:
        fpd.ApiSession(client, machine_token_sentinel)
    assert_sentinels_absent(excinfo.value)

    # property (b): the token travels in the POST body, never on the URL.
    assert auth_requests[0].method == "POST"
    assert machine_token_sentinel.encode() in auth_requests[0].content
    assert machine_token_sentinel not in str(auth_requests[0].url)

    # -- 5xx-exhausted: the token exchange succeeds; the GET fails twice.
    def five_xx_handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(500, text=f"internal error: {body_sentinel}")

    with pytest.raises(fpd.PantheonApiError) as excinfo:
        make_session(fpd, five_xx_handler).get("/sites/abc")
    assert_sentinels_absent(excinfo.value)

    # -- generic non-200 GET status: neither a retry status nor 200 -- e.g. a 403 whose body
    # is plain, undecodable-as-anything-useful text.
    def other_status_handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(403, text=f"forbidden: {body_sentinel}")

    with pytest.raises(fpd.PantheonApiError) as excinfo:
        make_session(fpd, other_status_handler).get("/sites/abc")
    assert_sentinels_absent(excinfo.value)

    # -- undecodable body (fix round 2): a 200 response whose body is not valid JSON at all --
    # the json.JSONDecodeError branch, distinct from every case above (all of which raise on a
    # non-200 status without ever calling response.json()).
    def undecodable_body_handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        return httpx.Response(200, text=f"<html>{body_sentinel}</html>")

    with pytest.raises(fpd.PantheonApiError) as excinfo:
        make_session(fpd, undecodable_body_handler).get("/sites/abc")
    assert_sentinels_absent(excinfo.value)


def test_machine_token_prefers_the_environment(fpd, monkeypatch):
    monkeypatch.setenv("PANTHEON_MACHINE_TOKEN", "from-env")
    assert fpd.machine_token() == "from-env"


def test_machine_token_reads_the_single_terminus_cache_file(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text('{"token": "from-cache", "email": "x"}')
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    assert fpd.machine_token() == "from-cache"


def test_machine_token_refuses_to_guess_between_several_cache_files(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "a@umich.edu").write_text('{"token": "a"}')
    (cache / "b@umich.edu").write_text('{"token": "b"}')
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="found 2"):
        fpd.machine_token()


def test_machine_token_missing_cache_directory_is_named(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError):
        fpd.machine_token()


def test_machine_token_undecodable_cache_file_is_named(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text("this is not json")
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="could not read"):
        fpd.machine_token()


def test_machine_token_cache_file_without_a_token_key_is_named(fpd, monkeypatch, tmp_path):
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text('{"email": "someone@umich.edu"}')
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="no 'token' key"):
        fpd.machine_token()


def test_machine_token_cache_file_holding_a_non_object_json_value_is_named(fpd, monkeypatch, tmp_path):
    # Fix round 1, M1: a truncated Terminus cache write can leave a cache file holding valid
    # JSON that is not a container at all (null/123/true/a bare string) -- "token" not in data
    # then raises a bare, unnamed TypeError ("argument of type 'NoneType' is not iterable"),
    # not the named MachineTokenError SPEC G2 requires.
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    (cache / "someone@umich.edu").write_text("null")
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match="no 'token' key"):
        fpd.machine_token()


def test_machine_token_empty_cache_directory_is_named(fpd, monkeypatch, tmp_path):
    # Fix round 1, M4: an EXISTING but empty tokens/ directory (0 files) is a distinct shadow
    # from the missing-directory case above, and exercises the `or 'none'` fallback in the
    # "found 0 (...)" message.
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(fpd.MachineTokenError, match=r"found 0 \(none\)"):
        fpd.machine_token()


def test_machine_token_unreadable_cache_directory_is_named(fpd, monkeypatch, tmp_path):
    """Fix round 1, C1 (SPEC G2's "unreadable ... is an error" branch, applied to the directory
    itself, not just a file inside it).  `cache.iterdir()` sat outside any try/except: an
    unreadable ~/.terminus/cache/tokens (e.g. left root-owned by a `sudo terminus auth:login`)
    raised an ordinary PermissionError -- an OSError -- straight out of machine_token(), which
    prepare_sweep's `except (MachineTokenError, PantheonApiError)` guard does not catch, so it
    escaped main() entirely as an unnamed exit-1 traceback (SPEC section 7 reserves 1 for
    "completed with indeterminates").
    """
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    cache = tmp_path / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    cache.chmod(0o000)
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: tmp_path))
    try:
        with pytest.raises(fpd.MachineTokenError, match="could not list"):
            fpd.machine_token()
    finally:
        cache.chmod(0o755)     # so tmp_path's own cleanup can remove the directory afterward


def test_main_returns_2_when_the_machine_token_cache_is_unreadable(fpd, monkeypatch, tmp_path,
                                                                   capsys):
    """Fix round 1, C1: the fix must actually reach main(), not just machine_token() in
    isolation -- prepare_sweep's except tuple is the seam that would otherwise let a
    PermissionError from this specific path escape uncaught.  Drives the REAL build_session() and
    machine_token() (neither is monkeypatched here) so the real prepare_sweep guard is exercised.
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    home = tmp_path / "home"
    cache = home / ".terminus" / "cache" / "tokens"
    cache.mkdir(parents=True)
    cache.chmod(0o000)
    monkeypatch.delenv("PANTHEON_MACHINE_TOKEN", raising=False)
    monkeypatch.setattr(fpd.Path, "home", staticmethod(lambda: home))
    try:
        assert fpd.main(["-c", str(config)]) == 2
    finally:
        cache.chmod(0o755)
    assert "could not list" in capsys.readouterr().err


def fake_site(n):
    # The membership id deliberately DIFFERS from the site id.  In production they are equal for
    # all 408 sites, but SPEC section 4.1 says that equality "is an observation, not a contract"
    # and requires the cursor to be site.id -- so the fixture must be able to tell them apart,
    # or the one decision that section argues for has no red-capable test (PD#14).
    return {"id": f"mem-{n:04d}", "site": {"id": f"id-{n:04d}", "name": f"site-{n:04d}"}}


class PagedGet:
    """A fake `get` returning canned site-list pages in order; records every path requested.

    A callable class rather than a function-with-bolted-on-attribute (fix round 1, M3): the
    `_RetrySleepSpy` above is the file's existing precedent for this shape, a plain function
    decorated with `.cursors` trips pyright's reportFunctionMemberAccess wherever this file is
    later brought under pyright (it isn't today, but nothing should rely on that), and one
    object holding both `.paths` (M1: pins the request path, not just its cursor) and
    `.cursors` (derived, for the existing cursor-sequence assertions) is one model instead of
    a closure plus an attribute bolted onto it.
    """

    def __init__(self, pages):
        self.pages = pages
        self.paths = []
        self.cursors = []

    def __call__(self, path):
        self.paths.append(path)
        cursor = path.split("start=")[1] if "start=" in path else None
        self.cursors.append(cursor)
        assert self.pages, "the code requested more pages than this test provided"
        return self.pages.pop(0)


def test_org_sites_quotes_the_org_id_in_the_url(fpd):
    """Fix round 1, m3.  org_id is read straight from TOML and reaches this URL unquoted before
    this fix: an org_id containing '#' or '?' (a config typo, not necessarily hostile) silently
    requested a DIFFERENT resource (`/organizations/abc` for `org_id = "abc#frag"`) rather than
    failing loudly.  quote(org_id, safe="") closes that -- SPEC section 3 already requires this
    for the SITE argv; org_id gets the same treatment for the same reason.
    """
    get = PagedGet([[]])
    fpd.org_sites(get, "abc#frag?x=1")
    assert get.paths == ["/organizations/abc%23frag%3Fx%3D1/memberships/sites?limit=100"]


def test_org_sites_walks_every_page(fpd):
    pages = [[fake_site(n) for n in range(100)],
             [fake_site(n) for n in range(100, 200)],
             [fake_site(n) for n in range(200, 208)]]
    get = PagedGet(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 208
    assert sites[0] == {"id": "id-0000", "name": "site-0000"}
    assert sites[-1]["name"] == "site-0207"
    # The cursor is the LAST *site* id of the previous FULL page -- "id-0099", never the
    # membership id "mem-0099" (SPEC section 4.1).
    assert get.cursors == [None, "id-0099", "id-0199"]
    # Fix round 1, M1: the cursor-substring extraction above would stay green even if the org
    # id were dropped from the path, or "/memberships/sites" were typo'd -- pin the first
    # request's full path too (named_sites already does this for its own path, at :693).
    assert get.paths[0] == "/organizations/org-1/memberships/sites?limit=100"


def test_org_sites_stops_on_a_short_first_page(fpd):
    get = PagedGet([[fake_site(n) for n in range(3)]])
    assert len(fpd.org_sites(get, "org-1")) == 3
    assert get.cursors == [None]


def test_org_sites_handles_an_empty_organization(fpd):
    get = PagedGet([[]])
    assert fpd.org_sites(get, "org-1") == []


def test_org_sites_handles_a_site_count_that_is_an_exact_multiple_of_the_page_size(fpd):
    # SPEC section 4.1: the FINAL boundary cursor really does return [] (verified live, 7/7).
    # An organization with exactly 200 sites therefore ends on an empty page, which must
    # terminate the loop normally -- NOT trip the zero-new-ids reset detector, which would
    # turn a perfectly good listing into a fatal error.
    pages = [[fake_site(n) for n in range(100)],
             [fake_site(n) for n in range(100, 200)],
             []]
    get = PagedGet(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 200
    assert get.cursors == [None, "id-0099", "id-0199"]


def test_org_sites_retries_an_ignored_cursor_then_succeeds(fpd, monkeypatch, capsys):
    # SPEC section 4.1: the API sometimes ignores `start` and returns page 1 again.  The loop must
    # notice (zero new ids) and retry the SAME cursor -- not spin, not truncate.
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    pages = [page1, list(page1), [fake_site(n) for n in range(100, 105)]]
    get = PagedGet(pages)
    sites = fpd.org_sites(get, "org-1")
    assert len(sites) == 105
    assert get.cursors == [None, "id-0099", "id-0099"]     # same cursor, retried
    # The ATTENTION line is the ONLY thing that distinguishes a detector-driven retry from a
    # loop that blunders into repeating the same cursor by accident -- both produce the cursor
    # sequence above, so without this assertion the test passes with the detector deleted.
    assert "cursor id-0099 was ignored" in capsys.readouterr().err


def test_ignored_cursor_retry_uses_the_retry_prefix_not_skipped(fpd, monkeypatch, capsys):
    """SPEC section 8, fix round 1 (R1): SKIPPED: is defined as "produced no row and WAS counted
    as indeterminate", but this retry line is never counted anywhere -- it fires entirely inside
    org_sites()/prepare_sweep(), before any Counters object exists, and prints nothing further at
    all if the retry goes on to succeed.  Reusing SKIPPED: broke the one property it exists to
    guarantee: `grep -c SKIPPED` reconciling exactly against the final `indeterminate=N`.  A
    dedicated RETRY: prefix keeps that reconciliation exact.
    """
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    pages = [page1, list(page1), [fake_site(n) for n in range(100, 105)]]
    fpd.org_sites(PagedGet(pages), "org-1")
    err = capsys.readouterr().err
    assert "RETRY: site listing cursor id-0099 was ignored" in err
    assert "SKIPPED:" not in err


def test_org_sites_gives_up_loudly_when_the_cursor_stays_ignored(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    page1 = [fake_site(n) for n in range(100)]
    # A fifth, short page is provided deliberately.  With the detector the loop never reaches
    # it (it raises after the third ignored page).  WITHOUT the detector the loop consumes it
    # and returns normally -- so the failure is a clean "DID NOT RAISE" rather than an
    # IndexError from a test fixture running out of canned pages.
    get = PagedGet([page1, list(page1), list(page1), list(page1),
                     [fake_site(n) for n in range(100, 105)]])
    with pytest.raises(fpd.SiteListingError, match="cursor") as excinfo:
        fpd.org_sites(get, "org-1")
    assert len(get.cursors) == 4      # first page + CURSOR_ATTEMPTS retries, then it stops
    # The fatal message MUST carry the real org id: it names a `terminus org:site:list <org_id>`
    # cross-check (SPEC section 4.1/G4a), and that command is a positional-argument usage error
    # without it (verified live: "Not enough arguments (missing: \"organization\")").
    assert "org-1" in str(excinfo.value)


def test_org_sites_caps_the_page_loop(fpd, monkeypatch):
    monkeypatch.setattr(fpd, "MAX_PAGES", 3)
    counter = {"n": 0}

    def get(path):
        counter["n"] += 1
        base = counter["n"] * 100
        return [fake_site(n) for n in range(base, base + 100)]

    with pytest.raises(fpd.SiteListingError, match="page"):
        fpd.org_sites(get, "org-1")


def test_named_sites_resolves_each_name_and_prefers_the_canonical_name(fpd):
    def get(path):
        assert path.startswith("/site-names/")
        slug = path.rsplit("/", 1)[1]
        # The real endpoint returns the canonical name alongside the id (verified live).
        return {"id": "uuid-" + slug, "name": slug.lower()}

    assert fpd.named_sites(get, ["Alpha", "beta"]) == [
        {"id": "uuid-Alpha", "name": "alpha"},   # canonical name wins over the argv casing
        {"id": "uuid-beta", "name": "beta"},
    ]


def test_named_sites_percent_encodes_the_site_name(fpd):
    seen = []

    def get(path):
        seen.append(path)
        return {"id": "uuid", "name": "x"}

    fpd.named_sites(get, ["we#ird/name?x"])
    # Unencoded, '#' would truncate the path and '?' would start a query string, silently
    # requesting a different resource instead of failing.
    assert seen == ["/site-names/we%23ird%2Fname%3Fx"]


def test_unexpected_response_shapes_raise_the_named_error(fpd):
    # SPEC G17: a bare KeyError here would be an uncaught traceback exiting 1, which section 7
    # reserves for "completed with indeterminates".
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: {"not": "a list"}, "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: [{"no_site_key": 1}], "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.site_environments(lambda _path: ["dev", "live"], "abc")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.partition_domains({"not": "a list"})
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.named_sites(lambda _path: {"no": "id"}, ["alpha"])
    # The keys the SWEEP reads later, not just the ones the listing reads: a bare KeyError on
    # site["name"] escapes main() entirely and exits 1 (SPEC section 10 item 16).
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: [{"site": {"id": "u1"}}], "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.named_sites(lambda _path: {"id": "uuid"}, ["alpha"])
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.partition_domains(["a-string-not-an-object"])
    # Fix round 1, main-review M2: `_require` only guards PRESENCE, not type.  A wrongly-typed
    # `site.id` used later as a dict key (`collected[site["id"]]`) raised a bare, unnamed
    # `TypeError: unhashable type: 'list'` -- an uncaught exit-1 traceback in a program where
    # exit 1 is reserved for "completed with indeterminates" (SPEC G17: "a missing/wrongly-typed
    # key").
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: [{"site": {"id": ["not-a-string"], "name": "n"}}], "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.org_sites(lambda _path: [{"site": {"id": "u1", "name": ["not-a-string"]}}], "org-1")
    with pytest.raises(fpd.PantheonApiShapeError):
        fpd.partition_domains([{"id": ["not-a-string"], "type": "custom"}])


def test_partition_domains_splits_custom_from_platform(fpd):
    entries = [
        {"id": "live-its-wws-test1.pantheonsite.io", "type": "platform"},
        {"id": "WWS-test1.cdn-dev.it.umich.edu", "type": "custom", "primary": True},
        {"id": "www.wws-test1.cdn-dev.it.umich.edu", "type": "custom", "primary": False},
    ]
    custom, platform, unknown = fpd.partition_domains(entries)
    # Primary domains ARE included, and everything is normalized.
    assert custom == ["wws-test1.cdn-dev.it.umich.edu", "www.wws-test1.cdn-dev.it.umich.edu"]
    assert platform == {"live-its-wws-test1.pantheonsite.io"}
    assert unknown == []


def test_partition_domains_of_an_uninitialized_environment(fpd):
    entries = [{"id": "live-vpao-accopp.pantheonsite.io", "type": "platform"}]
    assert fpd.partition_domains(entries) == ([], {"live-vpao-accopp.pantheonsite.io"}, [])


def test_partition_domains_reports_an_unknown_type_instead_of_dropping_it(fpd):
    # SPEC G6a.  `custom`/`platform` is an observation, not a documented enumeration, and a
    # silently dropped domain is the one failure the CSV cannot reveal (SPEC section 1).
    entries = [
        {"id": "live-s.pantheonsite.io", "type": "platform"},
        {"id": "something.umich.edu", "type": "brand-new-type"},
    ]
    custom, _platform, unknown = fpd.partition_domains(entries)
    assert custom == []
    assert unknown == [("something.umich.edu", "brand-new-type")]


def test_site_environments_returns_every_environment(fpd):
    def get(path):
        assert path == "/sites/abc/environments"
        return {"dev": {"initialized": True}, "live": {"initialized": False},
                "test-mark": {"initialized": True}}

    assert sorted(fpd.site_environments(get, "abc")) == ["dev", "live", "test-mark"]


def make_sweeper(fpd, get=None, *, verbose=False):
    """A Sweeper writing into an in-memory stream.

    `verbose` is keyword-only: ruff's FBT002 rejects a boolean positional default, and the
    tests/** per-file-ignores block covers FBT003 (positional bools at call sites), not FBT002.
    No `import csv`/`import io` here -- they are in the top-of-file import block (Task 1).
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    sweeper = fpd.Sweeper(get or (lambda path: {}), writer, out, verbose=verbose)
    return sweeper, out


def test_clean_hit_writes_exactly_the_five_fields(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("occb.bus.umich.edu", "CNAME"): ["live-bus-occb.pantheonsite.io."],
        ("live-bus-occb.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "uuid", "name": "bus-occb"}, "live", "occb.bus.umich.edu",
                         {"live-bus-occb.pantheonsite.io"})
    assert out.getvalue() == (
        "bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io\n")
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0
    assert capsys.readouterr().err == ""      # a clean hit says nothing at all


def test_csv_uses_unix_line_endings(fpd, monkeypatch):
    # Fix round 1, I3: this pins ONLY the `csv.writer(..., lineterminator="\n")` configuration
    # that THIS TEST's own `make_sweeper` helper constructs (tests:817-824) -- the script itself
    # contains no `csv.writer` call at all, since the writer is injected by the caller (SPEC
    # section 9). The production pin -- that `main()` actually constructs its writer with
    # `lineterminator="\n"` over real `sys.stdout` -- has no seam here and is a required Task 5
    # deliverable (`"\r" not in` captured stdout from a real `main()` invocation).
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-x.pantheonsite.io."],
        ("live-x.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-x.pantheonsite.io"})
    assert "\r" not in out.getvalue()


def test_indeterminate_domain_reports_and_counts_but_writes_no_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {("a.umich.edu", "CNAME"): dns.resolver.Timeout()})
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu", set())
    assert out.getvalue() == ""
    assert sweeper.counters.indeterminate == 1
    err = capsys.readouterr().err
    # SKIPPED:, not WARNING: -- this domain produced no row and WAS counted (SPEC section 8).
    assert err.startswith("SKIPPED:")
    assert "s.live" in err and "a.umich.edu" in err


def test_dead_platform_domain_warns_but_still_writes_the_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {("a.umich.edu", "CNAME"): ["live-gone.pantheonsite.io."]})
    #  ^ no A or AAAA for live-gone -> NoAnswer for both -> definitively dead
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-gone.pantheonsite.io"})
    assert out.getvalue().strip().endswith("live-gone.pantheonsite.io")
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0        # a warning, NOT an indeterminate
    assert "does not resolve" in capsys.readouterr().err


def test_transient_lookup_of_the_platform_domain_does_not_warn(fpd, monkeypatch, capsys):
    # The dead-target check exists to warn; it must never cry wolf on a blip (SPEC G12).
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-x.pantheonsite.io."],
        ("live-x.pantheonsite.io", "A"): dns.resolver.Timeout(),
    })
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-x.pantheonsite.io"})
    assert sweeper.counters.rows == 1
    assert "does not resolve" not in capsys.readouterr().err


def test_cross_site_target_warns_but_still_writes_the_row(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-other.pantheonsite.io."],
        ("live-other.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert sweeper.counters.rows == 1
    assert sweeper.counters.indeterminate == 0
    err = capsys.readouterr().err
    assert "different site" in err and "live-s.pantheonsite.io" in err


def test_mid_chain_hit_warns_that_the_record_is_an_alias(fpd, monkeypatch, capsys):
    # SPEC G13a.  Rewriting alias.umich.edu moves every other name pointing at it.
    patch_dns(monkeypatch, fpd, {
        ("www.example.umich.edu", "CNAME"): ["alias.umich.edu."],
        ("alias.umich.edu", "CNAME"): ["live-s.pantheonsite.io."],
        ("live-s.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "www.example.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert out.getvalue().split(",")[3] == "alias.umich.edu"
    err = capsys.readouterr().err
    assert "the record to change is alias.umich.edu" in err
    assert sweeper.counters.rows == 1


def test_direct_hit_does_not_warn_about_an_alias(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-s.pantheonsite.io."],
        ("live-s.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert "the record to change is" not in capsys.readouterr().err


def test_each_row_is_flushed_as_it_is_written(fpd, monkeypatch):
    # SPEC section 5: a 38-minute sweep must be watchable with tail -f.  Testable only because
    # the stream is injected (SPEC section 9).
    flushes = []
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-s.pantheonsite.io."],
        ("live-s.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, out = make_sweeper(fpd)
    monkeypatch.setattr(out, "flush", lambda: flushes.append(len(out.getvalue())))
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu",
                         {"live-s.pantheonsite.io"})
    assert len(flushes) == 1
    assert flushes[0] > 0        # flushed AFTER the row was written, not before


def test_verbose_reports_per_site_counts(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})
    responses = {
        "/sites/uuid/environments": {"dev": {}, "live": {}},
        "/sites/uuid/environments/dev/domains": [
            {"id": "dev-s.pantheonsite.io", "type": "platform"}],
        "/sites/uuid/environments/live/domains": [
            {"id": "live-s.pantheonsite.io", "type": "platform"},
            {"id": "a.umich.edu", "type": "custom"}],
    }
    sweeper, _out = make_sweeper(fpd, get=lambda path: responses[path], verbose=True)
    sweeper.sweep_site({"id": "uuid", "name": "s"})
    assert "s: 2 environments, 1 custom domains" in capsys.readouterr().err


def test_a_session_expiry_aborts_the_sweep_instead_of_counting_indeterminates(fpd, monkeypatch):
    # SPEC G7a.  If SessionExpiredError were caught per site, a revoked token 5 minutes into a
    # 38-minute sweep would emit ~400 ATTENTION lines and exit 1 instead of stopping.
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        raise fpd.SessionExpiredError("token revoked")

    sweeper, _out = make_sweeper(fpd, get=get)
    with pytest.raises(fpd.SessionExpiredError):
        sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.counters.indeterminate == 0
    # Fix round 1, I1.  SPEC section 7.3's "Stopped after <site>" / "Stopped during <site>" split
    # depends on `last_site` meaning ONLY a site that COMPLETED -- s1 never completed here, so
    # last_site must still be empty and current_site must name the site in flight.  Moving the
    # `self.last_site = site["name"]` assignment above `self.sweep_site(site)` in `sweep()`
    # passed all 67 tests before these two assertions existed.
    assert sweeper.last_site == ""
    assert sweeper.current_site == "s1"


def test_a_malformed_domains_payload_is_one_environments_indeterminate(fpd, monkeypatch, capsys):
    # SPEC G17 + section 10 item 17.  partition_domains sits INSIDE sweep_env's try; outside
    # it, one malformed payload aborted every remaining site of a 38-minute sweep.
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        if path.endswith("/environments"):
            return {"live": {}}
        return {"not": "a list"} if "/u1/" in path else []

    sweeper, _out = make_sweeper(fpd, get=get)
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.counters.sites == 2          # it kept going
    assert sweeper.counters.indeterminate == 1
    assert "SKIPPED: s1.live: could not list domains" in capsys.readouterr().err


def test_sweep_records_where_it_stopped(fpd, monkeypatch):
    # SPEC section 7.3: without this an aborted 38-minute sweep gives the operator no way to
    # resume except starting over.
    patch_dns(monkeypatch, fpd, {})
    sweeper, _out = make_sweeper(
        fpd, get=lambda path: {} if path.endswith("environments") else [])
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.last_site == "s2"
    assert sweeper.remaining == []


def test_sweep_site_counts_environments_and_domains(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})     # every domain is a clean no-hit
    responses = {
        "/sites/uuid/environments": {"dev": {}, "live": {}},
        "/sites/uuid/environments/dev/domains": [
            {"id": "dev-s.pantheonsite.io", "type": "platform"}],
        "/sites/uuid/environments/live/domains": [
            {"id": "live-s.pantheonsite.io", "type": "platform"},
            {"id": "a.umich.edu", "type": "custom"}],
    }
    sweeper, out = make_sweeper(fpd, get=lambda path: responses[path])       # verbose=False
    sweeper.sweep_site({"id": "uuid", "name": "s"})
    assert (sweeper.counters.sites, sweeper.counters.envs, sweeper.counters.custom_domains) == (1, 2, 1)
    assert out.getvalue() == ""
    # Fix round 1, I2.  The per-site progress/summary lines are "stderr, -v only" (SPEC
    # section 8); deleting the `if self._verbose:` gate in `_progress` passed all 67 tests
    # before this assertion existed, since every prior -v test ran with verbose=True.
    assert capsys.readouterr().err == ""


def test_failed_environment_listing_counts_once_and_continues(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        raise fpd.PantheonApiError("HTTP 500")

    sweeper, _ = make_sweeper(fpd, get=get)
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    assert sweeper.counters.indeterminate == 2        # once per site, and it kept going
    assert sweeper.counters.sites == 2
    assert "could not list environments" in capsys.readouterr().err


def test_failed_domain_listing_counts_once_and_continues_to_the_next_environment(fpd, monkeypatch, capsys):
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        if path.endswith("/environments"):
            return {"dev": {}, "live": {}}
        if "/dev/" in path:
            raise fpd.PantheonApiError("HTTP 503")
        return [{"id": "live-s.pantheonsite.io", "type": "platform"}]

    sweeper, _ = make_sweeper(fpd, get=get)
    sweeper.sweep_site({"id": "u", "name": "s"})
    assert sweeper.counters.indeterminate == 1
    assert sweeper.counters.envs == 2
    assert "could not list domains" in capsys.readouterr().err


def test_sweep_env_reports_and_counts_an_unknown_domain_type(fpd, monkeypatch, capsys):
    # Fix round 1, C1 (SPEC G6a / section 10 item 18).  The reviewer's mutation -- rename the
    # loop variable `unknown` to `_unknown` and delete the four-line report-and-count loop --
    # passed all 67 tests before this test existed, because none of the tests claimed as
    # covering it actually reached `sweep_env` with an unrecognized `type` entry.
    patch_dns(monkeypatch, fpd, {})

    def get(path):
        return [{"id": "live-s.pantheonsite.io", "type": "platform"},
                {"id": "x.umich.edu", "type": "brand-new-type"}]

    sweeper, _out = make_sweeper(fpd, get=get)
    sweeper.sweep_env({"id": "u", "name": "s"}, "live")
    err = capsys.readouterr().err
    assert "unknown domain type" in err
    assert sweeper.counters.indeterminate == 1
    assert sweeper.counters.custom_domains == 0


def test_verbose_sweep_prints_the_per_site_progress_counter(fpd, monkeypatch, capsys):
    # Fix round 1, M1 (SPEC section 8's `[12/408] bus-occb`).  `test_verbose_reports_per_site_
    # counts` only calls `sweep_site` directly and never exercises `sweep()`'s own progress
    # line, so deleting it passed all 67 tests.
    patch_dns(monkeypatch, fpd, {})
    sweeper, _out = make_sweeper(
        fpd, get=lambda path: {} if path.endswith("environments") else [], verbose=True)
    sweeper.sweep([{"id": "u1", "name": "s1"}, {"id": "u2", "name": "s2"}])
    err = capsys.readouterr().err
    assert "[1/2] s1" in err
    assert "[2/2] s2" in err


def test_cross_site_warning_with_no_platform_domains_reports_none_listed(fpd, monkeypatch, capsys):
    # Fix round 1, M2 (SPEC section 7.2's traced empty-platform-set shadow): an environment
    # whose OWN `type: platform` set is empty still gets a useful "expected one of" message,
    # not a bare trailing "()".
    patch_dns(monkeypatch, fpd, {
        ("a.umich.edu", "CNAME"): ["live-other.pantheonsite.io."],
        ("live-other.pantheonsite.io", "A"): ["23.185.0.4"],
    })
    sweeper, _out = make_sweeper(fpd)
    sweeper.check_domain({"id": "u", "name": "s"}, "live", "a.umich.edu", set())
    assert "expected one of: none listed" in capsys.readouterr().err


def test_counters_summary_format(fpd):
    # Fix round 1, M3 (SPEC section 8's `sites=N envs=N custom_domains=N rows=N
    # indeterminate=N` summary line).  Nothing referenced `Counters.summary()` before this.
    counters = fpd.Counters(sites=3, envs=5, custom_domains=7, rows=2, indeterminate=1)
    assert counters.summary() == "sites=3 envs=5 custom_domains=7 rows=2 indeterminate=1"


# ---------------------------------------------------------------------------------------------
# Task 5: CLI, main(), exit codes
# ---------------------------------------------------------------------------------------------


class _StubSession:
    """Stands in for ApiSession: an organization of one site with one environment.

    Takes the loaded module so it can raise the module's OWN PantheonApiError -- the sweep
    catches that class by identity, so a stand-in raising anything else would not exercise the
    G6 path at all.  `indeterminate=True` makes the domains call fail, which is the shortest
    path to a counted indeterminate without touching DNS.
    """

    def __init__(self, fpd, *, indeterminate):
        self._fpd = fpd
        self._indeterminate = indeterminate

    def get(self, path):
        if "/memberships/sites" in path:
            return [{"id": "mem-1", "site": {"id": "u1", "name": "s1"}}]
        if path.endswith("/environments"):
            return {"live": {}}
        if self._indeterminate:
            raise self._fpd.PantheonApiError("HTTP 500")
        return [{"id": "live-s1.pantheonsite.io", "type": "platform"}]


def test_org_id_is_read_from_the_config(fpd, tmp_path):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\nplan_info = {}\n')
    assert fpd.org_id_from_config(config) == "org-uuid"


def test_missing_org_id_raises_out_of_the_low_level_helper(fpd, tmp_path):
    # org_id_from_config is deliberately thin; prepare_sweep is what converts this into a
    # StartupError.  The exit-code contract is pinned by the main() tests below, which is where
    # it matters -- a bare KeyError reaching an operator would be the defect (PD#2).
    config = tmp_path / "c.toml"
    config.write_text("[Database]\ntype = \"sqlite\"\n")
    with pytest.raises(KeyError):
        fpd.org_id_from_config(config)


def test_parser_rejects_abbreviations(fpd):
    parser = fpd.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--verb"])          # allow_abbrev=False


def test_parser_accepts_site_arguments(fpd):
    options = fpd.build_arg_parser().parse_args(["-v", "alpha", "beta"])
    assert (options.verbose, options.site) == (True, ["alpha", "beta"])


def test_main_returns_2_when_the_config_has_no_org_id(fpd, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text("[Database]\n")
    assert fpd.main(["-c", str(config)]) == 2
    assert "org_id" in capsys.readouterr().err


def test_main_returns_2_when_the_config_is_missing(fpd, tmp_path, capsys):
    assert fpd.main(["-c", str(tmp_path / "nope.toml")]) == 2
    assert "nope.toml" in capsys.readouterr().err


def test_main_returns_2_for_a_config_whose_pantheon_is_not_a_table(fpd, tmp_path, capsys):
    # SPEC section 10 item 15.  ["Pantheon"]["org_id"] subscripts a str -> TypeError, which was
    # uncaught and therefore exit 1 -- the code reserved for a COMPLETED sweep.
    config = tmp_path / "c.toml"
    config.write_text('Pantheon = "not-a-table"\n')
    assert fpd.main(["-c", str(config)]) == 2
    assert "no usable [Pantheon].org_id" in capsys.readouterr().err


def test_main_returns_2_for_a_config_that_is_not_utf8(fpd, tmp_path, capsys):
    # UnicodeDecodeError is not an OSError, so it escaped the original handler.
    config = tmp_path / "c.toml"
    config.write_bytes(b'[Pantheon]\norg_id = "x"\n\xff\xfe garbage\n')
    assert fpd.main(["-c", str(config)]) == 2
    assert "could not read" in capsys.readouterr().err


def test_verbose_prints_the_reauthentication_note_and_quiet_does_not(fpd, monkeypatch, tmp_path,
                                                                     capsys):
    """SPEC section 10 item 11 -- driven through main(), where the verbosity gate lives."""
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": "sess"})
        if calls.count(request.url.path) == 1 and request.url.path.endswith("/environments"):
            return httpx.Response(401, json={"error": "expired"})
        if request.url.path.endswith("/environments"):
            return httpx.Response(200, json={"live": {}})
        if "/memberships/sites" in request.url.path:
            return httpx.Response(200, json=[{"id": "m1", "site": {"id": "u1", "name": "s1"}}])
        return httpx.Response(200, json=[{"id": "live-s1.pantheonsite.io", "type": "platform"}])

    def build(**kwargs):
        return fpd.ApiSession(httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0),
                              "mt", **kwargs)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", build)
    fpd.main(["-c", str(config), "-v"])
    assert "session expired; re-authenticated" in capsys.readouterr().err
    calls.clear()
    fpd.main(["-c", str(config)])
    assert "session expired; re-authenticated" not in capsys.readouterr().err


def test_main_returns_1_when_the_sweep_had_an_indeterminate(fpd, monkeypatch, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session",
                        lambda **_kwargs: _StubSession(fpd, indeterminate=True))
    assert fpd.main(["-c", str(config)]) == 1
    assert "indeterminate=1" in capsys.readouterr().err


def test_main_returns_0_on_a_clean_sweep(fpd, monkeypatch, tmp_path, capsys):
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session",
                        lambda **_kwargs: _StubSession(fpd, indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 0
    assert "indeterminate=0" in capsys.readouterr().err


def _main_with_sweep_raising(fpd, monkeypatch, tmp_path, error):
    """Run main() against a stub whose sweep raises `error` on the first domains call."""
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    class Boom(_StubSession):
        def get(self, path):
            if path.endswith("/domains"):
                raise error
            return super().get(path)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda **_kwargs: Boom(fpd, indeterminate=False))
    return fpd.main(["-c", str(config)])


def test_an_abort_names_the_completed_site_and_the_unreached_ones(fpd, monkeypatch, tmp_path,
                                                                  capsys):
    """SPEC section 7.3: the names, not just a count -- they are the resume instruction."""
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    class TwoSites(_StubSession):
        def get(self, path):
            if "/memberships/sites" in path:
                return [{"id": "m1", "site": {"id": "u1", "name": "s1"}},
                        {"id": "m2", "site": {"id": "u2", "name": "s2"}}]
            if path.endswith("/environments"):
                if "/u2/" in path:
                    raise KeyboardInterrupt
                return {"live": {}}
            return [{"id": "live-s1.pantheonsite.io", "type": "platform"}]

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda **_k: TwoSites(fpd, indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 130
    err = capsys.readouterr().err
    assert "Stopped after s1." in err
    assert "find-platform-domains-dns s2" in err      # paste-able resume command


def test_ctrl_c_returns_130_and_says_where_it_stopped(fpd, monkeypatch, tmp_path, capsys):
    # SPEC G15 + section 7.3.  130 matches the main program's abort_reason convention; the
    # default (an uncaught KeyboardInterrupt) would exit 1, which section 7 reserves for a
    # COMPLETED sweep.
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, KeyboardInterrupt()) == 130
    err = capsys.readouterr().err
    assert "did not complete (interrupted)" in err
    assert "sites=" in err                       # the summary is printed on an abort too


def test_broken_pipe_returns_2_and_reports_like_every_other_abort(fpd, monkeypatch, tmp_path,
                                                                  capsys):
    # SPEC G16 + section 8: `| head` must not produce a traceback at exit 1, AND stderr is
    # unaffected by a closed stdout, so the summary and position line are printed here too.
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, BrokenPipeError()) == 2
    err = capsys.readouterr().err
    assert "broken pipe" in err
    assert "sites=" in err          # the summary, which this path used to omit
    assert "Stopped" in err


def test_broken_pipe_dup2_recipe_actually_runs(fpd, monkeypatch, tmp_path):
    """Fix round 1, I1.  test_broken_pipe_returns_2_and_reports_like_every_other_abort (above)
    runs under capsys, whose captured sys.stdout has no real file descriptor --
    sys.stdout.fileno() raises io.UnsupportedOperation there, which the BrokenPipeError handler's
    contextlib.suppress(...) swallows, so the ENTIRE dup2 recipe silently never executes under
    that test.  Reviewer's mutation (replace the `with contextlib.suppress(...)` body with `pass`)
    left all 96 tests green while a real `find-platform-domains-dns bus-occb | head -0` exits
    120, not 2 -- the exact defect class this repo keeps getting burned by (an instrument that
    cannot go red, PD#14).  This test gives sys.stdout a REAL file descriptor (a plain opened
    file, not capsys's pseudo-stream) so the recipe actually runs, and records the os.dup2 call
    rather than relying on process exit code alone (which pytest cannot observe in-process).
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    class Boom(_StubSession):
        def get(self, path):
            if path.endswith("/domains"):
                raise BrokenPipeError
            return super().get(path)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda **_kwargs: Boom(fpd, indeterminate=False))

    real_stdout = (tmp_path / "stdout").open("w")
    expected_fd = real_stdout.fileno()          # captured before dup2 repoints this fd number
    calls = []
    real_dup2 = fpd.os.dup2

    def recording_dup2(fd, target_fd):
        calls.append((fd, target_fd))
        return real_dup2(fd, target_fd)

    monkeypatch.setattr(fpd.sys, "stdout", real_stdout)
    monkeypatch.setattr(fpd.os, "dup2", recording_dup2)
    try:
        assert fpd.main(["-c", str(config)]) == 2
    finally:
        real_stdout.close()
    assert len(calls) == 1
    assert calls[0][1] == expected_fd            # dup2's target was the real stdout's own fd


def test_session_expiry_returns_2_not_1(fpd, monkeypatch, tmp_path, capsys):
    # SPEC G7a: the whole point is that this is distinguishable from a completed sweep.
    error = fpd.SessionExpiredError("token revoked")
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, error) == 2
    assert "session expired" in capsys.readouterr().err


def test_an_unexpected_error_returns_2_never_1(fpd, monkeypatch, tmp_path, capsys):
    # SPEC G18.  Exit 1 must mean ONLY "completed with indeterminates".
    assert _main_with_sweep_raising(fpd, monkeypatch, tmp_path, ValueError("surprise")) == 2
    assert "unexpected ValueError" in capsys.readouterr().err


def test_system_exit_mid_sweep_propagates_unconverted(fpd, monkeypatch, tmp_path):
    """Fix round 1, m1.  `except SystemExit: raise` sits between the named handlers and the
    final `except BaseException as e:` catch-all.  Deleting it leaves all existing tests green
    (nothing else in the suite raises SystemExit mid-sweep) and lets the catch-all convert a
    SystemExit into `unexpected SystemExit: ...` / return 2 -- discarding whatever exit code the
    SystemExit itself carried.  CLAUDE.md's abort_reason describes the same rule for the main
    program: "There is no except SystemExit: clause and nothing is swallowed."
    """
    with pytest.raises(SystemExit) as excinfo:
        _main_with_sweep_raising(fpd, monkeypatch, tmp_path, SystemExit(7))
    assert excinfo.value.code == 7


def test_no_token_ever_reaches_stdout_or_stderr(fpd, monkeypatch, tmp_path, capsys):
    """SPEC section 3, threat-model property (a) -- instrumented rather than asserted.

    An unmeasured security claim is PD#14 in its design-time form: "Applies at design time too
    -- to a new counter, artifact, or notice -- not only in tests."
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    secrets = ("MACHINE-TOKEN-e7f2a1", "SESSION-TOKEN-9b4c3d")

    def handler(request):
        # The two paths SPEC section 3 names: a per-site G5 (environments 500) and, after it,
        # an authentication failure that survives re-authentication (G7a).  A test that only
        # failed the site listing would traverse neither.
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": secrets[1]})
        if "/memberships/sites" in request.url.path:
            return httpx.Response(200, json=[{"id": "m1", "site": {"id": "u1", "name": "s1"}},
                                             {"id": "m2", "site": {"id": "u2", "name": "s2"}}])
        if "/u1/" in request.url.path:
            return httpx.Response(500, text="boom")            # G5
        return httpx.Response(401, json={"error": "expired"})  # -> G7a on retry

    monkeypatch.setattr(fpd, "machine_token", lambda: secrets[0])
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    monkeypatch.setattr(fpd, "build_session", lambda **kwargs: fpd.ApiSession(
        httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0), secrets[0], **kwargs))
    assert fpd.main(["-c", str(config), "-v"]) == 2     # G7a aborts; -v is the noisiest mode
    captured = capsys.readouterr()
    for secret in secrets:
        assert secret not in captured.out
        assert secret not in captured.err


def test_no_token_ever_reaches_stdout_or_stderr_at_default_verbosity(fpd, monkeypatch, tmp_path,
                                                                     capsys):
    """Carry-forward 1 (task 5 dispatch): the test above only drove -v.  SPEC section 3's threat
    model makes no verbosity exception, so the default (quiet) path needs its own instrumented
    proof -- an untested half of a security property is PD#14 in its design-time form.
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    secrets = ("MACHINE-TOKEN-1a2b3c", "SESSION-TOKEN-4d5e6f")

    def handler(request):
        if request.url.path.endswith("/authorize/machine-token"):
            return httpx.Response(200, json={"session": secrets[1]})
        if "/memberships/sites" in request.url.path:
            return httpx.Response(200, json=[{"id": "m1", "site": {"id": "u1", "name": "s1"}},
                                             {"id": "m2", "site": {"id": "u2", "name": "s2"}}])
        if "/u1/" in request.url.path:
            return httpx.Response(500, text="boom")            # G5
        return httpx.Response(401, json={"error": "expired"})  # -> G7a on retry

    monkeypatch.setattr(fpd, "machine_token", lambda: secrets[0])
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    monkeypatch.setattr(fpd, "build_session", lambda **kwargs: fpd.ApiSession(
        httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0), secrets[0], **kwargs))
    assert fpd.main(["-c", str(config)]) == 2           # no -v this time
    captured = capsys.readouterr()
    for secret in secrets:
        assert secret not in captured.out
        assert secret not in captured.err


def test_build_session_pins_no_redirects_and_the_http_timeout(fpd, monkeypatch):
    """Carry-forwards 2 and 3 (task 5 dispatch).

    ApiSession receives an already-built client and never inspects it, so build_session is the
    ONLY place either property can be pinned.  follow_redirects=False is httpx's own default, and
    SPEC section 3 property (c) says it MUST NOT be changed to True (an Authorization header must
    never be replayed to a redirect target); HTTP_TIMEOUT was defined in task 2 and referenced
    nowhere until build_session applies it here -- dead code until this test and this call site.
    """
    monkeypatch.setattr(fpd.ApiSession, "_authenticate", lambda self: "sess")
    session = fpd.build_session()
    assert session._client.follow_redirects is False
    assert session._client.timeout == fpd.httpx.Timeout(fpd.HTTP_TIMEOUT)


def test_build_session_never_constructs_a_client_when_the_token_cannot_be_resolved(fpd, monkeypatch):
    """Fix round 2, N10.  build_session() used to construct its httpx.Client BEFORE calling
    machine_token() -- harmless while an unresolvable token used to crash the whole interpreter,
    but this round's C1 fix made "the token cannot be resolved" a reachable, non-fatal
    MachineTokenError, so the client built first would leak (never closed -- nothing holds a
    reference to it once the exception unwinds).  Spies on httpx.Client's constructor rather than
    asserting on a leaked object (there is nothing left to assert ON once it's unreferenced):
    the right assertion is that construction never happened at all.
    """
    calls = []
    real_client = fpd.httpx.Client

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real_client(*args, **kwargs)

    monkeypatch.setattr(fpd.httpx, "Client", spy)

    def boom():
        raise fpd.MachineTokenError("no token")

    monkeypatch.setattr(fpd, "machine_token", boom)
    with pytest.raises(fpd.MachineTokenError):
        fpd.build_session()
    assert calls == []


def test_main_writes_csv_with_unix_line_endings_only(fpd, monkeypatch, tmp_path, capsys):
    """Carry-forward 4 (task 5 dispatch).

    test_csv_uses_unix_line_endings (above) pins only the writer THAT TEST's own make_sweeper
    helper builds -- it cannot go red against a production main() that forgets
    lineterminator="\\n", because it never constructs main()'s writer at all.  This drives a real
    hit through the real main(), over the real sys.stdout capsys captures, and checks the actual
    bytes.
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')
    patch_dns(monkeypatch, fpd,
              {("occb.bus.umich.edu", "CNAME"): ["live-s1.pantheonsite.io."]})

    class Hit(_StubSession):
        def get(self, path):
            if "/memberships/sites" in path:
                return [{"id": "m1", "site": {"id": "u1", "name": "s1"}}]
            if path.endswith("/environments"):
                return {"live": {}}
            return [{"id": "live-s1.pantheonsite.io", "type": "platform"},
                    {"id": "occb.bus.umich.edu", "type": "custom"}]

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", lambda **_kwargs: Hit(fpd, indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 0
    out = capsys.readouterr().out
    assert out == "s1,live,occb.bus.umich.edu,occb.bus.umich.edu,live-s1.pantheonsite.io\n"
    assert "\r" not in out


def test_shape_error_during_listing_returns_2_not_1(fpd, monkeypatch, tmp_path, capsys):
    """Carry-forward 5 (task 5 dispatch): G17 at LISTING time (as opposed to per-site/per-env,
    which SPEC G17 says is counted like G4/G5/G6) must still exit 2, not fall through to the
    indeterminate-driven return.  PantheonApiShapeError is a PantheonApiError subclass, so
    prepare_sweep's existing except tuple already catches it -- this proves that, rather than
    assuming it from reading the class hierarchy.
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    class Malformed(_StubSession):
        def get(self, path):
            if "/memberships/sites" in path:
                return [{"id": "m1", "site": {"id": "u1"}}]     # no "name" -> shape error
            return super().get(path)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session",
                        lambda **_kwargs: Malformed(fpd, indeterminate=False))
    assert fpd.main(["-c", str(config)]) == 2
    assert "could not list sites" in capsys.readouterr().err


def test_report_stop_says_during_when_no_site_completed_yet(fpd, capsys):
    """Carry-forward 6 (task 5 dispatch): SPEC section 7.3's position line is UNCONDITIONAL.  An
    earlier draft printed it only `if sweeper.last_site` -- i.e. never, when the very first site
    is the one interrupted, which is exactly when the operator most needs it.  Exercises
    report_stop() directly rather than through main(), so the "no site has completed yet" state
    doesn't depend on how a particular stub happens to fail.
    """
    sweeper, _out = make_sweeper(fpd)
    sweeper.current_site = "s1"
    sweeper.remaining = [{"name": "s1"}]
    fpd.report_stop(sweeper, "interrupted")
    err = capsys.readouterr().err
    assert "Stopped during s1." in err
    assert "1 site not reached" in err
    assert "find-platform-domains-dns s1" in err


def test_report_stop_lists_multiple_remaining_site_names_space_separated(fpd, capsys):
    """Carry-forward 6 (task 5 dispatch): the names are the recovery instruction, not a count
    (SPEC section 7.3) -- pin the plural grammar and the space-separated join together, since a
    single-remaining-site test can't tell a join from a single f-string interpolation apart.
    """
    sweeper, _out = make_sweeper(fpd)
    sweeper.last_site = "s1"
    sweeper.remaining = [{"name": "s2"}, {"name": "s3"}]
    fpd.report_stop(sweeper, "interrupted")
    err = capsys.readouterr().err
    assert "Stopped after s1." in err
    assert "2 sites not reached" in err
    assert "find-platform-domains-dns s2 s3" in err


def test_report_stop_says_something_sane_when_ctrl_c_lands_before_the_first_site_starts(
        fpd, monkeypatch, capsys):
    """Fix round 2, N3.  KeyboardInterrupt is asynchronous and can land ANYWHERE -- including
    inside sweep()'s own `self.remaining = list(sites)` or `self._progress(...)` call, both of
    which run BEFORE `self.current_site = site["name"]`.  Fix round 1's m7 comment claimed
    current_site "cannot be falsy" by the time report_stop() runs -- true only for SYNCHRONOUS
    failures (inside sweep_site()), false here.  Reproduced by raising KeyboardInterrupt from
    _progress itself, the exact call the finding names, rather than from anywhere inside
    sweep_site() (which every other abort test in this file already uses, and which cannot
    reproduce this specific gap).
    """
    sweeper, _out = make_sweeper(fpd)

    def boom(_message):
        raise KeyboardInterrupt

    monkeypatch.setattr(sweeper, "_progress", boom)
    with pytest.raises(KeyboardInterrupt):
        sweeper.sweep([{"id": "u1", "name": "s1"}])
    assert sweeper.last_site == ""
    fpd.report_stop(sweeper, "interrupted")
    err = capsys.readouterr().err
    assert "Stopped during ." not in err
    assert "Stopped during startup." in err


def test_get_converts_invalid_url_into_a_named_error(fpd, monkeypatch):
    """Carry-forward 7 (task 5 dispatch).

    org_id (read straight from TOML) and the API's own site/env ids are unquoted path segments --
    SPEC section 3's quote(name, safe="") mandate covers only the SITE argv, not these.
    httpx.InvalidURL is NOT an httpx.HTTPError subclass (verified, httpx 0.28.1), so it bypassed
    BOTH of get()'s handlers before this fix -- an exit-1 traceback for something as ordinary as a
    literal newline in the config file.  No MockTransport needed: URL validation raises before
    any transport is reached.
    """
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    session = fpd.ApiSession.__new__(fpd.ApiSession)
    session._client = httpx.Client()
    session._machine_token = "mt"          # constructing the seam directly, bypassing
    session.token = "sess"                 # __init__'s real _authenticate() POST
    session._notify = lambda _message: None
    with pytest.raises(fpd.PantheonApiError):
        session.get("/organizations/org\nid/memberships/sites")


def test_hostile_org_id_does_not_produce_an_unnamed_traceback(fpd, monkeypatch, tmp_path, capsys):
    """Carry-forward 7 (task 5 dispatch), driven through the real main()/prepare_sweep/org_sites
    path rather than ApiSession.get() directly: a config file's [Pantheon].org_id is attacker- or
    operator-typo-controlled and reaches org_sites()'s URL completely unquoted.  Uses a REAL
    ApiSession over an httpx.MockTransport (not the _StubSession fake), because the fake's get()
    never builds an httpx.URL at all and so cannot exercise the bug this test guards.
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org\\nid"\n')     # TOML \n escape -> a literal newline

    def handler(_request):
        return httpx.Response(200, json={"session": "sess"})

    def build(**kwargs):
        return fpd.ApiSession(httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0),
                              "mt", **kwargs)

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "RETRY_SLEEP", 0)
    monkeypatch.setattr(fpd, "build_session", build)
    assert fpd.main(["-c", str(config)]) == 2
    assert "could not list sites" in capsys.readouterr().err


def test_ctrl_c_during_prepare_sweep_returns_130_cleanly(fpd, monkeypatch, tmp_path, capsys):
    """Fix round 1, m6.  Site listing (org_sites(): up to 5 pages plus two 2-second cursor
    retries, SPEC section 4.1) is a real Ctrl-C window during prepare_sweep(), which previously
    had no KeyboardInterrupt handler of its own -- CPython does exit 130 on an uncaught
    KeyboardInterrupt at the top level (the exit-code contract already held), but the operator
    got a raw Python traceback instead of the program's own message shape, and there was no
    handler AT ALL to route through, unlike every other abort path in main().

    Fix round 2, N2: a bare `assert fpd.main(...) == 130` cannot fail cleanly against a
    regression -- if the KeyboardInterrupt escapes main() uncaught, it also escapes THIS test
    function uncaught, and pytest treats an escaping KeyboardInterrupt as a session abort, not a
    normal failure: the run prints a "!!! KeyboardInterrupt !!!" banner, a "N passed" summary
    with NO "FAILED" line, and silently drops every test collected after this one. Catching it
    explicitly and calling pytest.fail() converts that into an ordinary, reported failure.
    """
    config = tmp_path / "c.toml"
    config.write_text('[Pantheon]\norg_id = "org-uuid"\n')

    def boom(**_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(fpd, "machine_token", lambda: "mt")
    monkeypatch.setattr(fpd, "build_session", boom)
    try:
        rc = fpd.main(["-c", str(config)])
    except KeyboardInterrupt:
        pytest.fail("KeyboardInterrupt escaped main() instead of being handled and returning 130")
    assert rc == 130
    assert "interrupted" in capsys.readouterr().err.lower()


def test_report_stop_ignores_a_second_sigint_while_printing(fpd, monkeypatch):
    """Fix round 1, m5.  A second Ctrl-C landing while report_stop() is still printing could
    truncate the resume line -- SPEC section 7.3 calls that line the whole recovery story.
    CLAUDE.md's abort_run() (the main program's own equivalent) sets SIGINT to SIG_IGN for
    exactly this reason: "so a second Ctrl-C cannot truncate the flush."

    MUST monkeypatch signal.signal here rather than let the real one run: the real one would
    leave SIG_IGN in effect for the REST of this pytest session, since signal handlers are
    process-global and are not restored automatically -- the identical trap CLAUDE.md's Testing
    section documents for abort_run() ("an in-process test that calls it MUST
    monkeypatch.setattr(psh.signal, 'signal', ...), or the rest of the pytest session silently
    ignores Ctrl-C").
    """
    calls = []
    monkeypatch.setattr(fpd.signal, "signal", lambda sig, handler: calls.append((sig, handler)))
    sweeper, _out = make_sweeper(fpd)
    sweeper.last_site = "s1"
    fpd.report_stop(sweeper, "interrupted")
    assert calls == [(fpd.signal.SIGINT, fpd.signal.SIG_IGN)]
