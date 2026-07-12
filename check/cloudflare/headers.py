"""PURE per-URL response-header battery for the Cloudflare cache-configuration check.

No I/O, no sc access: everything here is unit/property-testable in isolation.  Each rule
appends one "result item" dict:

    {"id": <rule id>, "kind": "page"|"asset", "url": <set by the caller>, "params": {...}}

The item ids are the consolidation identity (see notices.py) and the anchor slugs in the
"Understanding your Cloudflare cache report" documentation page.

Battery decision flow (see SPEC §8.6):

    status not 2xx ──▶ http-error, STOP (nothing else evaluated)
    Cf-Cache-Status ──▶ missing / not-acceptable items
    Cache-Control  ──▶ absent → no-cache-control, skip max-age-dependent rules below
                       no parseable max-age/s-maxage → no-max-age, skip max-age-dependent
                       rules below
                       max-age/s-maxage parses ──▶ < 3 days → short-cache-time
                                                    private/no-cache/no-store → one item each
                       must-revalidate/proxy-revalidate ──▶ evaluated REGARDLESS of max-age
                       (even when unparseable): one cc-must-revalidate item naming the
                       directive seen, on every page and asset, but suppressed when the
                       response is already uncacheable (private/no-cache/no-store present)
    Expires        ──▶ only when CC absent or without parseable max-age/s-maxage
    Set-Cookie     ──▶ set-cookie, or set-cookie-bypass REPLACING the BYPASS status item
"""

import email.utils
from datetime import datetime, timedelta, timezone

ACCEPTABLE_CACHE_STATUSES = {"HIT", "MISS", "EXPIRED", "STALE", "REVALIDATED", "UPDATING"}
MIN_CACHE_SECONDS = 3 * 86400        # the 3-day floor
RECOMMENDED_MAX_AGE = 31536000       # 1 year
MISS_RETRY_DELAY_SECONDS = 2
MISS_RETRY_ATTEMPTS = 2              # re-requests after the initial one (3 requests total)

# Items that make a MISS expected rather than mysterious; any of these suppresses the
# MISS-retry protocol (http-error because testing already stopped on that URL).
# NOTE: no revalidate directive belongs here -- must-revalidate/proxy-revalidate do not
# prevent Cloudflare from caching, so they never explain a MISS.
_MISS_RETRY_BLOCKERS = {
    "http-error", "no-cache-control", "no-max-age", "short-cache-time",
    "cc-private", "cc-no-cache", "cc-no-store",
    "set-cookie", "set-cookie-bypass",
}


# Cookies set by Cloudflare itself, not by the origin website.  They do not interfere with
# Cloudflare caching, so they are ignored when checking for cookies on public content.
# Compared case-insensitively (stored lowercased).
CLOUDFLARE_COOKIES = frozenset({
    "__cf_bm", "__cflb", "__cfseq", "cf_clearance", "cf_ob_info", "cf_use_ob",
    "__cfwaitingroom", "__cfruid", "_cfuvid", "cf_chl_rc_i", "cf_chl_rc_ni",
    "cf_chl_rc_m", "cf_authorization", "cf_binding", "cf_session", "cd_appsession",
    "cf_device",
})


def cookie_names(set_cookie) -> list:
    """The names (not the values) of the cookies in a response's Set-Cookie header, with
    Cloudflare's own cookies (CLOUDFLARE_COOKIES) removed.  Accepts a single header string
    or a list of them (httpx exposes multiple Set-Cookie headers as a list); returns the
    remaining names in first-seen order, de-duplicated.  Never raises."""
    if isinstance(set_cookie, str):
        raw = [set_cookie]
    elif isinstance(set_cookie, (list, tuple)):
        raw = list(set_cookie)
    else:
        return []
    names = []
    for value in raw:
        if not isinstance(value, str):
            continue
        # A Set-Cookie value is "name=value; attr; attr..."; the name is everything before
        # the first '=' of the first ';'-delimited pair.
        name = value.split(";", 1)[0].split("=", 1)[0].strip()
        if not name or name.lower() in CLOUDFLARE_COOKIES:
            continue
        if name not in names:
            names.append(name)
    return names


def parse_cache_control(value) -> dict:
    """Tolerant Cache-Control parser: lowercased directive names; int values where they
    parse, True for valueless directives, the raw string otherwise.  Never raises."""
    directives = {}
    if not isinstance(value, str):
        return directives
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, raw = part.partition("=")
        name = name.strip().lower()
        if not name:
            continue
        if not sep:
            directives[name] = True
            continue
        raw = raw.strip().strip('"')
        try:
            directives[name] = int(raw)
        except ValueError:
            directives[name] = raw
    return directives


def cache_seconds(cc: dict):  # -> int | None
    """max(max-age, s-maxage) across the PARSEABLE (int) directives; None if neither
    parsed (a `max-age=garbage` counts as absent -- same predicate everywhere)."""
    values = [cc[k] for k in ("max-age", "s-maxage") if isinstance(cc.get(k), int)]
    return max(values) if values else None


