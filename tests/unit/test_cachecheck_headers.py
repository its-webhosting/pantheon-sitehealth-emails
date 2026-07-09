"""Unit tests for check/cloudflare/headers.py (the pure per-URL header battery).

Table-driven over the battery rules plus Hypothesis properties (the parser never raises;
cache_seconds is the max of the parseable directives; the battery is deterministic).
"""
import datetime
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

pytestmark = pytest.mark.unit

NOW = datetime.datetime(2026, 3, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)
YEAR = "max-age=31536000"


@pytest.fixture(scope="module")
def hdrs(psh):
    path = Path(psh.__file__).parent / "check" / "cloudflare" / "headers.py"
    loader = SourceFileLoader("cachecheck_headers_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(hdrs, headers, *, main=False, kind="page", status=200):
    return hdrs.evaluate_headers(headers, is_main_page=main, kind=kind, now=NOW,
                                 status_code=status)


def ids(items):
    return sorted(i["id"] for i in items)


# ── battery table ────────────────────────────────────────────────────────────────────
def test_perfect_response_yields_no_items(hdrs):
    assert run(hdrs, {"cf-cache-status": "HIT", "cache-control": f"public, {YEAR}"}) == []


def test_non_2xx_short_circuits_to_http_error_only(hdrs):
    items = run(hdrs, {"cf-cache-status": "MISS"}, status=404)
    assert ids(items) == ["http-error"]
    assert items[0]["params"]["status"] == 404


def test_empty_headers(hdrs):
    assert ids(run(hdrs, {})) == ["cf-status-missing", "no-cache-control"]


@pytest.mark.parametrize("status", ["DYNAMIC", "BYPASS", "NONE", "UNKNOWN", "dynamic"])
def test_unacceptable_cache_status_flagged(hdrs, status):
    items = run(hdrs, {"cf-cache-status": status, "cache-control": YEAR})
    assert ids(items) == ["cf-status-uncacheable"]
    assert items[0]["params"]["status"] == status.upper()


@pytest.mark.parametrize("status", ["HIT", "MISS", "EXPIRED", "STALE", "REVALIDATED",
                                    "UPDATING", "hit"])
def test_acceptable_cache_statuses_pass(hdrs, status):
    assert run(hdrs, {"cf-cache-status": status, "cache-control": YEAR}) == []


def test_no_cache_control_skips_remaining_cc_rules(hdrs):
    # No CC header at all: even though there is no max-age either, only no-cache-control.
    items = run(hdrs, {"cf-cache-status": "HIT"})
    assert ids(items) == ["no-cache-control"]


@pytest.mark.parametrize("cc", ["public", "max-age=garbage", "private"])
def test_no_parseable_max_age(hdrs, cc):
    # no-max-age fires and the remaining CC rules are skipped (note: 'private' present
    # but not flagged -- the directive rules only run once a cache time parses).
    items = run(hdrs, {"cf-cache-status": "HIT", "cache-control": cc})
    assert ids(items) == ["no-max-age"]


def test_short_cache_time(hdrs):
    items = run(hdrs, {"cf-cache-status": "HIT", "cache-control": "max-age=3600"})
    assert ids(items) == ["short-cache-time"]
    assert items[0]["params"]["seconds"] == 3600


def test_cache_time_is_max_of_max_age_and_s_maxage(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": "max-age=60, s-maxage=31536000"}
    assert run(hdrs, headers) == []


def test_bad_directives_each_flagged(hdrs):
    headers = {"cf-cache-status": "HIT",
               "cache-control": f"private, no-cache, no-store, proxy-revalidate, {YEAR}"}
    assert ids(run(hdrs, headers)) == ["cc-no-cache", "cc-no-store", "cc-private",
                                       "cc-proxy-revalidate"]


def test_must_revalidate_ok_on_main_page_flagged_elsewhere(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": f"must-revalidate, {YEAR}"}
    assert run(hdrs, headers, main=True) == []
    assert ids(run(hdrs, headers, main=False)) == ["cc-must-revalidate"]
    assert ids(run(hdrs, headers, kind="asset")) == ["cc-must-revalidate"]


# ── Expires ─────────────────────────────────────────────────────────────────────────
SHORT_EXPIRES = "Wed, 01 Apr 2026 12:00:00 GMT"   # NOW + 1 day
LONG_EXPIRES = "Thu, 01 Apr 2027 12:00:00 GMT"


def test_expires_short_without_cache_control(hdrs):
    items = run(hdrs, {"cf-cache-status": "HIT", "expires": SHORT_EXPIRES})
    assert ids(items) == ["expires-short", "no-cache-control"]


def test_expires_far_future_ok(hdrs):
    items = run(hdrs, {"cf-cache-status": "HIT", "expires": LONG_EXPIRES})
    assert ids(items) == ["no-cache-control"]


def test_expires_ignored_when_max_age_present(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": YEAR, "expires": SHORT_EXPIRES}
    assert run(hdrs, headers) == []


def test_garbage_max_age_plus_short_expires_fires_both(hdrs):
    # The shared "parseable" predicate: max-age=garbage counts as absent for BOTH rules.
    headers = {"cf-cache-status": "HIT", "cache-control": "max-age=garbage",
               "expires": SHORT_EXPIRES}
    assert ids(run(hdrs, headers)) == ["expires-short", "no-max-age"]


def test_unparseable_expires_is_ignored(hdrs):
    items = run(hdrs, {"cf-cache-status": "HIT", "expires": "not a date"})
    assert ids(items) == ["no-cache-control"]


# ── Set-Cookie ──────────────────────────────────────────────────────────────────────
def test_set_cookie_on_public_content(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": YEAR, "set-cookie": ["a=1"]}
    assert ids(run(hdrs, headers)) == ["set-cookie"]


def test_bypass_with_cookie_replaces_status_item(hdrs):
    headers = {"cf-cache-status": "BYPASS", "cache-control": YEAR, "set-cookie": ["a=1"]}
    assert ids(run(hdrs, headers)) == ["set-cookie-bypass"]


def test_bypass_without_cookie_keeps_status_item(hdrs):
    headers = {"cf-cache-status": "BYPASS", "cache-control": YEAR}
    assert ids(run(hdrs, headers)) == ["cf-status-uncacheable"]


def _item(items, item_id):
    return next(i for i in items if i["id"] == item_id)


def test_set_cookie_records_names_not_values(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": YEAR,
               "set-cookie": ["sessionid=SECRETVALUE; Path=/; HttpOnly",
                              "csrftoken=deadbeef"]}
    item = _item(run(hdrs, headers), "set-cookie")
    # Names only, no values, sorted (order-independent for consolidation):
    assert item["params"]["cookies"] == "csrftoken, sessionid"
    assert "SECRETVALUE" not in item["params"]["cookies"]


def test_set_cookie_names_are_order_independent(hdrs):
    # Same cookies in different header order must produce the same item so the two FQDNs
    # consolidate into one notice rather than fragmenting.
    a = _item(run(hdrs, {"cf-cache-status": "HIT", "cache-control": YEAR,
                         "set-cookie": ["sessionid=1", "csrftoken=2"]}), "set-cookie")
    b = _item(run(hdrs, {"cf-cache-status": "HIT", "cache-control": YEAR,
                         "set-cookie": ["csrftoken=2", "sessionid=1"]}), "set-cookie")
    assert a["params"]["cookies"] == b["params"]["cookies"] == "csrftoken, sessionid"


def test_only_cloudflare_cookies_yields_no_finding(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": YEAR,
               "set-cookie": ["__cf_bm=abc; Path=/", "_cfuvid=xyz"]}
    assert ids(run(hdrs, headers)) == []


def test_cloudflare_cookie_filter_is_case_insensitive(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": YEAR,
               "set-cookie": ["__CF_BM=abc", "CF_Clearance=xyz"]}
    assert ids(run(hdrs, headers)) == []


def test_mixed_cookies_keep_only_website_names(hdrs):
    headers = {"cf-cache-status": "HIT", "cache-control": YEAR,
               "set-cookie": ["__cf_bm=abc", "sessionid=1", "cf_clearance=z"]}
    item = _item(run(hdrs, headers), "set-cookie")
    assert item["params"]["cookies"] == "sessionid"


def test_bypass_caused_by_website_cookie_names_the_cookie(hdrs):
    headers = {"cf-cache-status": "BYPASS", "cache-control": YEAR,
               "set-cookie": ["__cf_bm=abc", "sessionid=1"]}
    items = run(hdrs, headers)
    assert ids(items) == ["set-cookie-bypass"]
    assert _item(items, "set-cookie-bypass")["params"]["cookies"] == "sessionid"


def test_bypass_with_only_cloudflare_cookies_keeps_status_item(hdrs):
    headers = {"cf-cache-status": "BYPASS", "cache-control": YEAR,
               "set-cookie": ["__cf_bm=abc"]}
    assert ids(run(hdrs, headers)) == ["cf-status-uncacheable"]


def test_cookie_names_helper(hdrs):
    assert hdrs.cookie_names("sessionid=1; Path=/") == ["sessionid"]
    assert hdrs.cookie_names(["a=1", "a=2", "b=3"]) == ["a", "b"]
    assert hdrs.cookie_names(["__cf_bm=x", "__cflb=y"]) == []
    assert hdrs.cookie_names(None) == []
    assert hdrs.cookie_names("") == []


# ── should_retry_miss ───────────────────────────────────────────────────────────────
def test_retry_miss_matrix(hdrs):
    def check(headers, *, status=200, main=False):
        items = run(hdrs, headers, main=main, status=status)
        return hdrs.should_retry_miss(headers, items)

    cacheable_miss = {"cf-cache-status": "MISS", "cache-control": YEAR}
    assert check(cacheable_miss) is True
    # must-revalidate alone does not block the retry (object still cacheable):
    assert check({"cf-cache-status": "MISS",
                  "cache-control": f"must-revalidate, {YEAR}"}) is True
    # short/missing cache time blocks:
    assert check({"cf-cache-status": "MISS", "cache-control": "max-age=3600"}) is False
    assert check({"cf-cache-status": "MISS"}) is False
    # disqualifying directives/cookies block:
    assert check({"cf-cache-status": "MISS",
                  "cache-control": f"no-store, {YEAR}"}) is False
    assert check({"cf-cache-status": "MISS", "cache-control": YEAR,
                  "set-cookie": ["a=1"]}) is False
    # http-error blocks (a cacheable 404 must not burn retries):
    assert check(cacheable_miss, status=404) is False
    # non-MISS statuses never retry:
    for status in ("HIT", "EXPIRED", "STALE", "REVALIDATED", "UPDATING", "DYNAMIC"):
        assert check({"cf-cache-status": status, "cache-control": YEAR}) is False


# ── Hypothesis properties ───────────────────────────────────────────────────────────
@given(st.text(max_size=200))
def test_parse_cache_control_never_raises(psh, value):
    hdrs = _load(psh)
    result = hdrs.parse_cache_control(value)
    assert isinstance(result, dict)


@given(st.integers(min_value=0, max_value=10**9), st.integers(min_value=0, max_value=10**9))
def test_cache_seconds_is_max(psh, a, b):
    hdrs = _load(psh)
    assert hdrs.cache_seconds({"max-age": a, "s-maxage": b}) == max(a, b)


@given(st.dictionaries(
    st.sampled_from(["cf-cache-status", "cache-control", "expires", "set-cookie"]),
    st.text(max_size=60), max_size=4))
def test_evaluate_headers_deterministic_and_total(psh, headers):
    hdrs = _load(psh)
    if "set-cookie" in headers:
        headers["set-cookie"] = [headers["set-cookie"]]
    once = hdrs.evaluate_headers(headers, is_main_page=False, kind="page", now=NOW,
                                 status_code=200)
    twice = hdrs.evaluate_headers(headers, is_main_page=False, kind="page", now=NOW,
                                  status_code=200)
    assert once == twice


_CACHED = {}


def _load(psh):
    # Hypothesis @given can't take function-scoped fixtures; cache the module manually.
    if "m" not in _CACHED:
        path = Path(psh.__file__).parent / "check" / "cloudflare" / "headers.py"
        loader = SourceFileLoader("cachecheck_headers_probe2", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHED["m"] = module
    return _CACHED["m"]
