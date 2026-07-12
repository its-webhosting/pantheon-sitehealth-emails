"""PURE result-item language (console + report HTML, U-M and generic variants),
cross-FQDN consolidation, and notice assembly for the Cloudflare cache check.

Consolidation (SPEC §9): an item's identity is (id, kind, params) -- the URL is excluded --
and a FQDN's signature is the frozenset of its item identities.  FQDNs with identical
signatures share ONE notice listing all of them (PROMPT step 3); FQDNs with no items get
no notice.  All notices carry the csv key `cloudflare-cache`.

Language rules (SPEC §12): console lines are one-line/technical/no doc links; report HTML
is short, plain-language, actionable, one primary doc link.  U-M variants link
documentation.its.umich.edu (`{doc_url}#<item-id>` plus CMS-appropriate install docs on
framework-relevant items, D15); generic variants use public docs only and NEVER emit
doc_url (its default is a U-M URL).  `timeout`/`request-failed` generic variants are
"steps only" (no natural public doc).  NEVER suggest disabling or bypassing caching.

Owner-facing text always agrees in number: an item's sentence is written for the count of
URLs listed beneath it ("This page ..." / "These pages ..."), counts are spelled out
("1 hour" / "2 hours", never "2 hour(s)"), and each URL list is introduced by a header
naming how many pages were sampled.

Escaping: every remotely-derived string (URL, header value, error reason) passes through
html.escape for display and sc.escape_url for hrefs -- notices are HTML shown to owners.
"""

import html

import script_context as sc

# ── Documentation links ─────────────────────────────────────────────────────────────
# U-M pages (never fetched by the program; fragments per the verified anchor inventory --
# node/5110's ids are literally "rule 1".."rule 4", hence the %20):
NODE_4241 = "https://documentation.its.umich.edu/node/4241"   # Managing Cloudflare Caching
NODE_5110 = "https://documentation.its.umich.edu/node/5110"   # U-M Managed Cache Rules
NODE_5110_COOKIES = NODE_5110 + "#rule%202"                    # login/session-cookie bypass list
NODE_5114 = "https://documentation.its.umich.edu/node/5114"   # WP umich-cloudflare plugin
NODE_4242 = "https://documentation.its.umich.edu/node/4242"   # Drupal Cloudflare module

# Public docs (generic variants):
_MDN = "https://developer.mozilla.org/en-US/docs/Web/HTTP/"
MDN_CACHE_CONTROL = _MDN + "Headers/Cache-Control"
MDN_SET_COOKIE = _MDN + "Headers/Set-Cookie"
MDN_EXPIRES = _MDN + "Headers/Expires"
MDN_STATUS = _MDN + "Status"
MDN_REDIRECTIONS = _MDN + "Redirections"
CF_CACHE_RESPONSES = "https://developers.cloudflare.com/cache/concepts/cache-responses/"
CF_DEFAULT_CACHE = "https://developers.cloudflare.com/cache/concepts/default-cache-behavior/"
CF_CHALLENGES = "https://developers.cloudflare.com/cloudflare-challenges/"
PANTHEON_COOKIES = "https://docs.pantheon.io/cookies"
PANTHEON_CERTS = "https://docs.pantheon.io/guides/custom-certificates"

# Item ids that get the CMS-appropriate U-M install-doc link (D15):
_FRAMEWORK_RELEVANT = {"no-cache-control", "no-max-age", "short-cache-time",
                       "set-cookie", "set-cookie-bypass"}

# ── Console lines (one line, technical, no doc links; printed as items occur) ───────
_CONSOLE = {
    "http-error": "HTTP {status}, cannot check caching",
    "cf-status-missing": "no Cf-Cache-Status header - response may not be served via Cloudflare",
    "cf-status-uncacheable": "Cf-Cache-Status {status} - not being cached",
    "no-cache-control": "no Cache-Control header",
    "no-max-age": "Cache-Control has no max-age/s-maxage",
    "short-cache-time": "cache time {seconds}s < 3 days",
    "cc-private": "Cache-Control contains private",
    "cc-no-cache": "Cache-Control contains no-cache",
    "cc-no-store": "Cache-Control contains no-store",
    "cc-must-revalidate": "Cache-Control contains {directive}",
    "expires-short": "Expires < 3 days and no max-age",
    "set-cookie": "Set-Cookie on public content: {cookies}",
    "set-cookie-bypass": "Cf-Cache-Status BYPASS caused by Set-Cookie: {cookies}",
    "miss-persistent": "still MISS after 3 attempts - cacheable but never cached",
    "timeout": "no response within {timeout}s",
    "invalid-cert": "TLS certificate invalid",
    "challenge": "Cloudflare challenge (cf-mitigated) - cannot check",
    "request-failed": "request failed ({reason})",
    "too-many-redirects": "more than {max_redirects} redirects",
}


