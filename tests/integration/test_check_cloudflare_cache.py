"""Integration tests for check/cloudflare/cache.py (per-site orchestration).

Offline by construction: `httpseam.fetch` and `httpseam.sleep` (the seams) are replaced
with canned FetchResults built from real HTML strings (parsed by real bs4).  Covers the
transport policy (cert-insecure-continue, challenge short-circuit, cross-FQDN drop,
non-2xx stop), the D9 MISS-retry protocol, consolidation, RNG determinism (D6), and the
csv contract.
"""
import importlib.util
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"
FQDN = "www.example.edu"
MAIN = f"https://{FQDN}/"
YEAR = "max-age=31536000"
CONFIG = {"Cloudflare": {"enabled": True,
                         "cachecheck": {"enabled": True, "account_id": "a",
                                        "list_name": "l"}}}


@pytest.fixture
def cache(psh, monkeypatch):
    """Load cache.py under a probe package so its relative imports resolve."""
    pkg_dir = Path(psh.__file__).parent / "check" / "cloudflare"
    package = types.ModuleType("cf_cache_pkg")
    package.__path__ = [str(pkg_dir)]
    monkeypatch.setitem(sys.modules, "cf_cache_pkg", package)
    for sub in ("cfg", "headers", "notices", "pages", "httpseam", "cache"):
        monkeypatch.delitem(sys.modules, f"cf_cache_pkg.{sub}", raising=False)
    loader = SourceFileLoader("cf_cache_pkg.cache", str(pkg_dir / "cache.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "cf_cache_pkg.cache", module)
    loader.exec_module(module)
    return module


class FakeFetch:
    """Canned responses keyed by (url, verify); successive calls consume a queue whose
    last entry repeats.  Unexpected URLs fail the test loudly."""

    def __init__(self, httpseam):
        self.httpseam = httpseam
        self.responses = {}
        self.calls = []

    def add(self, url, *results, verify=True):
        self.responses.setdefault((url, verify), []).extend(results)

    def __call__(self, url, *, fqdn, timeout, user_agent, verify=True, pool=None):
        self.calls.append((url, verify))
        queue = self.responses.get((url, verify))
        assert queue, f"unexpected fetch: {url} (verify={verify})"
        return queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.fixture
def env(cache, psh, reset_sc, monkeypatch):
    sc = reset_sc
    sc.config = dict(CONFIG)
    sc.options = psh.parse_args(["--date", "2026-03-31"])
    fetch = FakeFetch(cache.httpseam)
    sleeps = []
    monkeypatch.setattr(cache.httpseam, "fetch", fetch)
    monkeypatch.setattr(cache.httpseam, "sleep", sleeps.append)
    return types.SimpleNamespace(sc=sc, psh=psh, cache=cache, fetch=fetch, sleeps=sleeps)


def _ctx(env, fqdns=(FQDN,), framework="wordpress"):
    ctx = env.sc.SiteContext({"name": SITE, "framework": framework})
    ctx["fqdns_behind_cloudflare"] = list(fqdns)
    return ctx


def _resp(env, url, *, status=200, html="", error=None, insecure=False, final=None,
          detail="", **headers):
    base = {"cf-cache-status": "HIT", "cache-control": YEAR}
    base.update(headers)
    return env.cache.httpseam.FetchResult(
        url=url, final_url=final or url, status_code=None if error else status,
        headers={k: v for k, v in base.items() if v is not None},
        text=html, error=error, redirect_chain=[], insecure=insecure,
        error_detail=detail)


def test_happy_path_no_items_no_notices(env):
    env.fetch.add(MAIN, _resp(env, MAIN))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert ctx["notices"] == []


def test_no_proxied_fqdns_is_a_noop(env):
    ctx = _ctx(env, fqdns=())
    env.cache.check_cloudflare_cache(ctx)
    assert env.fetch.calls == []


def test_miss_persistent_after_three_attempts(env):
    miss = _resp(env, MAIN, **{"cf-cache-status": "MISS"})
    env.fetch.add(MAIN, miss, miss, miss)
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert env.sleeps == [2, 2]
    assert len(ctx["notices"]) == 1
    assert "miss-persistent" in ctx["notices"][0]["csv"]


def test_miss_then_hit_no_item(env):
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cf-cache-status": "MISS"}), _resp(env, MAIN))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert env.sleeps == [2]
    assert ctx["notices"] == []


def test_expired_never_retries(env):
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cf-cache-status": "EXPIRED"}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert env.sleeps == []
    assert ctx["notices"] == []


def test_uncacheable_miss_never_retries(env):
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cf-cache-status": "MISS",
                                            "cache-control": "no-store, max-age=60"}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert env.sleeps == []
    csv = ctx["notices"][0]["csv"]
    assert "miss-persistent" not in csv and "cc-no-store" in csv


def test_retry_fetch_error_ends_protocol_itemlessly(env):
    miss = _resp(env, MAIN, **{"cf-cache-status": "MISS"})
    env.fetch.add(MAIN, miss, _resp(env, MAIN, error="timeout"))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert env.sleeps == [2]
    assert ctx["notices"] == []  # neither miss-persistent nor a transport item


def test_invalid_cert_flagged_then_insecure_battery_continues(env):
    env.fetch.add(MAIN, _resp(env, MAIN, error="cert"))
    env.fetch.add(MAIN, _resp(env, MAIN, insecure=True, **{"cache-control": None}),
                  verify=False)
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    csv = ctx["notices"][0]["csv"]
    assert "invalid-cert" in csv and "no-cache-control" in csv
    assert (MAIN, False) in env.fetch.calls


def test_challenge_short_circuits(env):
    env.fetch.add(MAIN, _resp(env, MAIN, error="challenge"))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert ctx["notices"][0]["csv"].endswith(",challenge")
    assert len(env.fetch.calls) == 1  # nothing else fetched


def test_cross_fqdn_redirect_drops_url_without_item(env, capsys):
    env.fetch.add(MAIN, _resp(env, MAIN, error="cross_fqdn_redirect",
                              final="https://example.edu/"))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert ctx["notices"] == []
    assert "redirects to another FQDN" in capsys.readouterr().out


def test_non_2xx_main_page_stops_and_is_not_mined(env):
    html = '<a href="/never-fetched">x</a>'
    env.fetch.add(MAIN, _resp(env, MAIN, status=500, html=html))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert [u for u, _ in env.fetch.calls] == [MAIN]
    assert ctx["notices"][0]["csv"].endswith(",http-error")


def test_request_failed_reason_travels_to_notice(env):
    env.fetch.add(MAIN, _resp(env, MAIN, error="connection", detail="connection refused"))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert "request-failed" in ctx["notices"][0]["csv"]
    assert "connection refused" in ctx["notices"][0]["message"]


def test_linked_pages_and_assets_are_tested(env):
    page_url = f"https://{FQDN}/about"
    asset_url = f"https://{FQDN}/js/app.js"
    main_html = f'<a href="/about">a</a><script src="/js/app.js"></script>'
    env.fetch.add(MAIN, _resp(env, MAIN, html=main_html))
    env.fetch.add(page_url, _resp(env, page_url, **{"cache-control": "max-age=60"}))
    env.fetch.add(asset_url, _resp(env, asset_url))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    fetched = [u for u, _ in env.fetch.calls]
    assert fetched == [MAIN, page_url, asset_url]
    assert "short-cache-time" in ctx["notices"][0]["csv"]


def test_url_list_header_reports_the_pages_actually_checked(env):
    # One link is mined and checked, so the header the owner sees says "plus 1 random page".
    page_url = f"https://{FQDN}/about"
    env.fetch.add(MAIN, _resp(env, MAIN, html='<a href="/about">a</a>',
                              **{"cache-control": None}))
    env.fetch.add(page_url, _resp(env, page_url, **{"cache-control": None}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    message = ctx["notices"][0]["message"]
    assert "URLs with this issue (checked main page plus 1 random page linked from it)" \
        in message


def test_pages_dropped_as_cross_fqdn_redirects_are_not_counted_as_checked(env):
    # The picked page is never cache-checked (no result item), so the header must not
    # claim it was: the count falls back to "main page only".
    page_url = f"https://{FQDN}/about"
    env.fetch.add(MAIN, _resp(env, MAIN, html='<a href="/about">a</a>',
                              **{"cache-control": None}))
    env.fetch.add(page_url, _resp(env, page_url, error="cross_fqdn_redirect",
                                  final="https://elsewhere.example.edu/about"))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    message = ctx["notices"][0]["message"]
    assert "URLs with this issue (checked main page only)" in message
    assert "random page" not in message


def test_a_page_that_errors_is_still_counted_because_it_is_listed(env):
    # A picked page that times out gets a result item and so appears in a URL list; the
    # header's count must cover it.
    page_url = f"https://{FQDN}/about"
    env.fetch.add(MAIN, _resp(env, MAIN, html='<a href="/about">a</a>',
                              **{"cache-control": None}))
    env.fetch.add(page_url, _resp(env, page_url, error="timeout"))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    messages = " ".join(n["message"] for n in ctx["notices"])
    assert "checked main page plus 1 random page linked from it" in messages
    assert page_url in messages


def test_a_cert_failure_that_then_redirects_off_fqdn_is_still_counted(env):
    # _test_url emits invalid-cert BEFORE re-fetching insecurely; if that re-fetch
    # redirects cross-FQDN the page still contributed a listed URL, so it must be counted.
    page_url = f"https://{FQDN}/about"
    env.fetch.add(MAIN, _resp(env, MAIN, html='<a href="/about">a</a>',
                              **{"cache-control": None}))
    env.fetch.add(page_url, _resp(env, page_url, error="cert"))
    env.fetch.add(page_url, _resp(env, page_url, error="cross_fqdn_redirect",
                                  final="https://elsewhere.example.edu/about"),
                  verify=False)
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    messages = " ".join(n["message"] for n in ctx["notices"])
    assert page_url in messages  # listed under invalid-cert
    assert "checked main page plus 1 random page linked from it" in messages
    assert "checked main page only" not in messages


def test_a_timed_out_page_counts_as_checked_but_not_as_an_asset_source(env):
    # pages=1 (it has a result item and is listed) but asset_pages=0 (never mined).
    page_url = f"https://{FQDN}/about"
    asset_url = f"https://{FQDN}/js/app.js"
    env.fetch.add(MAIN, _resp(env, MAIN,
                              html='<a href="/about">a</a><script src="/js/app.js"></script>'))
    env.fetch.add(page_url, _resp(env, page_url, error="timeout"))
    env.fetch.add(asset_url, _resp(env, asset_url, **{"cache-control": None}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    messages = " ".join(n["message"] for n in ctx["notices"])
    assert "checked main page plus 1 random page linked from it" in messages   # the timeout
    assert "checked static assets on the main page only" in messages           # not mined


def test_asset_items_get_an_asset_scoped_header(env):
    asset_url = f"https://{FQDN}/js/app.js"
    env.fetch.add(MAIN, _resp(env, MAIN, html='<script src="/js/app.js"></script>'))
    env.fetch.add(asset_url, _resp(env, asset_url, **{"cache-control": None}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    message = ctx["notices"][0]["message"]
    assert "(checked static assets on the main page only)" in message


def test_identical_fqdns_consolidate_different_split(env):
    fqdn2 = "www2.example.edu"
    main2 = f"https://{fqdn2}/"
    # identical problem -> one notice:
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    env.fetch.add(main2, _resp(env, main2, **{"cache-control": None}))
    ctx = _ctx(env, fqdns=(FQDN, fqdn2))
    env.cache.check_cloudflare_cache(ctx)
    assert len(ctx["notices"]) == 1
    assert f"{FQDN}+{fqdn2}" in ctx["notices"][0]["csv"]

    # different problems -> two notices:
    env.fetch.responses.clear()
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    env.fetch.add(main2, _resp(env, main2, **{"set-cookie": ["a=1"]}))
    ctx2 = _ctx(env, fqdns=(FQDN, fqdn2))
    env.cache.check_cloudflare_cache(ctx2)
    assert len(ctx2["notices"]) == 2


def test_primary_domain_only_tests_primary_fqdn(env):
    # A primary custom domain is set: only it is cache-checked; the other proxied FQDN
    # is skipped entirely (no fetch, no notice for it).
    fqdn2 = "www2.example.edu"
    main2 = f"https://{fqdn2}/"
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    ctx = _ctx(env, fqdns=(FQDN, fqdn2))
    ctx["primary_domain"] = [FQDN]
    env.cache.check_cloudflare_cache(ctx)
    assert [u for u, _ in env.fetch.calls] == [MAIN]  # main2 never fetched
    assert ctx["notices"][0]["csv"] == f"{SITE},cloudflare-cache,{FQDN},no-cache-control"


def test_primary_domain_not_behind_cloudflare_is_a_noop(env):
    # Primary is set but is not itself proxied through Cloudflare (not in the behind-CF
    # list): nothing is checked, and the other proxied FQDN is still skipped.
    fqdn2 = "www2.example.edu"
    ctx = _ctx(env, fqdns=(fqdn2,))
    ctx["primary_domain"] = [FQDN]  # FQDN is not in fqdns_behind_cloudflare
    env.cache.check_cloudflare_cache(ctx)
    assert env.fetch.calls == []
    assert ctx["notices"] == []


def test_csv_contract(env):
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert ctx["notices"][0]["csv"] == f"{SITE},cloudflare-cache,{FQDN},no-cache-control"


def test_rng_determinism_same_site_and_date(env):
    links = "".join(f'<a href="/p{i}">x</a>' for i in range(8))
    for run in range(2):
        env.fetch.responses.clear()
        env.fetch.calls.clear()
        env.fetch.add(MAIN, _resp(env, MAIN, html=links))
        for i in range(8):
            url = f"https://{FQDN}/p{i}"
            env.fetch.add(url, _resp(env, url))
        env.cache.check_cloudflare_cache(_ctx(env))
        fetched = tuple(u for u, _ in env.fetch.calls)
        if run == 0:
            first = fetched
    assert fetched == first  # same site + same report date -> same selections


def test_umich_vs_generic_language(env):
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    env.sc.config["UMich"] = {"enabled": True}
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)
    assert "documentation.its.umich.edu" in ctx["notices"][0]["message"]

    env.fetch.responses.clear()
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    env.sc.config["UMich"] = {"enabled": False}
    ctx2 = _ctx(env)
    env.cache.check_cloudflare_cache(ctx2)
    assert "documentation.its.umich.edu" not in ctx2["notices"][0]["message"]
    assert "developer.mozilla.org" in ctx2["notices"][0]["message"]


def test_items_print_immediately_at_verbosity_zero(env, capsys):
    env.fetch.add(MAIN, _resp(env, MAIN, **{"cache-control": None}))
    assert env.sc.options.verbose == 0
    env.cache.check_cloudflare_cache(_ctx(env))
    assert "no Cache-Control header" in capsys.readouterr().out


def test_rich_markup_in_remote_urls_does_not_crash_verbose_runs(env):
    # Regression (code review): remote-derived URLs reach sc.debug/console.log; an
    # un-escaped '[/red]'-shaped sequence raised rich.errors.MarkupError at -v/-vvv.
    env.sc.options = env.psh.parse_args(["--date", "2026-03-31", "-vvv"])
    evil_page = f"https://{FQDN}/p[/red]x"
    env.fetch.add(MAIN, _resp(env, MAIN, html='<a href="/p[/red]x">x</a>'))
    env.fetch.add(evil_page, _resp(env, evil_page, **{"cache-control": None}))
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)  # must not raise MarkupError
    assert "no-cache-control" in ctx["notices"][0]["csv"]


def test_unknown_fetch_error_degrades_to_request_failed(env):
    # Regression (code review): _transport_item must .get-fallback, never KeyError, when
    # FetchResult.error carries a value outside its map (enum drift, or 'cert' surfacing
    # from the insecure refetch via the string-match fallback).
    env.fetch.add(MAIN, _resp(env, MAIN, error="cert"))
    env.fetch.add(MAIN, _resp(env, MAIN, error="cert", insecure=True), verify=False)
    ctx = _ctx(env)
    env.cache.check_cloudflare_cache(ctx)  # must not raise KeyError
    csv = ctx["notices"][0]["csv"]
    assert "invalid-cert" in csv and "request-failed" in csv
