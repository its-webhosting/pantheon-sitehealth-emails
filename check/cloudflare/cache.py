"""Per-site Cloudflare cache-configuration checks (site_post_dns hook) — orchestration.

For each FQDN in site_context["fqdns_behind_cloudflare"] (custom domain, in DNS, DNS at
Cloudflare, proxied record — computed by the main loop, see the CLAUDE.md data contract):

    GET https://{fqdn}/ ── error/non-2xx? ─▶ transport/http-error item, next FQDN
       │ ok
       battery(main page) ─▶ items
       links → filter/dedupe/sort → rng pick ≤3 pages
       each picked page: GET + battery
       each successful page (main included): assets → rng pick ≤1 js/css/img → GET + battery
    items grouped per FQDN ─▶ consolidation (notices.py) ─▶ notices on site_context

All requests sequential; the RNG is seeded from site name + report date (D6) so re-runs
of the same report test the same URLs and selections rotate month to month.  Result items
print to the console the moment they occur, at every verbosity (SPEC §10); ephemeral
rich-status progress at verbosity 0, plain step lines at -v, full HTTP debug at -vvv.

MISS-retry protocol (D9), only when should_retry_miss says the object ought to cache:

    MISS ─▶ sleep 2s ─▶ refetch ── not MISS ─▶ done (cache warmed; no item)
                          └─ MISS ─▶ sleep 2s ─▶ refetch ── not MISS ─▶ done
                                                   └─ MISS ─▶ item: miss-persistent
    (any fetch error during a retry ends the protocol with no item; retries examine
    Cf-Cache-Status only and are never re-run through the battery)
"""

import random
from datetime import datetime, timezone

from rich.markup import escape as rich_escape

import script_context as sc

from . import httpseam
from .cfg import cachecheck_config
from .headers import (MISS_RETRY_ATTEMPTS, MISS_RETRY_DELAY_SECONDS, evaluate_headers,
                      should_retry_miss)
from .notices import build_cache_notices, console_line
from .pages import choose_assets, choose_pages, extract_assets, extract_page_links


def _make_rng(site_name: str, date_iso: str) -> random.Random:
    return random.Random(f"{site_name}:{date_iso}")


make_rng = _make_rng  # module attribute = test seam for selection determinism


def _step(status, message: str) -> None:
    """Progress: ephemeral status update at verbosity 0, plain -v line otherwise.
    Messages embed remote-derived URLs, so ALWAYS rich-escape (an un-escaped
    '[/...]' sequence in a URL raises rich.errors.MarkupError and aborts the run)."""
    if status is not None:
        status.update(f"[bold green]Cloudflare cache check: {rich_escape(message)}")
    else:
        sc.debug(f"Cloudflare cache check: {rich_escape(message)}")


def _debug_response(result) -> None:
    """-vvv: everything needed to debug a failed test (request, status, all headers).
    All values are remote-derived -- rich-escape every line (see _step)."""
    sc.debug(rich_escape(
        f"GET {result.url}"
        + (f" -> {result.final_url} (redirects: {result.redirect_chain})"
           if result.redirect_chain else "")
        + f" status={result.status_code} error={result.error or 'none'}"
        + (" INSECURE" if result.insecure else "")),
        level=3)
    for key, value in sorted(result.headers.items()):
        sc.debug(rich_escape(f"    {key}: {value}"), level=3)


def _emit(items: list, item: dict) -> None:
    """Record a result item and print it immediately (every verbosity, SPEC §10)."""
    items.append(item)
    sc.console.print(f":exclamation: [bold red]{rich_escape(console_line(item))}")


def _transport_item(result, kind: str, cfg: dict) -> dict:
    error_to_id = {"timeout": "timeout", "challenge": "challenge",
                   "connection": "request-failed",
                   "too_many_redirects": "too-many-redirects"}
    # .get fallback: any FetchResult.error value this map does not know (enum drift, or
    # 'cert' surfacing from the insecure refetch via the string-match fallback) must
    # degrade to a request-failed item, never a run-killing KeyError.
    item_id = error_to_id.get(result.error, "request-failed")
    params = {}
    if item_id == "timeout":
        params["timeout"] = cfg["timeout"]
    elif item_id == "request-failed":
        params["reason"] = result.error_detail or result.error or "connection failed"
    elif item_id == "too-many-redirects":
        params["max_redirects"] = httpseam.MAX_REDIRECTS
    return {"id": item_id, "kind": kind, "url": result.url, "params": params}


