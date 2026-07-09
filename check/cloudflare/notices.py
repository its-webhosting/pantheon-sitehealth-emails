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
    "cf-status-missing": "no Cf-Cache-Status header — response may not be served via Cloudflare",
    "cf-status-uncacheable": "Cf-Cache-Status {status} — not being cached",
    "no-cache-control": "no Cache-Control header",
    "no-max-age": "Cache-Control has no max-age/s-maxage",
    "short-cache-time": "cache time {seconds}s < 3 days",
    "cc-private": "Cache-Control contains private",
    "cc-no-cache": "Cache-Control contains no-cache",
    "cc-no-store": "Cache-Control contains no-store",
    "cc-proxy-revalidate": "Cache-Control contains proxy-revalidate",
    "cc-must-revalidate": "Cache-Control contains must-revalidate (non-main page)",
    "expires-short": "Expires < 3 days and no max-age",
    "set-cookie": "Set-Cookie on public content: {cookies}",
    "set-cookie-bypass": "Cf-Cache-Status BYPASS caused by Set-Cookie: {cookies}",
    "miss-persistent": "still MISS after 3 attempts — cacheable but never cached",
    "timeout": "no response within {timeout}s",
    "invalid-cert": "TLS certificate invalid",
    "challenge": "Cloudflare challenge (cf-mitigated) — cannot check",
    "request-failed": "request failed ({reason})",
    "too-many-redirects": "more than {max_redirects} redirects",
}


def console_line(item: dict) -> str:
    detail = _CONSOLE[item["id"]].format(**item["params"])
    return f"{item['url']} ({item['kind']}): {detail}"


# ── Report HTML per item ─────────────────────────────────────────────────────────────
def _a(url: str, text: str) -> str:
    return f'<a href="{sc.escape_url(url)}">{html.escape(text)}</a>'


def _human_seconds(seconds: int) -> str:
    if seconds >= 86400:
        return f"{seconds // 86400} day(s)"
    if seconds >= 3600:
        return f"{seconds // 3600} hour(s)"
    if seconds >= 60:
        return f"{seconds // 60} minute(s)"
    return f"{seconds} second(s)"


def _cms_link(framework: str):  # -> str | None
    framework = (framework or "").lower()
    if framework.startswith("wordpress"):
        return _a(NODE_5114, "umich-cloudflare plugin documentation")
    if framework.startswith("drupal"):
        return _a(NODE_4242, "Cloudflare module documentation")
    return None


