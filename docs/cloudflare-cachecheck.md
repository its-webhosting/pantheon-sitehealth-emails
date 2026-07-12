# Cloudflare cache-configuration checks (`[Cloudflare.cachecheck]`)

When `[Cloudflare]` **and** `[Cloudflare.cachecheck]` are both enabled, the tool probes
each site's Cloudflare-proxied FQDNs over HTTPS during report runs and adds a
"Cloudflare caching" warning notice to the site's report for any cache-configuration
problems it finds (missing or short `Cache-Control`, cookies on public content,
uncacheable `Cf-Cache-Status` values, and so on).  The check is **opt-in**: absent
config, nothing runs.

## When it runs

- Report paths only: a normal report run, or `--only-warn`.
- Never on `--update`, `--import-older-metrics`, or `--create-tables`.
- Per site, only FQDNs that are custom domains in the live environment, resolve in DNS,
  point at Cloudflare, and have a proxied record (the same classification the report
  already performs).  Sites with no such FQDNs are skipped silently.
- **If the site has a primary custom domain set**, only that FQDN is cache-checked and
  every other custom domain FQDN is skipped (visitors are redirected to the primary, so
  it is the one that matters).  If the primary domain is not itself behind Cloudflare,
  nothing is checked for that site.

## What is tested, per FQDN

1. The main page `https://{fqdn}/`.
2. Up to **3 same-FQDN pages** linked from the main page (auth/API paths like
   `/wp-admin`, `/login`, `/api/` are never probed).
3. For every page tested, up to **one JavaScript file, one CSS file, and one image**
   referenced by that page (same FQDN only).

Pages **and** assets whose path starts with `/cdn-cgi/` or `/.well-known/` are never
selected. `/cdn-cgi/` is Cloudflare's own prefix (challenge platform, email-address
obfuscation, Rocket Loader, the RUM beacon); `/.well-known/` is protocol/infrastructure
metadata (ACME challenges, `security.txt`, and the like). Neither is the website's own
content, so probing them says nothing about the site's caching.

URL selection is **deterministic per site per report date**: re-running the same report
tests the same URLs (so problems can be reproduced), and the selection rotates from
month to month.  Requests are sequential, send no cookies, use the configured
`user_agent`, and follow at most 5 same-FQDN redirects per URL; redirects to any other
FQDN (even apex↔www) drop that URL with a console note.

Each response's `Cf-Cache-Status`, `Cache-Control`, `Expires`, and `Set-Cookie` headers
are evaluated.  When a `Set-Cookie` is found, the cookie **names** (never their values)
are recorded on the console and in the report finding.  Cookies set by Cloudflare itself
(`__cf_bm`, `__cflb`, `cf_clearance`, `_cfuvid`, and the rest of the `CLOUDFLARE_COOKIES`
list in `check/cloudflare/headers.py`, matched case-insensitively) are ignored — they do
not affect origin caching — so a response whose only cookies are Cloudflare's produces no
cookie finding.  When a response is a cacheable `MISS`, it is re-requested up to twice
(2-second pauses) to distinguish "not cached *yet*" from "never caches"; only a
persistent `MISS` is reported.  No revalidate directive suppresses this retry —
neither `must-revalidate` nor `proxy-revalidate` prevents Cloudflare from caching,
so neither explains a `MISS`.  An invalid HTTPS certificate is reported and the
checks then continue against the response anyway.  A `cf-mitigated: challenge`
response is reported and ends that URL's checks.

Every finding prints to the console immediately (any verbosity).  At verbosity 0 progress
is shown ephemerally; `-v` prints plain step lines; `-vvv` additionally prints each
request, its final status code, and **all** response headers, for debugging.

## The egress-IP allowlist test

Cache results are only meaningful when the requests come from a network Cloudflare
treats normally (not challenged as an outsider).  So, once per report run — before the
site loop — the tool:

1. Discovers its own external IPv4 **and** IPv6 addresses via
   `https://1.1.1.1/cdn-cgi/trace` (and the IPv6 literal equivalent), falling back to
   `https://ip-check-perf.radar.cloudflare.com/` and then `https://ifconfig.me/ip`.
   A family with no connectivity at all is skipped with a console note; finding no
   address at all is fatal.