def console_line(item: dict) -> str:
    detail = _CONSOLE[item["id"]].format(**item["params"])
    return f"{item['url']} ({item['kind']}): {detail}"


# ── Report HTML per item ─────────────────────────────────────────────────────────────
def _a(url: str, text: str) -> str:
    return f'<a href="{sc.escape_url(url)}">{html.escape(text)}</a>'


def _plural(count: int, singular: str) -> str:
    """'1 hour' / '2 hours' -- owner-facing text never uses '(s)'."""
    return f"{count} {singular if count == 1 else singular + 's'}"


def _kind_noun(item: dict) -> str:
    """The owner-facing word for an item's kind; the ONE place kinds are named."""
    return "page" if item["kind"] == "page" else "static asset"


def _human_seconds(seconds: int) -> str:
    if seconds >= 86400:
        return _plural(seconds // 86400, "day")
    if seconds >= 3600:
        return _plural(seconds // 3600, "hour")
    if seconds >= 60:
        return _plural(seconds // 60, "minute")
    return _plural(seconds, "second")


def _cookie_phrase(cookies: str, count: int) -> str:
    """'a cookie (<code>sessionid</code>)' / 'cookies (<code>a, b</code>)'.  The count comes
    from the item's `cookie_count` param, NOT from re-splitting the display string: a
    malformed Set-Cookie can yield one cookie whose *name* contains a comma."""
    lead = "cookies" if count > 1 else "a cookie"
    return f"{lead} (<code>{html.escape(cookies)}</code>)"


def _url_list_header(counts: list, kind: str) -> str:
    """The line introducing an item's URL list: says what was checked, so an owner can see
    that a short list is a sample, not an exhaustive audit of their site.

    `counts` is the per-FQDN sample size for THIS item's kind, one entry per FQDN in the
    consolidated group -- pages and static assets are sampled by different mechanisms, so
    each kind describes its own sample.  A group consolidates on item signature, not on
    how many pages each FQDN happened to have to sample, so the counts can differ; the
    header then says "up to N", which is true of every FQDN listed.  Reducing them to one
    number (a min or a max) cannot work: the URL list aggregates URLs from every FQDN in
    the group, so a min can render "main page only" above a list of sub-page URLs, and a
    max can assert a sample size no single FQDN reached.
    """
    scope = "static assets on the main page" if kind == "asset" else "main page"
    biggest = max(counts) if counts else 0
    if biggest <= 0:  # nothing beyond the main page anywhere in the group
        return f"URLs with this issue (checked {scope} only)"
    # "up to" only when the group's FQDNs actually disagree; an exact count is friendlier.
    approximate = "up to " if len(set(counts)) > 1 else ""
    return (f"URLs with this issue (checked {scope} plus "
            f"{approximate}{_plural(biggest, 'random page')} linked from it)")


def _cms_link(framework: str):  # -> str | None
    framework = (framework or "").lower()
    if framework.startswith("wordpress"):
        return _a(NODE_5114, "umich-cloudflare plugin documentation")
    if framework.startswith("drupal"):
        return _a(NODE_4242, "Cloudflare module documentation")
    return None


def _item_html(item: dict, *, umich: bool, doc_url: str, framework: str,
               count: int = 1) -> str:
    """One short, actionable sentence-or-two of HTML for a distinct item.  U-M variants
    link {doc_url}#<id>; generic variants never do.

    `count` is how many URLs the notice lists under this item, so the sentence agrees in
    number with the list beneath it ("This page ..." vs. "These pages ...")."""
    item_id = item["id"]
    p = item["params"]
    many = count > 1
    noun = _kind_noun(item)
    nouns = noun + "s"
    subject = f"These {nouns}" if many else f"This {noun}"          # "These pages"
    object_ = f"these {nouns}" if many else f"this {noun}"          # "... for these pages"
    possessive = f"These {nouns}'" if many else f"This {noun}'s"    # "These pages' headers"
    it, its = ("them", "their") if many else ("it", "its")
    is_, has_hdr = ("are", "headers have") if many else ("is", "header has")
    contains_hdr = "headers contain" if many else "header contains"
    learn = _a(f"{doc_url}#{item_id}", "How to fix this") if umich else None
    # Appended to items whose fix is a site-wide configuration change: the listed URLs are
    # a sample, not the full extent of the problem, and owners read them as the extent.
    sitewide = (f" Apply this to all {nouns} site-wide &mdash; the {'ones' if many else 'one'} "
                f"listed below {'are' if many else 'is'} only what we sampled.")

    if item_id == "http-error":
        text = (f"{subject} returned an error (HTTP {int(p['status'])}), so {its} caching "
                f"could not be checked. Fix the {'errors' if many else 'error'}, then the "
                f"next report will check {it}.")
        links = [learn] if umich else [_a(MDN_STATUS, "About HTTP status codes")]
    elif item_id == "cf-status-missing":
        text = (f"Cloudflare did not report a cache status for {object_}; "
                f"{'they' if many else 'it'} may not be fully protected or accelerated by "
                f"Cloudflare. Please investigate so your site gets Cloudflare's full "
                f"protection, cost savings, and performance.")
        links = [learn] if umich else [_a(CF_CACHE_RESPONSES, "About Cloudflare cache statuses")]
    elif item_id == "cf-status-uncacheable":
        text = (f"Cloudflare reports cache status <code>{html.escape(str(p['status']))}</code>, "
                f"meaning {object_} {is_} not served from Cloudflare's cache. Please "
                f"investigate so your site gets Cloudflare's full protection, cost savings, "
                f"and performance.")
        links = ([learn, _a(NODE_5110, "U-M managed Cloudflare cache rules")] if umich
                 else [_a(CF_CACHE_RESPONSES, "About Cloudflare cache statuses"),
                       _a(CF_DEFAULT_CACHE, "What Cloudflare caches by default")])
    elif item_id == "no-cache-control":
        text = (f"{subject} {'do' if many else 'does'} not send a <code>Cache-Control</code> "
                f"header, so caching is unpredictable. Configure your site to allow caching "
                f"{it} for 31536000 seconds (1 year)." + sitewide)
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "no-max-age":
        text = (f"{possessive} <code>Cache-Control</code> {has_hdr} no usable "
                f"<code>max-age</code> or <code>s-maxage</code>. Configure your site to "
                f"allow caching {it} for 31536000 seconds (1 year)." + sitewide)
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "short-cache-time":
        text = (f"{subject} {is_} only cached for {_human_seconds(int(p['seconds']))}. "
                f"Increase the cache time to 31536000 seconds (1 year) for the full "
                f"cost-savings and performance benefit." + sitewide)
        links = ([learn, _a(NODE_4241, "Managing Cloudflare caching")] if umich
                 else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")])
    elif item_id in ("cc-private", "cc-no-cache", "cc-no-store"):
        directive = item_id[3:]
        text = (f"{possessive} <code>Cache-Control</code> {contains_hdr} "
                f"<code>{directive}</code>, which prevents Cloudflare from caching {it}. "
                f"Configure your site to remove <code>{directive}</code> from public "
                f"content." + sitewide)
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "cc-must-revalidate":
        # Same text for both variants; only the link differs.  No "unless you have a strict
        # freshness requirement" escape hatch: a real freshness requirement is met by purging
        # the stale copy, never by must-revalidate.  p["directive"] is always supplied by
        # headers.py -- a KeyError here means a caller broke the item contract.
        directive = html.escape(str(p["directive"]))
        text = (f"{possessive} <code>Cache-Control</code> {contains_hdr} "
                f"<code>{directive}</code>. You should remove it since it has no effect "
                f"until {object_} {'go' if many else 'goes'} stale, and if Cloudflare "
                f"can't reach your web server at that time, visitors will get errors "
                f"rather than {'stale copies' if many else 'a stale copy'} of {object_}."
                + sitewide)
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "expires-short":
        text = (f"{subject} "
                + (f"rely on legacy <code>Expires</code> headers that expire" if many
                   else f"relies on a legacy <code>Expires</code> header that expires")
                + f" in under 3 days. Replace {it} with "
                f"<code>Cache-Control: max-age=31536000</code> (1 year)." + sitewide)
        links = [learn] if umich else [_a(MDN_EXPIRES, "About the Expires header")]
    elif item_id == "set-cookie":
        text = (f"The site sets {_cookie_phrase(p['cookies'], p['cookie_count'])} on "
                f"{f'these public {nouns}' if many else f'this public {noun}'}, which "
                f"prevents Cloudflare from caching {it}. Configure your site not to set "
                f"cookies for visitors who are not logged in.")
        links = ([learn, _a(NODE_5110_COOKIES, "How login/session cookies affect U-M caching")]
                 if umich
                 else [_a(PANTHEON_COOKIES, "Pantheon: working with cookies"),
                       _a(MDN_SET_COOKIE, "About the Set-Cookie header")])
    elif item_id == "set-cookie-bypass":
        text = (f"Cloudflare is bypassing its cache for {object_} <em>because</em> the "
                f"site sets {_cookie_phrase(p['cookies'], p['cookie_count'])} on {it}. "
                f"Configure your site not to set cookies for visitors who are not logged "
                f"in, and caching will resume.")
        links = ([learn, _a(NODE_5110_COOKIES, "How login/session cookies affect U-M caching")]
                 if umich
                 else [_a(CF_CACHE_RESPONSES, "About Cloudflare cache statuses"),
                       _a(MDN_SET_COOKIE, "About the Set-Cookie header")])
    elif item_id == "miss-persistent":
        text = (f"{possessive} headers allow caching, but Cloudflare never served {it} from "
                f"cache across three attempts &mdash; something (for example a <code>Vary</code> "
                f"header or a cache rule) is preventing {it} from being stored. Please "
                f"investigate with your web team.")
        links = [learn] if umich else [_a(CF_DEFAULT_CACHE, "What Cloudflare caches by default")]
    elif item_id == "timeout":
        text = (f"{subject} did not respond within {_plural(int(p['timeout']), 'second')}; "
                f"visitors likely experience the same slowness. Ask your web team to "
                f"investigate the site's performance and availability.")
        links = [learn] if umich else []  # generic: steps only, no natural public doc
    elif item_id == "invalid-cert":
        text = (f"The HTTPS certificate for {object_} failed validation; browsers will "
                f"show visitors a security warning. Renew or fix the certificate.")
        links = ([learn, _a(PANTHEON_CERTS, "Pantheon: custom certificates")] if umich
                 else [_a(PANTHEON_CERTS, "Pantheon: custom certificates")])
    elif item_id == "challenge":
        text = (f"Cloudflare presented a security challenge when we requested {object_}, "
                f"so {its} caching could not be checked. If this is unexpected for public "
                f"content, review the site's security settings with your web team.")
        links = [learn] if umich else [_a(CF_CHALLENGES, "About Cloudflare challenges")]
    elif item_id == "request-failed":
        text = (f"{subject} could not be fetched ({html.escape(str(p['reason']))}); "
                f"visitors may be affected. Ask your web team to check the server and DNS "
                f"for {'these addresses' if many else 'this address'}.")
        links = [learn] if umich else []  # generic: steps only
    elif item_id == "too-many-redirects":
        text = (f"{subject} {'redirect' if many else 'redirects'} more than "
                f"{_plural(int(p['max_redirects']), 'time')} &mdash; likely "
                f"{'redirect loops' if many else 'a redirect loop'}. Fix the site's "
                f"redirect configuration.")
        links = [learn] if umich else [_a(MDN_REDIRECTIONS, "About HTTP redirections")]
    else:  # unknown id: fail loudly in tests, degrade readably in production
        text = f"A problem was detected with {object_}."
        links = [learn] if umich else []

    if umich and item_id in _FRAMEWORK_RELEVANT:
        cms = _cms_link(framework)
        if cms:
            links.append(cms)
    links = [l for l in links if l]
    return text + (" " + " &middot; ".join(links) if links else "")


# ── Consolidation + notice assembly ─────────────────────────────────────────────────
def item_key(item: dict) -> tuple:
    """Consolidation identity: everything except the URL."""
    return (item["id"], item["kind"], tuple(sorted(item["params"].items())))


def build_cache_notices(site_name: str, items_by_fqdn: dict, *, umich: bool,
                        doc_url: str, framework: str, sample_by_fqdn: dict) -> list:
    """One notice (type 'info', magnifying-glass icon) per group of FQDNs whose items are
    identical except for the URLs tested (PROMPT step 3).  Returns notice dicts ready for
    site_context.add_notice.

    `sample_by_fqdn` maps FQDN -> {"pages": n, "asset_pages": n} (see cache._check_fqdn):
    how many pages beyond the main page were checked there, and how many of those were
    mined for assets.  Each item's URL-list header is built from the counts of its OWN
    kind across the group's FQDNs -- see `_url_list_header` for why they are not reduced
    to a single number here."""
    populated = {fqdn: items for fqdn, items in items_by_fqdn.items() if items}
    if not populated:
        return []

    groups = {}  # signature -> [fqdn, ...] (fqdns iterated sorted, so groups stay sorted)
    for fqdn in sorted(populated):
        signature = frozenset(item_key(i) for i in populated[fqdn])
        groups.setdefault(signature, []).append(fqdn)

    notices = []
    for signature, fqdns in sorted(groups.items(), key=lambda kv: kv[1][0]):
        # Distinct items in first-occurrence order (all group members share the same set):
        first = populated[fqdns[0]]
        seen, distinct = set(), []
        for item in first:
            key = item_key(item)
            if key not in seen:
                seen.add(key)
                distinct.append(item)

        def sample_counts(kind: str, fqdns=fqdns) -> list:
            key = "asset_pages" if kind == "asset" else "pages"
            return [sample_by_fqdn.get(fqdn, {}).get(key, 0) for fqdn in fqdns]

        blocks = []
        for item in distinct:
            key = item_key(item)
            url_lines = []
            seen_urls = set()  # the same asset can be tested from several pages; the
            for fqdn in fqdns:  # owner-visible list must not repeat a URL
                for match in populated[fqdn]:
                    if item_key(match) == key and match["url"] not in seen_urls:
                        seen_urls.add(match["url"])
                        url_lines.append(f'<li>{_a(match["url"], match["url"])} '
                                         f'({_kind_noun(match)})</li>')
            # An item's URLs are all of its own kind (kind is part of item_key), and pages
            # and assets are sampled differently -- so the header describes this item's kind.
            header = html.escape(_url_list_header(sample_counts(item["kind"]), item["kind"]))
            # The header is an <li> whose child <ul> holds the URLs, rather than a <br> or a
            # styled <span>.  Native list markup is the only construct that breaks the line
            # in Outlook's Word engine (which honors no `display` value but `none`), keeps
            # the header indented under its finding in the html2text plaintext copy, AND
            # makes the URL list programmatically a child of its caption for a screen reader.
            urls = ('<ul style="list-style-type: none;">' + "\n".join(url_lines) + "</ul>")
            blocks.append(
                "<li>"
                + _item_html(item, umich=umich, doc_url=doc_url, framework=framework,
                             count=len(url_lines))
                + '<ul style="list-style-type: none;">'
                + f"<li>{header}{urls}</li>"
                + "</ul>"
                + "</li>")

        fqdn_links = ", ".join(_a(f"https://{f}/", f) for f in fqdns)
        ids = sorted({i["id"] for i in distinct})
        notices.append({
            "type": "info",  # info -> magnifying-glass icon (see script_context.icon)
            "csv": f"{site_name},cloudflare-cache,{'+'.join(fqdns)},{'+'.join(ids)}",
            "short": "improve Cloudflare caching",
            "message": (
                f"<p><strong>Cloudflare caching:</strong> some pages or files on "
                f"{fqdn_links} are not being cached by Cloudflare as effectively as they "
                f"could be. Full caching protects your site from traffic spikes, lowers "
                f"visitor counts that determine hosting costs, and makes pages load "
                f"faster.</p>\n<ul>\n" + "\n".join(blocks) + "\n</ul>"
            ),
        })
    return notices