def _run_miss_retries(result, url: str, fqdn: str, cfg: dict, items: list, found: list,
                      kind: str, status, pool) -> None:
    """D9: distinguish 'cache warming up' from 'never caches' for a cacheable MISS."""
    if not should_retry_miss(result.headers, found):
        return
    for _attempt in range(MISS_RETRY_ATTEMPTS):
        _step(status, f"{fqdn}: MISS on {url}; waiting {MISS_RETRY_DELAY_SECONDS}s to re-request")
        httpseam.sleep(MISS_RETRY_DELAY_SECONDS)
        retry = httpseam.fetch(url, fqdn=fqdn, timeout=cfg["timeout"],
                               user_agent=cfg["user_agent"], verify=not result.insecure,
                               pool=pool)
        _debug_response(retry)
        if retry.error:
            # Any fetch error ends the protocol: no miss-persistent, no transport item
            # (the original response was already evaluated), no insecure retry.
            sc.debug(rich_escape(f"{url}: re-request failed ({retry.error}); ending MISS re-checks"))
            return
        if (retry.headers.get("cf-cache-status") or "").upper() != "MISS":
            return  # the object reached the cache after all
    _emit(items, {"id": "miss-persistent", "kind": kind, "url": url, "params": {}})


def _test_url(url: str, fqdn: str, cfg: dict, items: list, *, is_main_page: bool,
              kind: str, status, pool):  # -> FetchResult | None
    """Fetch one URL and run the battery; transport policy in one place (SPEC §8.8).
    Returns the FetchResult the battery ran against (callers mine ONLY successful 2xx
    results for links/assets), or an errored result."""
    _step(status, f"{fqdn}: fetching {kind} {url}")
    result = httpseam.fetch(url, fqdn=fqdn, timeout=cfg["timeout"],
                            user_agent=cfg["user_agent"], pool=pool)
    _debug_response(result)

    if result.error == "cert":
        # PROMPT: flag the invalid certificate, then check the response anyway
        # (insecurely) so the owner still gets cache findings for this URL.
        _emit(items, {"id": "invalid-cert", "kind": kind, "url": url, "params": {}})
        result = httpseam.fetch(url, fqdn=fqdn, timeout=cfg["timeout"],
                                user_agent=cfg["user_agent"], verify=False, pool=pool)
        _debug_response(result)

    if result.error == "cross_fqdn_redirect":
        # Console note only, NO result item (PROMPT rule); the URL is dropped.
        sc.console.print(f"[yellow]{rich_escape(url)} ({kind}): redirects to another "
                         f"FQDN ({rich_escape(result.final_url)}); skipping")
        return result
    if result.error:
        _emit(items, _transport_item(result, kind, cfg))
        return result

    found = evaluate_headers(result.headers, is_main_page=is_main_page, kind=kind,
                             now=datetime.now(timezone.utc),
                             status_code=result.status_code)
    for item in found:
        item["url"] = url
        _emit(items, item)
    # (found items are appended inside _emit; nothing more to collect here)

    _run_miss_retries(result, url, fqdn, cfg, items, found, kind, status, pool)
    return result


def _ok(result) -> bool:
    return (result is not None and result.error is None
            and result.status_code is not None and 200 <= result.status_code < 300)