2. Fetches the Cloudflare list named `list_name` from account `account_id` and checks
   every discovered address against the list's IPs/CIDRs.  Any address not on the list
   is **fatal**, with a message naming the address and the list.

**The list must contain ranges for every IP family the host can egress on** — an
IPv6-capable runner with an IPv4-only list fails every report run.  Pass
`--allow-any-source-ip` to skip this test entirely (for example, when intentionally
testing from outside the institutional network).

## Configuration

```toml
[Cloudflare.cachecheck]
enabled = true
account_id = "..."       # REQUIRED: the Cloudflare account holding the allowlist
list_name = "..."        # REQUIRED: the list of allow-listed IPs/CIDRs
#user_agent = "pantheon-sitehealth-emails (Linux; UMich WWS 0.1) webmaster@umich.edu"
#timeout = 5             # per-request timeout, seconds
#report_doc_url = "..."  # the "Understanding your Cloudflare cache report" page
```

- `enabled` defaults to false.  When enabled, `account_id` and `list_name` are required
  (the run exits with a clear message if either is missing).
- All values must resolve in the **first** substitution pass (same rule as the
  `[Cloudflare]` credentials) — do not route them through deferring substitutions.
- The `[Cloudflare]` credentials additionally need the **Account Filter Lists: Read**
  scope for `account_id` (on top of the DNS:Read the plugin already needs).
- `user_agent` is sent on every request so site owners can identify this tool in their
  webserver logs.
- `report_doc_url` is the documentation page notices link to for fix instructions.  Do
  not enable the check in production until this URL resolves (the default points at a
  U-M page that must exist first), or notices will carry dead links.
- Python dependencies come from the `cloudflare` extra:
  `uv pip install .[cloudflare]` (pulls the `cloudflare` SDK, `httpx`, and
  `beautifulsoup4`).

## Result items (what a notice can contain)

| id | Meaning |
|---|---|
| `cf-status-missing` | No `Cf-Cache-Status` header — response may not be served via Cloudflare |
| `cf-status-uncacheable` | `Cf-Cache-Status` other than HIT/MISS/EXPIRED/STALE/REVALIDATED/UPDATING (e.g. DYNAMIC, BYPASS) |
| `no-cache-control` | No `Cache-Control` header |
| `no-max-age` | `Cache-Control` without a usable `max-age`/`s-maxage` |
| `short-cache-time` | Cache time under 3 days (1 year is recommended) |
| `cc-private` / `cc-no-cache` / `cc-no-store` | Directives that stop Cloudflare serving the visitor from its cache, so every request is passed through to the origin (slower, and each request can count toward the Pantheon visit limits). `no-cache` differs only in that Cloudflare may hold a copy but must check with the origin before serving it. |
| `cc-must-revalidate` | `must-revalidate` or `proxy-revalidate` on any page or asset (the directive seen is in `params["directive"]`). Neither prevents caching; both mean that once the content is stale and the origin is unreachable, visitors get an error instead of a stale copy. Suppressed whenever the content is not being served from Cloudflare's cache in the first place — either the header says so (`private`/`no-cache`/`no-store`) or Cloudflare does (a `Cf-Cache-Status` such as `DYNAMIC`/`BYPASS`) — since content that is never served from cache cannot go stale. |
| `expires-short` | Legacy `Expires` under 3 days with no usable `Cache-Control` cache time |
| `set-cookie` / `set-cookie-bypass` | Cookies set on public content (the `-bypass` form when the cookie is what made Cloudflare bypass its cache) |
| `miss-persistent` | Headers allow caching but the object never entered the cache across 3 attempts |
| `http-error` | Non-2xx response; caching could not be checked |
| `timeout` / `request-failed` / `invalid-cert` / `challenge` / `too-many-redirects` | Transport-level problems visitors may also experience |

Notices for FQDNs with identical findings (differing only in which URLs were tested)
are consolidated into a single notice.  All notices from this check use the CSV key
`cloudflare-cache`.  When the `[UMich]` plugin is enabled, notice language links U-M
documentation; otherwise a generic variant links public documentation (MDN, Cloudflare,
Pantheon) instead.
