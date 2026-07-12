# SPEC: correct the cachecheck revalidate-directive test

**Status:** approved (survived adversarial review), not yet implemented
**Scope:** `check/cloudflare/headers.py`, `check/cloudflare/notices.py`, `docs/cloudflare-cachecheck.md`, tests

## Glossary

| Term | Meaning |
|---|---|
| **battery** | The pure per-URL header checks in `check/cloudflare/headers.py` (`evaluate_headers`). |
| **result item** | One finding: `{"id", "kind", "url", "params"}`. Ids are also the anchor slugs on the U-M documentation page. |
| **revalidate directive** | `must-revalidate` or `proxy-revalidate`. To Cloudflare (a shared cache) these mean the same thing. |
| **OCC** | Cloudflare's **Origin Cache Control** feature: whether Cloudflare honors origin `Cache-Control` directives. |
| **uncacheable response** | One whose `Cache-Control` carries `private`, `no-cache`, or `no-store`. |

MUST / MUST NOT / SHOULD are used in the RFC 2119 sense.

## Problem

The cache check treats the two revalidate directives as if they stopped Cloudflare from
caching. They do not. The misconception is baked into the code in three places:

1. **`must-revalidate`** emits `cc-must-revalidate`, whose notice says it *"defeats
   caching"* (U-M variant) / *"forces revalidation and reduces caching benefit"* (generic).
   Both are false: the directive has **no effect at all** while the response is fresh.
2. **`proxy-revalidate`** is bucketed with `private`/`no-cache`/`no-store` in the "prevents
   Cloudflare from caching" loop (`headers.py:156`). Also false — `proxy-revalidate` *is*
   `must-revalidate` scoped to shared caches, and Cloudflare is a shared cache.
3. **`cc-proxy-revalidate` sits in `_MISS_RETRY_BLOCKERS`** (`headers.py:35-39`), so the code
   believes a cache MISS is *explained* by `proxy-revalidate` and skips the MISS-retry
   protocol. Since the directive does not prevent caching, a MISS alongside it is genuinely
   unexplained — exactly what the retry protocol exists to diagnose.

Two further detection defects:

- Both directive checks sit inside the `else` branch that only runs when a
  `max-age`/`s-maxage` parses (`headers.py:153-162`). `Cache-Control: must-revalidate` with
  no `max-age` reports `no-max-age` and **never mentions `must-revalidate`**.
- `must-revalidate` is suppressed on the main page (`and not is_main_page`) — a carve-out
  that existed only because the notice wrongly told owners to remove it.

## What the directives actually do

Per RFC 9111 §5.2.2.2, `must-revalidate` does nothing while a response is fresh. Once stale,
a cache MUST NOT reuse it without successfully validating with the origin; if the origin
cannot be reached, the cache MUST generate a 504 rather than serve the stale copy.
`proxy-revalidate` (§5.2.2.7) is identical but applies only to shared caches.

### Cloudflare-specific verification (load-bearing — do not skip)