def parse_expires(value):  # -> datetime | None
    """RFC-2822 date via email.utils; naive results are treated as UTC; None on garbage."""
    if not isinstance(value, str):
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _item(item_id: str, kind: str, **params) -> dict:
    return {"id": item_id, "kind": kind, "url": None, "params": params}


def evaluate_headers(headers: dict, *, is_main_page: bool, kind: str,
                     now: datetime, status_code: int) -> list:
    """Run the battery against one response's headers (lowercased keys; 'set-cookie' may
    be a list).  Returns result items; the caller fills in each item's 'url'."""
    # is_main_page is a reserved seam: no rule currently consults it.  (The must-revalidate
    # main-page carve-out that used to read it was retired -- see
    # development/2026-07-11-cachecheck-must-revalidate/SPEC.md.)  Removing it end-to-end
    # through cache.py is a separate cleanup.
    items = []

    # Non-2xx: nothing else is evaluated for this URL (PROMPT: "do not check anything
    # else, move on"); the caller also skips link/asset extraction.
    if not 200 <= status_code < 300:
        return [_item("http-error", kind, status=status_code)]

    cf_status = headers.get("cf-cache-status")
    if cf_status is None:
        items.append(_item("cf-status-missing", kind))
    elif cf_status.upper() not in ACCEPTABLE_CACHE_STATUSES:
        items.append(_item("cf-status-uncacheable", kind, status=cf_status.upper()))

    cc_value = headers.get("cache-control")
    cc = parse_cache_control(cc_value)
    seconds = cache_seconds(cc)
    if cc_value is None:
        items.append(_item("no-cache-control", kind))
    elif seconds is None:
        items.append(_item("no-max-age", kind))
    else:
        if seconds < MIN_CACHE_SECONDS:
            items.append(_item("short-cache-time", kind, seconds=seconds))
        for directive in ("private", "no-cache", "no-store"):
            if directive in cc:
                items.append(_item(f"cc-{directive}", kind))

    # Outside the max-age branch on purpose: these directives matter whenever they are
    # present, even with no parseable cache time (that case used to be silent).
    #
    # must-revalidate and proxy-revalidate are the same thing to Cloudflare (a shared cache).
    # Neither prevents caching; both mean that once the content is stale and the origin is
    # unreachable, visitors get an error instead of a stale copy.  must-revalidate is the
    # superset, so when both are present we report it alone rather than emitting two
    # near-identical items for one URL.  Suppressed on an uncacheable response: content
    # Cloudflare never caches cannot go stale, so the risk cannot arise.
    uncacheable = any(d in cc for d in ("private", "no-cache", "no-store"))
    revalidate = ("must-revalidate" if "must-revalidate" in cc
                  else "proxy-revalidate" if "proxy-revalidate" in cc
                  else None)
    if revalidate and not uncacheable:
        items.append(_item("cc-must-revalidate", kind, directive=revalidate))

    # Expires matters only when Cache-Control provides no parseable cache time:
    expires_value = headers.get("expires")
    if expires_value is not None and (cc_value is None or seconds is None):
        expires = parse_expires(expires_value)
        if expires is not None and expires < now + timedelta(seconds=MIN_CACHE_SECONDS):
            items.append(_item("expires-short", kind))

    # Only the website's own cookies matter: Cloudflare's cookies do not affect caching and
    # are filtered out.  If nothing but Cloudflare cookies were set, there is no finding.
    names = cookie_names(headers.get("set-cookie"))
    if names:
        # Sorted so the string is order-independent: two FQDNs that set the same cookies in
        # a different header order still produce the same item and consolidate into one
        # notice (item_key folds params into the consolidation identity).
        # cookie_count travels alongside the display string: a cookie *name* can contain a
        # comma, so the notice must not recover the count by re-splitting `cookies`.
        cookies = ", ".join(sorted(names))
        count = len(names)
        if cf_status is not None and cf_status.upper() == "BYPASS":
            # The BYPASS is *caused by* the cookie: replace the generic uncacheable item
            # with the specific explanation.
            items = [i for i in items if i["id"] != "cf-status-uncacheable"]
            items.append(_item("set-cookie-bypass", kind, cookies=cookies,
                               cookie_count=count))
        else:
            items.append(_item("set-cookie", kind, cookies=cookies, cookie_count=count))

    return items


def should_retry_miss(headers: dict, items: list) -> bool:
    """True when Cf-Cache-Status is MISS but the headers say the object SHOULD cache
    (cache time at or above the 3-day floor, no disqualifying items) -- the only case
    where the 2s/retry/2s/retry protocol can distinguish 'cache warming up' from
    'never caches'.  EXPIRED/STALE/REVALIDATED/UPDATING/HIT never retry: they all prove
    the object reaches Cloudflare's cache."""
    cf_status = headers.get("cf-cache-status")
    if cf_status is None or cf_status.upper() != "MISS":
        return False
    seconds = cache_seconds(parse_cache_control(headers.get("cache-control")))
    if seconds is None or seconds < MIN_CACHE_SECONDS:
        return False
    return not any(i["id"] in _MISS_RETRY_BLOCKERS for i in items)