def _item_html(item: dict, *, umich: bool, doc_url: str, framework: str) -> str:
    """One short, actionable sentence-or-two of HTML for a distinct item.  U-M variants
    link {doc_url}#<id>; generic variants never do."""
    item_id = item["id"]
    p = item["params"]
    kind = "page" if item["kind"] == "page" else "static asset"
    learn = _a(f"{doc_url}#{item_id}", "How to fix this") if umich else None

    if item_id == "http-error":
        text = (f"This {kind} returned an error (HTTP {int(p['status'])}), so its caching "
                f"could not be checked. Fix the error, then the next report will check it.")
        links = [learn] if umich else [_a(MDN_STATUS, "About HTTP status codes")]
    elif item_id == "cf-status-missing":
        text = (f"Cloudflare did not report a cache status for this {kind}; it may not be "
                f"fully protected or accelerated by Cloudflare. Please investigate so your "
                f"site gets Cloudflare's full protection, cost savings, and performance.")
        links = [learn] if umich else [_a(CF_CACHE_RESPONSES, "About Cloudflare cache statuses")]
    elif item_id == "cf-status-uncacheable":
        text = (f"Cloudflare reports cache status <code>{html.escape(str(p['status']))}</code>, "
                f"meaning this {kind} is not served from Cloudflare's cache. Please "
                f"investigate so your site gets Cloudflare's full protection, cost savings, "
                f"and performance.")
        links = ([learn, _a(NODE_5110, "U-M managed Cloudflare cache rules")] if umich
                 else [_a(CF_CACHE_RESPONSES, "About Cloudflare cache statuses"),
                       _a(CF_DEFAULT_CACHE, "What Cloudflare caches by default")])
    elif item_id == "no-cache-control":
        text = (f"This {kind} does not send a <code>Cache-Control</code> header, so caching "
                f"is unpredictable. Configure your site to allow caching it for 31536000 "
                f"seconds (1 year).")
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "no-max-age":
        text = (f"This {kind}'s <code>Cache-Control</code> header has no usable "
                f"<code>max-age</code> or <code>s-maxage</code>. Configure your site to "
                f"allow caching it for 31536000 seconds (1 year).")
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "short-cache-time":
        text = (f"This {kind} is only cached for {_human_seconds(int(p['seconds']))}. "
                f"Increase the cache time to 31536000 seconds (1 year) for the full "
                f"cost-savings and performance benefit.")
        links = ([learn, _a(NODE_4241, "Managing Cloudflare caching")] if umich
                 else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")])
    elif item_id in ("cc-private", "cc-no-cache", "cc-no-store", "cc-proxy-revalidate"):
        directive = item_id[3:]
        text = (f"This {kind}'s <code>Cache-Control</code> header contains "
                f"<code>{directive}</code>, which prevents Cloudflare from caching it. "
                f"Configure your site to remove <code>{directive}</code> from public content.")
        links = [learn] if umich else [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "cc-must-revalidate":
        if umich:
            text = (f"This {kind}'s <code>Cache-Control</code> header contains "
                    f"<code>must-revalidate</code>. On your home page that is intentional "
                    f"(it makes emergency alerts appear promptly), but on other pages and "
                    f"assets it defeats caching — configure your site to remove it here.")
            links = [learn]
        else:
            text = (f"This {kind}'s <code>Cache-Control</code> header contains "
                    f"<code>must-revalidate</code>, which forces revalidation and reduces "
                    f"caching benefit. Remove it unless this specific {kind} has a strict "
                    f"freshness requirement.")
            links = [_a(MDN_CACHE_CONTROL, "About the Cache-Control header")]
    elif item_id == "expires-short":
        text = (f"This {kind} relies on a legacy <code>Expires</code> header that expires in "
                f"under 3 days. Replace it with <code>Cache-Control: max-age=31536000</code> "
                f"(1 year).")
        links = [learn] if umich else [_a(MDN_EXPIRES, "About the Expires header")]
    elif item_id == "set-cookie":
        text = (f"The site sets a cookie (<code>{html.escape(p['cookies'])}</code>) on this "
                f"public {kind}, which prevents Cloudflare from caching it. Configure your "
                f"site not to set cookies for visitors who are not logged in.")
        links = ([learn, _a(NODE_5110_COOKIES, "How login/session cookies affect U-M caching")]
                 if umich
                 else [_a(PANTHEON_COOKIES, "Pantheon: working with cookies"),
                       _a(MDN_SET_COOKIE, "About the Set-Cookie header")])
    elif item_id == "set-cookie-bypass":
        text = (f"Cloudflare is bypassing its cache for this {kind} <em>because</em> the "
                f"site sets a cookie (<code>{html.escape(p['cookies'])}</code>) here. "
                f"Configure your site not to set cookies for visitors who are not logged "
                f"in, and caching will resume.")
        links = ([learn, _a(NODE_5110_COOKIES, "How login/session cookies affect U-M caching")]
                 if umich
                 else [_a(CF_CACHE_RESPONSES, "About Cloudflare cache statuses"),
                       _a(MDN_SET_COOKIE, "About the Set-Cookie header")])
    elif item_id == "miss-persistent":
        text = (f"This {kind}'s headers allow caching, but Cloudflare never served it from "
                f"cache across three attempts — something (for example a <code>Vary</code> "
                f"header or a cache rule) is preventing it from being stored. Please "
                f"investigate with your web team.")
        links = [learn] if umich else [_a(CF_DEFAULT_CACHE, "What Cloudflare caches by default")]
    elif item_id == "timeout":
        text = (f"This {kind} did not respond within {int(p['timeout'])} seconds; visitors "
                f"likely experience the same slowness. Ask your web team to investigate the "
                f"site's performance and availability.")
        links = [learn] if umich else []  # generic: steps only, no natural public doc
    elif item_id == "invalid-cert":
        text = (f"The HTTPS certificate for this {kind} failed validation; browsers will "
                f"show visitors a security warning. Renew or fix the certificate.")
        links = ([learn, _a(PANTHEON_CERTS, "Pantheon: custom certificates")] if umich
                 else [_a(PANTHEON_CERTS, "Pantheon: custom certificates")])
    elif item_id == "challenge":
        text = (f"Cloudflare presented a security challenge when we requested this {kind}, "
                f"so its caching could not be checked. If this is unexpected for public "
                f"content, review the site's security settings with your web team.")
        links = [learn] if umich else [_a(CF_CHALLENGES, "About Cloudflare challenges")]
    elif item_id == "request-failed":
        text = (f"This {kind} could not be fetched ({html.escape(str(p['reason']))}); "
                f"visitors may be affected. Ask your web team to check the server and DNS "
                f"for this address.")
        links = [learn] if umich else []  # generic: steps only
    elif item_id == "too-many-redirects":
        text = (f"This {kind} redirects more than {int(p['max_redirects'])} times — likely a "
                f"redirect loop. Fix the site's redirect configuration.")
        links = [learn] if umich else [_a(MDN_REDIRECTIONS, "About HTTP redirections")]
    else:  # unknown id: fail loudly in tests, degrade readably in production
        text = f"A problem was detected with this {kind}."
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
                        doc_url: str, framework: str) -> list:
    """One 'warning' notice per group of FQDNs whose items are identical except for the
    URLs tested (PROMPT step 3).  Returns notice dicts ready for site_context.add_notice."""
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

        blocks = []
        for item in distinct:
            key = item_key(item)
            url_lines = []
            seen_urls = set()  # the same asset can be tested from several pages; the
            for fqdn in fqdns:  # owner-visible list must not repeat a URL
                for match in populated[fqdn]:
                    if item_key(match) == key and match["url"] not in seen_urls:
                        seen_urls.add(match["url"])
                        kind = "page" if match["kind"] == "page" else "static asset"
                        url_lines.append(
                            f'<li>{_a(match["url"], match["url"])} ({kind})</li>')
            blocks.append(
                "<li>"
                + _item_html(item, umich=umich, doc_url=doc_url, framework=framework)
                + '<ul style="list-style-type: none;">' + "\n".join(url_lines) + "</ul>"
                + "</li>")

        fqdn_links = ", ".join(_a(f"https://{f}/", f) for f in fqdns)
        ids = sorted({i["id"] for i in distinct})
        notices.append({
            "type": "warning",
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