RFC semantics alone are **not** sufficient grounds for this notice, because Cloudflare only
honors these directives when **OCC** is enabled. Per
[Cloudflare's Origin Cache Control docs](https://developers.cloudflare.com/cache/concepts/cache-control/):

| Directive | OCC **disabled** | OCC **enabled** |
|---|---|---|
| `must-revalidate` | *"Cache directive is ignored and stale is served."* | *"Does not serve stale. Must revalidate for CDN and for browser."* |
| `proxy-revalidate` | *"Cache directive is ignored and stale is served."* | *"Does not serve stale. Must revalidate for CDN but not for browser."* |

- Free / Pro / Business zones have OCC **enabled by default and cannot disable it**.
- Enterprise zones toggle it per cache rule (`action_parameters.origin_cache_control`).
- **U-M's zones have OCC enabled** (confirmed by the maintainer, 2026-07-11). The notice text
  below is therefore accurate for U-M and for every non-Enterprise adopter.
- **Known limitation:** an Enterprise adopter who has deliberately *disabled* OCC would see a
  notice describing an effect their zone does not have. The tool does not inspect the zone's
  OCC setting. Accepted; revisit only if a non-U-M Enterprise adopter appears.

Cloudflare also lists `must-revalidate` among the directives that cause `stale-if-error` to
be ignored, which confirms the mechanism the notice describes.

**Deliberately out of scope:** removing `must-revalidate` does not *by itself* make Cloudflare
serve a stale copy on error — that additionally needs `stale-if-error` (and Always Online
overrides it). The notice stays single-purpose and does not mention this. A future
`no-stale-if-error` item could flag sites with no serve-stale path at all.

## Design

### Detection (`headers.py`)

Drop `proxy-revalidate` from the "prevents caching" loop and replace the `must-revalidate`
check with a single directive-agnostic one, hoisted out of the `max-age` branch and with no
main-page condition:

```python
    else:
        if seconds < MIN_CACHE_SECONDS:
            items.append(_item("short-cache-time", kind, seconds=seconds))
        for directive in ("private", "no-cache", "no-store"):   # proxy-revalidate removed
            if directive in cc:
                items.append(_item(f"cc-{directive}", kind))

    uncacheable = any(d in cc for d in ("private", "no-cache", "no-store"))
    revalidate = ("must-revalidate" if "must-revalidate" in cc
                  else "proxy-revalidate" if "proxy-revalidate" in cc
                  else None)
    if revalidate and not uncacheable:
        items.append(_item("cc-must-revalidate", kind, directive=revalidate))
```

Rules (this list is **exhaustive**):

1. The item fires for **every page and asset tested**, main page included. (This is what
   retires the main-page carve-out.)
2. It fires **whenever the directive is present**, regardless of `max-age` — the previously
   silent `must-revalidate`-with-no-`max-age` case now reports.
3. It is **suppressed on an uncacheable response** (`private`/`no-cache`/`no-store`). *Why:*
   content Cloudflare never caches cannot go stale, so the notice's stated risk cannot
   arise. Suppression does **not** contradict rule 1 — rule 1 retired the *main-page*
   carve-out, not co-occurring-directive logic.
   **Suppression keys off the `Cache-Control` header, not off the emitted items.** These are
   not the same thing: `cc-private`/`cc-no-cache`/`cc-no-store` are only emitted when a
   `max-age` parsed (they sit inside that branch — see the out-of-scope note below), so
   `Cache-Control: private, must-revalidate` with no `max-age` reports **only** `no-max-age`
   — no `cc-private`, and the revalidate item suppressed. That is correct: the page is
   uncacheable regardless of whether we happened to emit a finding saying so, and
   `no-max-age` still tells the owner to configure caching. Pinned by a test.
4. When **both** revalidate directives are present, emit **one** item naming
   `must-revalidate` (the superset), not two near-identical items for one URL.
5. The item id stays `cc-must-revalidate`; the directive actually seen goes in
   `params["directive"]`. Consolidation identity is `(id, kind, params)` (`notices.py:304`),
   so the two directives consolidate separately and each notice names the right one.
6. `cc-proxy-revalidate` is **retired**: remove it from `_CONSOLE` (`notices.py:56-77`) and
   from `_MISS_RETRY_BLOCKERS` (`headers.py:35-39`), and drop it from the
   `cc-private`/`cc-no-cache`/`cc-no-store` branch in `_item_html`. Those two are the only
   registries — there is no central item-id list. `cc-must-revalidate` MUST NOT be added to
   `_MISS_RETRY_BLOCKERS`: neither directive explains a MISS.
7. `is_main_page` becomes **unused by the battery** (verified: `headers.py:159` is its only
   reader). It stays in the signature as a reserved seam; removing it end-to-end through
   `cache.py` is a separate cleanup.

### Notice text (`notices.py`)

This is the **rendered singular** form (exactly what ships for a one-URL page finding); the
existing helpers pluralize it and swap the noun for assets. `sitewide` is the shared suffix
defined at `notices.py:171-172`.

> This page's `Cache-Control` header contains `must-revalidate`. You should remove it since
> it has no effect until this page goes stale, and if Cloudflare can't reach your web server
> at that time, visitors will get errors rather than a stale copy of this page. Apply this to
> all pages site-wide — the one listed below is only what we sampled.

- Same text for U-M and generic; they differ **only in links** (U-M gets
  `{doc_url}#cc-must-revalidate`, generic gets the MDN `Cache-Control` link).
- The removal advice is **unconditional**. NEVER add "unless this page has a strict freshness
  requirement": a real freshness requirement is met by purging the stale copy (good) or a
  shorter `s-maxage` (not good), never by `must-revalidate`.
- The `sitewide` suffix is **included**. *Why:* the directive comes from a theme, plugin, or
  server config, so it is site-wide, and the check samples only the main page plus a few
  random pages/assets. The old item omitted the suffix because it was about *where* the
  directive appeared — a rationale that dies with the main-page carve-out.
- The old "on your home page `must-revalidate` is intentional, it makes emergency alerts
  appear promptly" sentence is deleted.
- `_CONSOLE["cc-must-revalidate"]` becomes `"Cache-Control contains {directive}"` (the old
  string hardcoded `must-revalidate` and the now-obsolete `(non-main page)`).

## Consequences

- **MISS-retry:** a MISS on a URL carrying `proxy-revalidate` now triggers the retry protocol
  — up to 2 extra requests and 4s of sleeps per affected URL. Intended; the only
  runtime-behavior change outside the notice text.
- **CSV granularity is lost (accepted):** `-notices.csv` carries item ids, not params
  (`notices.py:374-377`), so `must-revalidate` and `proxy-revalidate` both appear as
  `cc-must-revalidate`. The directive remains visible in the console line and in the notice
  HTML. Accepted in exchange for one item id and one doc anchor.
- **U-M documentation page (out of repo, tracked by the maintainer):** this change orphans the
  `#cc-proxy-revalidate` anchor and *inverts* the meaning of `#cc-must-revalidate`, whose
  current text says the directive defeats caching. A `proxy-revalidate` finding will link to
  an anchor named `cc-must-revalidate`. The page should be updated before the next
  `--for-real` run.
- No security surface: `params["directive"]` is one of two **code literals**, never the raw
  header value, and is `html.escape`d regardless.

## Testing

- `tests/unit/test_cachecheck_headers.py` — the battery: fires on the main page; fires with no
  `max-age`; `proxy-revalidate` yields `cc-must-revalidate` with
  `params["directive"] == "proxy-revalidate"`; both directives yield exactly one item naming
  `must-revalidate`; **suppressed** on `private`/`no-cache`/`no-store`; `should_retry_miss` is
  now True for MISS + `proxy-revalidate` + adequate `max-age`.
- `tests/unit/test_cachecheck_consolidation.py` — the two directives do not consolidate into
  each other; the notice carries the `sitewide` suffix; the retired language is gone.
- `tests/integration/test_cachecheck_notice_render.py` — refresh syrupy snapshots
  (`./run-tests --update-goldens`) and review the diff; add a `proxy-revalidate` case.
- **Tests are load-bearing.** The e2e goldens run with `[Cloudflare].enabled = false` and MUST
  remain byte-identical. A golden diff means something is wrong — never regenerate them to
  make a failure go away.

## Docs

Update `docs/cloudflare-cachecheck.md`: the item table (`:114-115`) and the MISS-retry
sentence (`:48-50`). Note the doc has no blocker *list* — only that sentence.