def _check_fqdn(fqdn: str, cfg: dict, rng, status) -> (list, dict):
    """Returns the FQDN's result items and the sizes of the two SEPARATE samples the
    notice's URL-list headers report to the owner:

        "pages"       -- pages beyond the main page that were actually checked.  NOT the
                         number selected: a pick dropped as a cross-FQDN redirect is never
                         checked and yields no result item, so it must not be counted,
                         while a pick that errors or returns non-2xx IS counted because it
                         gets a result item and so appears in a URL list under the count.
        "asset_pages" -- pages (beyond the main page) that were mined for assets.  Only
                         pages with a usable body are mined, so this is <= "pages": a pick
                         that timed out is a checked page but never yields an asset.

    One number cannot serve both: an asset item's header would otherwise claim assets were
    sampled from pages that were never opened for assets.
    """
    items = []
    # One connection pool per FQDN: TLS handshakes are paid once per FQDN (per verify
    # mode) instead of once per URL; cookies are still never sent (the pool clears the
    # jar before every request).
    with httpseam.ClientPool(cfg["timeout"], cfg["user_agent"]) as pool:
        main = _test_url(f"https://{fqdn}/", fqdn, cfg, items, is_main_page=True,
                         kind="page", status=status, pool=pool)
        if not _ok(main):
            # link/asset steps need a successful body; move on (PROMPT)
            return items, {"pages": 0, "asset_pages": 0}

        links = extract_page_links(main.text, fqdn, main.final_url)
        picks = choose_pages(links, rng)
        sc.debug(rich_escape(f"{fqdn}: {len(links)} candidate link(s); testing {picks or 'none'}"))

        pages = [main]
        checked_pages = 0
        for url in picks:
            before = len(items)
            result = _test_url(url, fqdn, cfg, items, is_main_page=False, kind="page",
                               status=status, pool=pool)
            # A pick counts as checked when its battery ran OR it produced a result item
            # (its URL is then listed under the header's count).  Testing for an item --
            # rather than for `error != "cross_fqdn_redirect"` -- is what keeps the
            # cert-then-cross-FQDN path counted: _test_url emits invalid-cert and only
            # then re-fetches insecurely, and that re-fetch may redirect off the FQDN.
            if _ok(result) or len(items) > before:
                checked_pages += 1
            if _ok(result):
                pages.append(result)

        for page in pages:
            assets = extract_assets(page.text, fqdn, page.final_url)
            chosen = choose_assets(assets, rng)
            if chosen:
                sc.debug(rich_escape(f"{fqdn}: testing asset(s) from {page.final_url}: "
                                     f"{[url for _cls, url in chosen]}"))
            for _cls, url in chosen:
                _test_url(url, fqdn, cfg, items, is_main_page=False, kind="asset",
                          status=status, pool=pool)
    return items, {"pages": checked_pages, "asset_pages": len(pages) - 1}


def check_cloudflare_cache(site_context) -> None:
    """The site_post_dns hook."""
    fqdns = site_context.get("fqdns_behind_cloudflare") or []
    if not fqdns:
        return
    # If the site has a primary custom domain set, that is the one FQDN visitors are
    # redirected to, so cache-check only it and skip every other custom domain FQDN.
    # (primary_domain is a 0-or-1 element list of custom-domain names; when the primary
    # is not itself behind Cloudflare the intersection is empty and there is nothing to
    # check.)
    primary_domain = site_context.get("primary_domain") or []
    if primary_domain:
        fqdns = [f for f in fqdns if f in primary_domain]
        if not fqdns:
            return
    cfg = cachecheck_config()
    rng = make_rng(site_context["site"]["name"], sc.options.date.isoformat())

    items_by_fqdn = {}
    sample_by_fqdn = {}

    def run(status):
        for fqdn in sorted(fqdns):
            _step(status, f"testing {fqdn}")
            items_by_fqdn[fqdn], sample_by_fqdn[fqdn] = _check_fqdn(fqdn, cfg, rng, status)

    if sc.options.verbose == 0:
        # Ephemeral progress; no other rich Live/status is active at site_post_dns (the
        # only other user is run_terminus, whose status context has already exited).
        with sc.console.status("[bold green]Cloudflare cache check") as status:
            run(status)
    else:
        run(None)

    for notice in build_cache_notices(
            site_context["site"]["name"], items_by_fqdn,
            umich=sc.umich_enabled(),
            doc_url=cfg["report_doc_url"],
            framework=site_context["site"].get("framework", ""),
            sample_by_fqdn=sample_by_fqdn):
        site_context.add_notice(notice)
