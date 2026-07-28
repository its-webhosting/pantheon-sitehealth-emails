# `find-platform-domains-dns` — Specification

**Status:** approved design, ready for implementation
**Date:** 2026-07-28
**Prompt:** `development/2026-07-28-platform-domain-util/PROMPT.md`
**Plan:** `development/2026-07-28-platform-domain-util/PLAN.md`
**Lifetime:** temporary. Delete after Pantheon completes the Fastly → Pantheon-Cloudflare CDN
migration (expected later in 2026). See §14.

---

## Glossary

Terms of art, each used exactly once per concept throughout this spec. Three of these are
added to `CONTEXT.md` by this work (PD#11); the rest already exist there.

**Platform domain**
A Pantheon-provided hostname for one site environment, always ending in `.pantheonsite.io`
(e.g. `live-bus-occb.pantheonsite.io`). Pantheon's domain API labels these `type: platform`.
_Avoid_: Pantheon domain, pantheonsite name.

**Custom domain**
A hostname the site owner connected to a site environment, labelled `type: custom` by
Pantheon's domain API (e.g. `occb.bus.umich.edu`). Primary domains are custom domains and are
**in scope**.

**Environment**
One deployable instance of a site — `dev`, `test`, `live`, or a multidev (`test-mark`,
`autopilot`, …). Every environment has its own domain list.

**Chain**
The sequence of CNAME records followed from a custom domain until a non-CNAME answer, an
error, or the hop limit.

**Hit**
A chain in which some CNAME record's target is a platform domain. A hit produces one CSV row.

**`dns_record`**
The FQDN that *owns* the hitting CNAME record — i.e. the name whose CNAME target is the
platform domain. Equal to the custom domain in the common case; a mid-chain name otherwise.
This is the record the downstream rewriter must replace. See §6.3.

**Indeterminate**
A custom domain whose chain reached neither a hit nor a definitive no-hit (transient DNS
error, malformed name, chain loop, hop-limit overrun, or an upstream API failure that
prevented the domain from being examined at all). Indeterminates are reported on stderr,
counted, and drive the exit code. They are **never** silently dropped (PD#1).

**Sweep**
One execution of this utility over the requested sites.

**Legacy CDN**
Pantheon's outgoing Fastly-based CDN. A custom domain whose chain hits a platform domain is
still served through it; the migration replaces those CNAMEs with A/AAAA records.

## Requirement vocabulary

**MUST** — required; an implementation lacking it is incorrect.
**MUST NOT / NEVER** — prohibited; presence is a defect.
**SHOULD** — required unless a stated, reviewed reason applies.
**MAY** — optional; the choice is the implementer's.

---

## 1. Purpose

U-M ITS Web Hosting Services needs the exhaustive list of custom domains, across every site
and every environment in the Pantheon organization, whose public DNS still points at a
platform domain by CNAME. A second script — written by another team — consumes that list and
replaces each CNAME with the A/AAAA records the platform domain currently resolves to (there
are five distinct A/AAAA combinations). This utility produces the input to that script.

The expensive failure mode is a **missing row**: a domain omitted from the CSV is a domain
nobody migrates, and the CSV itself cannot reveal the omission. Every design decision below
that trades speed or brevity for completeness is made for that reason.

## 2. Scope

### 2.1 In scope

1. Every site in the organization, **including Sandbox-plan and frozen sites**. No plan
   filter, no `frozen` filter.
2. Every environment of every site, **including multidevs and uninitialized environments**.
3. Every **custom domain** of every environment, **including primary domains**.
4. Per custom domain: walk the chain; on a hit, write one CSV row to stdout.
5. Two zero-extra-API-call integrity checks on each hit, reported on stderr (§7).

### 2.2 NOT in scope — with the reasoning, so a later session does not re-litigate

| Excluded | Why |
|---|---|
| Apex / A-record legacy domains (a domain pointed straight at `23.185.0.4` / `2620:12a:8000::4` with no CNAME anywhere) | User decision, 2026-07-28: the downstream rewriter replaces CNAMEs only, so a domain with no CNAME is not actionable by it. Consequence accepted: such domains are absent from the CSV. |
| Custom domains fronted by U-M Cloudflare | Another team owns them (PROMPT.md). No code is needed either way: a proxied domain resolves to Cloudflare A/AAAA records with no CNAME visible in public DNS, so the chain reaches a definitive no-hit on its own. |
| Skipping the domains call for `initialized: false` environments | Measured saving is 8.9% of API calls (~2 min of a ~21 min sweep) and its safety rests on a 25-site sample, not a documented Pantheon guarantee. A wrong assumption produces a missing row — the one failure the output cannot reveal (PD#14). |
| A per-run DNS memo cache | API calls (~2,060 × 0.61 s measured) dominate the runtime; duplicate CNAME targets across custom domains are rare in this data. Not worth the extra state in the walk. |
| Resumability / checkpointing | A whole re-run is ~21 minutes; `--resume-from` machinery (PD#7) is not worth it at that cost. Re-running is the recovery procedure. |
| Parallelism | PROMPT.md: no significant work on speed. Sequential keeps the failure taxonomy (§7) trivially attributable. |
| Recorded API fixtures / e2e tier | The script is deleted within months; hand-maintained fixtures would rot first. §10 covers the logic offline with injected fakes. |
| Importing from `psh/` | PROMPT.md: copy, do not modularize, so deletion is a `git rm` of three paths. |
| A `docs/` usage page | The script's module docstring plus §3 here is the documentation. A doc page for a doomed script is inventory, not value. |

## 3. CLI contract

```
find-platform-domains-dns [-h] [-c CONFIG] [-v] [SITE ...]
```

| Flag | Default | Meaning |
|---|---|---|
| `SITE ...` | none = whole organization | Pantheon site names to sweep. Each is resolved with `GET /v0/site-names/{name}`, so a targeted run does **not** page the organization list. |
| `-c`, `--config` | `pantheon-sitehealth-emails.toml` | TOML file read **only** for `[Pantheon].org_id`. Parsed with `tomllib`; the config-substitution engine is NOT used (that value is a literal). |
| `-v`, `--verbose` | off | Per-site progress to stderr. ATTENTION lines and the summary are printed regardless. |

The parser MUST set `allow_abbrev=False`, matching the main tool's house rule.

**Machine token resolution**, in order: `$PANTHEON_MACHINE_TOKEN` if set and non-empty;
otherwise the single JSON file in `~/.terminus/cache/tokens/`, whose `token` key is used. Zero
files, more than one file, an unreadable file, or a missing `token` key is **fatal** (exit 2)
with a message naming what was found — never a guess (PD#1).

> **PD#6 tension, stated rather than buried.** The main program NEVER reads credentials from
> the environment; everything flows through `<{secret env …}>` config substitution. This script
> reads one credential from the environment and one from the Terminus token cache. Justification:
> it is standalone, has no substitution engine, and adding a secret key to the shared production
> TOML for a script that is deleted within months is the worse outcome. The token is never
> logged, never echoed, and never written to stdout.

## 4. Data sources

All Pantheon data comes from the Pantheon API (CLAUDE.md's stated preference for new code), not
Terminus. Every row below was verified live on 2026-07-28 against the real organization.

| Call | Purpose | Verified shape / behavior |
|---|---|---|
| `POST /v0/authorize/machine-token` body `{"machine_token": …, "client": "find-platform-domains-dns"}` | session token | returns `{"session": "…"}` |
| `GET /v0/organizations/{org_id}/memberships/sites?limit=100&start={last_site_id}` | site list | `limit` max 100; `start` is a site UUID, exclusive. **Read §4.1 before implementing — the cursor has a silent failure mode.** Each element: `{"id": <membership id, equal to site.id for all 408>, "site": {"id", "name", "plan_name", "framework", "frozen", …}}` |
| `GET /v0/site-names/{site_name}` | name → id for `SITE` args | `{"id": "…"}` |
| `GET /v0/sites/{site_id}/environments` | environment list | object keyed by environment id; includes multidevs (`autopilot`, `test-mark`, …); each value carries `initialized`, `php_version`, … |
| `GET /v0/sites/{site_id}/environments/{env_id}/domains` | domain list | array of `{"id", "type": "platform"\|"custom", "primary", "status", …}`. An uninitialized environment returns its platform domain only. |

The swagger (`https://api.pantheon.io/docs/swagger.json`) documents **no 429 / rate-limit
response**; the retry policy in §7 nonetheless treats 429 like a 5xx, because an undocumented
limit is not the same as no limit.

### 4.1 The pagination cursor's silent failure mode — READ THIS

Measured 2026-07-28 and written up in full, with a standalone reproduction script, in
`pantheon-api-pagination-bug-report.txt` and `reproduce-pagination-bug.sh` **in this
directory** — that report is the authority for this section; re-run the script before
trusting any of it a second time.

**The cursor is honored only when the supplied id is the last element of a page the API has
already computed for that organization.** For any other site id, the API returns **the first
page again**, with HTTP 200 and no error, warning, or header. The failure is not random: a
positional scan of the 408-site organization (`limit=100`) found `start` honored at positions
100, 200, 300, 400 and 408 — every page boundary — and ignored at positions 1, 2, 50, 99, 101,
102, 150, 199, 201, 250, 299, 301, 350, 399, 401, 405 and 407. The apparent flakiness in
earlier notes was self-inflicted: an earlier `limit=50` request created a boundary at position
50, after which that cursor stayed valid, including for later `limit=100` requests.

Three consequences are load-bearing:

1. **The walk pattern is the only correct usage**, and it is structurally safe: passing the
   last id of the page you just received always passes a boundary. Measured over **10+
   consecutive full walks**, every one returning 408 unique ids identical to
   `terminus org:site:list`'s 408, with zero resets.
2. **"Loop until an empty page" is wrong**, though not for the reason first recorded here. The
   final boundary cursor *does* return `[]` (CASE D of the report, 7/7) — but an *unrecognized*
   cursor returns a full first page rather than `[]`, so a loop with that stop condition never
   terminates once it goes off the boundary. Stop on a **short page** instead.
3. **A silently ignored cursor is indistinguishable from a complete listing.** Without
   detection, the loop either spins or (with a naive dedupe) returns 100 of 408 sites, and the
   CSV cannot reveal the loss.

The implementation MUST therefore (G4a/G4b, §7):

- request `limit=100` and use the previous full page's last **`site.id`** as `start` — the
  swagger says the cursor is a site UUID; the element's top-level membership `id` is equal to
  `site.id` for all 408 sites today, but that equality is an observation, not a contract;
- keep a `seen` set of site ids and dedupe against it;
- treat a **non-empty** page that contributes **zero new ids** as a cursor reset: sleep
  `RETRY_SLEEP` and retry the **same** cursor, up to 3 attempts, then **exit 2** with a named
  error. The non-empty qualifier is load-bearing — without it, the legitimate final empty page
  of an exact-multiple-of-100 organization is misread as a fault and aborts a good sweep;
- stop when a page returns fewer than 100 items — including **zero** items, which is exactly
  what an organization holding an exact multiple of 100 sites produces on its final request;
- cap the loop at 100 pages (10,000 sites) as a runaway guard, exiting 2 if exceeded.

If G4a ever fires in production, one documented recovery was observed but **not adopted**,
because it rests on a single observation: re-issuing the *uncursored* first-page request
appeared to re-establish a previously-ignored cursor's validity. Prefer switching the site list
to `terminus org:site:list` (one call, all 408, no cursor) over building on that inference —
see §15 question 4.

**Transport.** One `httpx.Client` for the whole sweep, so ~2,000 requests share one TLS
connection. `httpx` is already a direct dependency of this project (declared under the
`cloudflare` extra, which the documented setup line installs). The script MUST state that
dependency in its module docstring.

## 5. Output contract

Exactly one CSV row per hit, on **stdout**, five fields, **no header row**, `\n` line
terminator (`csv.writer` defaults to `\r\n` — it MUST be set explicitly), flushed after every
row so a long sweep can be watched with `tail -f`:

```
site_name,site_env,custom_domain,dns_record,platform_domain
```

| Field | Value |
|---|---|
| `site_name` | Pantheon site name, e.g. `bus-occb` |
| `site_env` | environment id, e.g. `live`, `test-mark` |
| `custom_domain` | the connected custom domain, normalized (lowercase, no trailing dot) |
| `dns_record` | FQDN owning the hitting CNAME record (§6.3) |
| `platform_domain` | the CNAME target ending in `.pantheonsite.io` |

Example, direct hit (verified live: `occb.bus.umich.edu` CNAMEs straight to the platform
domain):

```
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io
```

Example, mid-chain hit (`www.example.umich.edu → alias.umich.edu → live-y.pantheonsite.io`):

```
some-site,live,www.example.umich.edu,alias.umich.edu,live-y.pantheonsite.io
```

**NEVER** write anything but CSV rows to stdout. Progress, ATTENTION lines, and the summary go
to stderr, so `find-platform-domains-dns > domains.csv` yields a clean file.

## 6. Algorithm

### 6.1 Sweep flow

```
 pantheon-sitehealth-emails.toml ──[Pantheon].org_id──┐
 $PANTHEON_MACHINE_TOKEN or                           │
 ~/.terminus/cache/tokens/<user> ──machine token──┐   │
                                                  v   v
                        POST /v0/authorize/machine-token  →  session token
                                                  │
        ┌─────────────────────────────────────────┘
        │  SITE args?  ── yes ──→ GET /site-names/{name}  (one call per site)
        │              ── no  ──→ GET /organizations/{org}/memberships/sites
        v                          ?limit=100&start=<last id of previous FULL page>
        │                          stop on a short page; a page with zero new ids is a
        │                          silently-ignored cursor → retry, then exit 2 (§4.1)
   for each site  (sandbox + frozen included, no filter)
        │
        v
   GET /sites/{id}/environments            → every env, multidev and uninitialized included
        │
        v   for each environment
   GET /sites/{id}/environments/{env}/domains
        │      ├── type == "platform" → collect into this environment's platform-domain set
        │      └── type == "custom"   → examine (primary domains included)
        v
   walk the chain (§6.2)
        │
        ├── no hit ─────────→ nothing
        ├── indeterminate ──→ ATTENTION on stderr, counter += 1, no row
        └── hit ────────────→ two integrity checks (§7), then one CSV row on stdout
```

### 6.2 Chain walk

Copied from `check/pantheon_cdn_change/chain.py` and adapted (§6.3). `MAX_CNAME_DEPTH = 8`.

```
  name := normalize(custom_domain)

  name ends .pantheonsite.io?  ── yes ──→ INDETERMINATE
        │ no                                ("custom domain is itself a platform domain":
        v                                     there is no CNAME record to replace)
  ┌─→ name already seen? ── yes ──→ INDETERMINATE (chain loops)
  │         │ no
  │         v
  │   resolve(name, "CNAME")
  │         │
  │         ├── NoAnswer / NXDOMAIN ─────────────→ NO HIT (definitive: chain ends here)
  │         ├── Timeout / NoNameservers ─────────→ INDETERMINATE (transient)
  │         ├── MalformedNameError ──────────────→ INDETERMINATE (not a valid DNS name)
  │         └── target t:
  │               t ends .pantheonsite.io? ─ yes ─→ HIT(dns_record = name, platform_domain = t)
  │                     │ no
  └──── name := t ──────┘   (after 8 hops without a definitive answer → INDETERMINATE)
```

A transient resolver failure is retried **once** immediately, with no sleep — dnspython has
already spent its own 5-second lifetime on the query, so an added delay buys nothing.

### 6.3 Why the walk differs from `chain.py`

`chain.py` tests the *current name* at the top of each hop, because its caller starts from a
Cloudflare origin string that may already be a platform domain. This utility must report the
**owner of the hitting record** (`dns_record`), so the platform-domain test moves to the
*resolved target*, and the hit carries the name that was resolved. The degenerate case
`chain.py` handles at the top — the start is itself a platform domain — becomes an
indeterminate here, because there is no CNAME record to rewrite.

The unchanged copies are `normalize()` and the exception handling; `is_legacy_gcdn()` is
renamed `is_platform_domain()` to match this spec's glossary. `resolve()` and
`MalformedNameError` are copied verbatim from `psh/dns_classify.py`, including the
`struct.error` reasoning (a garbled wire response MUST surface as transient, never as a
malformed name).

## 7. Gates, failure taxonomy, exit codes

One canonical table. Every row is a decision the implementation makes; nothing else may
produce output.

| # | Condition | Retry | Operator sees (stderr) | CSV row | Counted indeterminate | Run continues |
|---|---|---|---|---|---|---|
| G1 | Config file missing / unparseable / no `[Pantheon].org_id` | — | fatal message | — | — | no, **exit 2** |
| G2 | Machine token unresolvable (0 or >1 cache files, unreadable, no `token` key) | — | fatal message naming what was found | — | — | no, **exit 2** |
| G3 | `POST /authorize/machine-token` fails | — | fatal message | — | — | no, **exit 2** |
| G4 | Organization site listing fails, or a `SITE` arg's name lookup fails | 1 (per §7.1) | fatal message | — | — | no, **exit 2** |
| G4a | A **non-empty** site-list page contributes zero new ids (the cursor was silently ignored, §4.1). An **empty** page is not this condition — it is a legitimate end of collection | 3 attempts of the same cursor, `RETRY_SLEEP` apart | `ATTENTION: site listing cursor was ignored …` per attempt, then a fatal message | — | — | no, **exit 2** after the third |
| G4b | The site-list loop exceeds 100 pages | — | fatal message | — | — | no, **exit 2** |
| G5 | `environments` call fails for a site | 1 | `ATTENTION: <site>: could not list environments: <reason>` | no | **yes** (once for the site) | yes, next site |
| G6 | `domains` call fails for an environment | 1 | `ATTENTION: <site>.<env>: could not list domains: <reason>` | no | **yes** (once for the env) | yes, next env |
| G7 | HTTP 401 mid-sweep (session expiry) | re-authenticate once, then retry the request | `-v` note only | — | no | yes |
| G8 | DNS `Timeout` / `NoNameservers` | 1 | `ATTENTION: <site>.<env> <domain>: transient DNS error at <name>: <Type>` | no | **yes** | yes |
| G9 | Malformed DNS name | — | `ATTENTION: … not a valid DNS name: <detail>` | no | **yes** | yes |
| G10 | Chain loops, or exceeds 8 hops | — | `ATTENTION: … CNAME chain loops at <name>` / `… exceeds 8 hops` | no | **yes** | yes |
| G11 | Custom domain is itself a platform domain | — | `ATTENTION: … is itself a platform domain; no CNAME record to replace` | no | **yes** | yes |
| G12 | Hit whose `platform_domain` resolves to no address (definitively) | — | `ATTENTION: … platform domain <t> does not resolve; the downstream rewrite has no addresses to use` | **yes** | no | yes |
| G13 | Hit whose `platform_domain` is not one of this environment's own platform domains | — | `ATTENTION: … points at <t>, which belongs to a different site/environment (expected one of: …)` | **yes** | no | yes |
| G14 | Hit, clean | — | nothing | **yes** | no | yes |

**Exit codes.** `0` = sweep completed with zero indeterminates. `1` = sweep completed with ≥1
indeterminate. `2` = the sweep could not be completed (G1–G4, or `argparse` usage error).
Rationale: a cron wrapper or a human MUST be able to tell a complete sweep from a partial one
without reading stderr (PD#1).

**G12 detail.** The check resolves `platform_domain` for `A`, then `AAAA`. A definitive empty
answer for both (`NoAnswer`/`NXDOMAIN`) means dead. Any transient or malformed outcome is
treated as **alive** — the check MUST NOT cry wolf on a blip, since its only job is to warn.

**G13 detail.** The environment's own platform domains are the `type: platform` entries from
the *same* `domains` response already fetched — the check costs zero extra API calls. The
comparison is against the **set** of them, not a single value.

### 7.1 Retry policy for API calls

`ApiSession.get()` retries **once**, after a 2-second sleep, on: an `httpx.HTTPError`
(timeout, connection failure, protocol error), HTTP `>= 500`, or HTTP `429`. It
re-authenticates **once** on HTTP `401` and retries the request immediately (a re-auth does
not consume the transport retry). Any other non-200, a second failure, or an undecodable JSON
body raises the named `PantheonApiError`, which the caller turns into G4/G5/G6.

### 7.2 Shadow paths (PD#3), traced

| Flow | Nil input | Empty input | Upstream error |
|---|---|---|---|
| Site listing | organization with no sites → first page is `[]` → sweep 0 sites, summary all zeros, exit 0 | two empty-ish shapes, both legitimate and both terminating on the "fewer than 100" rule: a short page (the common case, 8 of 408) and a genuinely **empty** page, which is what an organization holding an exact multiple of 100 sites returns for its final boundary cursor (§4.1). The empty page MUST NOT trip the G4a detector — that detector fires only on a **non-empty** page contributing no new ids | G4 / G4a / G4b |
| Environment listing | site with `{}` environments → 0 envs swept, site counted | — | G5 |
| Domain listing | environment with `[]` domains → nothing examined | environment with platform domain only → 0 custom domains | G6 |
| Chain walk | `NoAnswer` for the first hop → no hit | — | G8/G9/G10 |
| Hit checks | platform-domain set empty (no `type: platform` entry) → G13 fires with an empty "expected" list, which is itself worth seeing | — | G12 treats transient as alive |

## 8. Observability (PD#5)

- **stdout**: CSV rows only.
- **stderr, always**: `ATTENTION: …` lines per §7, and a final summary line:
  `sites=N envs=N custom_domains=N rows=N indeterminate=N`.
- **stderr, `-v` only**: one progress line per site (`[12/408] bus-occb`), the environment and
  custom-domain counts per site, and the session re-authentication note (G7).
- **NEVER `rich`.** Plain `print(…, file=sys.stderr)`. The main program's console has two
  documented traps — markup silently deleting `[bracketed]` fragments (exactly the shape of DNS
  and API error text) and an 80-column hard wrap on a non-tty. Not importing `rich` removes
  both by construction rather than by discipline.

## 9. Seams under test — named and agreed

Per the Spine's spec bar, these are fixed here, before implementation, because the implementer
works test-first and cannot ask.

| Seam | Form | Used by |
|---|---|---|
| `resolve(name, rrtype)` | module-level function, monkeypatched exactly as `psh.dns_classify.resolve` is today; `tests/helpers/dnsfake.make_resolver` builds the fake | every DNS test |
| `get` callable | **injected**, not patched: `org_sites(get, org_id)`, `Sweeper(get=…)` etc. take the getter as a parameter. Production passes `ApiSession.get`; tests pass a dict-driven fake | every enumeration and sweep test |
| `httpx.MockTransport` | passed into `ApiSession`'s client at construction | the retry / re-auth / JSON-error tests, and only those |
| `RETRY_SLEEP` | module-level constant, monkeypatched to `0` | the retry tests (so the suite never actually sleeps) |

No other seam is created. In particular there is **no** patching of `time.sleep` or of
`httpx.Client` itself.

## 10. Test plan

One file: `tests/unit/test_find_platform_domains_dns.py`, marked `pytest.mark.unit`, fully
offline, collected by `./run-tests --fast`. The script is loaded with the
`SourceFileLoader` + `spec_from_loader` + `module_from_spec` idiom already used by
`tests/integration/test_plugin_aws.py`, against the extension-less file, in a function-scoped
fixture. The script MUST therefore guard its entry point with `if __name__ == "__main__":`.

Required coverage — each item is a behavior a defect could silently break:

1. `normalize` / `is_platform_domain`, including that a name merely *containing*
   `pantheonsite.io` (`pantheonsite.io.evil.example`) is **not** a platform domain.
2. Walk: direct hit; mid-chain hit (asserting `dns_record` is the mid-chain name, not the
   custom domain); no hit via `NoAnswer`; no hit via `NXDOMAIN`; transient; malformed name;
   loop; hop-limit overrun; custom domain that is itself a platform domain.
3. Pagination: three pages (100/100/8) yielding 208 unique sites; a zero-site organization;
   **an organization whose site count is an exact multiple of 100** — a full page followed by
   an empty one, which §4.1 confirms is what the API really returns for the final boundary
   cursor, and which must terminate normally rather than trip the reset detector;
   **the ignored-cursor case (§4.1)** — a fake `get` that returns page 1 again for a cursor
   must produce a retry and then a named error, NEVER an infinite loop and NEVER a silently
   short list; and the 100-page runaway cap. **PD#14: the multi-page test MUST be shown going
   red against a single-call implementation**, and the ignored-cursor test MUST be shown going
   red against a loop that lacks the detector — they are the only guards against a silent
   truncation to the first 100 of 408 sites.
4. Domain partitioning: a mixed list yields only the custom domains, and the platform set is
   every `type: platform` entry.
5. `ApiSession`: 401 → re-authenticate once → success; 500 → one retry → success; 500 twice →
   `PantheonApiError`; `httpx.ConnectError` → one retry; undecodable body → `PantheonApiError`.
6. Hit handling: clean hit writes exactly the five expected fields in order; G12 dead target
   still writes the row and emits ATTENTION; G13 cross-site target still writes the row and
   emits ATTENTION; G12 with a transient lookup does **not** emit ATTENTION.
7. Counters and exit codes: a sweep with one indeterminate returns 1; a clean sweep returns 0;
   G5 counts the site once and continues to the next site.
8. CSV mechanics: the writer emits `\n`, not `\r\n`.

**Tests are load-bearing.** NEVER weaken an assertion, delete a case, or relax a fake to make
a test pass. A red test here is a finding about the code.

## 11. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | Pantheon API, not Terminus | Measured: `env:list` 7.4 s and `domain:list` 2.0–2.9 s per Terminus call, vs **0.61 s** per API call over a reused `httpx` connection (24 sequential calls timed); 408 sites × ~5.04 calls is ~2 h vs ~21 min. CLAUDE.md prefers the API for new code. |
| D2 | Self-contained script, code copied not imported | PROMPT.md. Deletion is `git rm` of three paths plus two `pyproject.toml` lines. |
| D3 | Committed `find-platform-domains-dns.py` symlink | ruff, pyright, CodeGraph, and importers all key off the `.py` extension; verified 2026-07-28 that ruff 0.15.22 traverses into symlinked `.py` files and pyright 1.1.411 analyzes them. Same convention as `pantheon-sitehealth-emails.py`. |
| D4 | stderr + counted + non-zero exit for indeterminates | User decision. Keeps stdout a clean CSV while making incompleteness impossible to miss. |
| D5 | `dns_record` column | User requirement: the downstream rewriter must edit the record that actually holds the CNAME, which is not always the custom domain. |
| D6 | G13 cross-site check, row still emitted | User decision. The record must go regardless; a cross-site target is a review item, not a disqualifier. |
| D7 | G12 dead-target check, row still emitted | User decision. Turns a downstream crash into a pre-flight warning. |
| D8 | No `rich` | §8. |
| D9 | Machine token from env or Terminus cache | §3, with the PD#6 tension stated. |
| D10 | Every environment queried, uninitialized included | §2.2. |
| D11 | Site list stays on the API, with the G4a reset detector rather than switching to `terminus org:site:list` | User decision after the §4.1 finding was presented. The characterization has since sharpened (§4.1): the walk pattern is *structurally* safe, because it only ever passes page boundaries, and it measured 0 resets across 10+ full walks. The detector is kept anyway — it costs a `seen` set the loop needs regardless, and it converts the residual silent-truncation risk into a loud exit 2. §15 question 4 revisits it with production evidence. |

## 12. Verified facts

Everything load-bearing here was confirmed against the authority on 2026-07-28, not assumed.

| Claim | How it was verified |
|---|---|
| API pagination is `limit`≤100 + exclusive `start` cursor | swagger `GetOrganizationSiteMemberships` |
| The walk pattern (cursor = last id of the previous full page) is reliable | 10+ consecutive live full walks, 0 resets, 408 unique ids each, identical to `terminus org:site:list`'s 408 |
| The cursor is honored **only** at a page boundary; every other id silently returns page 1 with HTTP 200 (§4.1) | live positional scan, `limit=100`: honored at positions 100/200/300/400/408, ignored at 1/2/50/99/101/102/150/199/201/250/299/301/350/399/401/405/407. Reproduced 5/5 and 2/2 for positions 1 and 101 by `reproduce-pagination-bug.sh` |
| The final boundary cursor returns `[]` — so an exact-multiple-of-100 organization really does end on an empty page | live: `start` = the maximum site id → empty array, 7/7 across two script runs |
| An *unrecognized* cursor returns a full first page, never `[]` — which is why "loop until empty" cannot be the stop condition | the same positional scan: every ignored position returned `n=100` |
| The collection is ordered ascending by site id and stable across calls | live: every full walk's ids sorted identically; `sort -u` count equals the collected count |
| Membership id equals site id for all 408 sites (so either works as a cursor today; the swagger specifies the **site** UUID) | live: full walk comparing `.id` against `.site.id`, 0 differences |
| Nothing in these tests ever returned a 4xx or 5xx | every probe and walk recorded HTTP 200, including the failing ones. **Consequence:** the §7.1 retry policy's 5xx/429 paths have never been exercised against the real API — they are covered only by `httpx.MockTransport` in §10, item 5 |
| A Pantheon API call costs **0.61 s** over a reused `httpx` connection | live: 24 sequential calls on one client, 14.64 s total. (The ~1.3 s figures from the `curl` probes include a fresh TLS handshake per call and are not representative of the script.) So 408 sites × ~5.04 calls ≈ 2,060 calls ≈ 21 minutes, plus the per-custom-domain DNS walks |
| A site has ~4.0 environments on average | live: 25-site sample, 101 environments. (`its-wws-test1` has 7, which is atypical — do not extrapolate the runtime from it) |
| `/environments` includes multidevs | live: `its-wws-test1` → `autopilot, dev, live, test, test-jpr, test-mark, test-md` |
| Domain entries carry `type: platform\|custom` | live: `its-wws-test1.live` → 1 platform + 2 custom |
| An uninitialized environment exposes only its platform domain | live: `vpao-accopp.live` (`initialized: false`) |
| Uninitialized environments are ~8.9% of environments and held no custom domains in a 25-site sample | live sample: 25 sites, 101 envs, 9 uninitialized, 0 with custom domains |
| A legacy-CDN domain's chain hits the platform domain at hop 1 | live: `occb.bus.umich.edu` → `live-bus-occb.pantheonsite.io` → `fe4.edge.pantheon.io` → `23.185.0.4` |
| A migrated domain's chain does **not** contain a platform domain | live: `wws-test1.cdn-dev.it.umich.edu` → `fe.cfp2c.edge.pantheon.io` → `185.178.196.3` |
| The swagger documents no 429 response | `grep -c 429 swagger.json` → 0 |
| ruff lints files reached through a `.py` symlink | probe repo: a symlinked `probe.py` was reported by `ruff check .` |
| pyright analyzes a `.py` symlink | `uvx pyright@1.1.411 pantheon-sitehealth-emails.py` → 1 file analyzed |

## 13. Acceptance criteria

Exact commands. The implementer MUST run each and paste the real output into
`development/2026-07-28-platform-domain-util/ACCEPTANCE.md` — a summarized or predicted result
is PD#14 exactly.

```bash
# 1. Full gate: ruff (select = ALL) + pyright + the offline suite
./run-tests --fast

# 2. The new test file alone, verbose
./run-tests tests/unit/test_find_platform_domains_dns.py -v

# 3. Help text
./find-platform-domains-dns --help

# 4. A known-migrated site: expect ZERO CSV rows on stdout and exit 0
./find-platform-domains-dns its-wws-test1; echo "exit=$?"

# 5. A known-legacy site: expect the bus-occb row on stdout
./find-platform-domains-dns bus-occb; echo "exit=$?"

# 6. Clean-file behavior: stdout redirects to a file containing only CSV
./find-platform-domains-dns its-wws-test1 bus-occb > /tmp/pd.csv 2>/tmp/pd.err
echo "exit=$?"; cat /tmp/pd.csv; cat /tmp/pd.err

# 7. Fatal path: a config with no [Pantheon].org_id exits 2 with a named message
./find-platform-domains-dns -c /dev/null; echo "exit=$?"
```

A full-organization sweep is NOT an acceptance step: it takes ~21 minutes and its output is
operational data, not evidence of correctness. Run it when you actually want the list.

## 14. Deletion checklist (post-migration)

1. `git rm find-platform-domains-dns find-platform-domains-dns.py tests/unit/test_find_platform_domains_dns.py`
2. Remove the `find-platform-domains-dns.py` entries from `[tool.ruff.lint.per-file-ignores]`
   and `[tool.pyright].include` in `pyproject.toml`.
3. Remove the CLAUDE.md paragraph describing the utility.
4. Leave `CONTEXT.md`'s glossary additions in place — those terms describe Pantheon, not this
   script.
5. Leave `pantheon-api-pagination-bug-report.txt` and `reproduce-pagination-bug.sh` in this
   directory. They document a defect in **Pantheon's API**, not in this utility, and stay
   useful (and re-runnable) for as long as that endpoint is paginated — including for whoever
   next writes a paginated consumer here.

## 15. Closing audit questions (answer after implementation)

1. On the first full-organization sweep: how many rows, and how many indeterminates? If
   indeterminates are more than a handful, is the cause a systematic one (a resolver limit, an
   API pattern) rather than genuinely broken domains?
2. Did G13 (cross-site targets) fire at all? If it did, were those rows safe to hand to the
   downstream rewriter?
3. Did any custom domain turn out to be attached to an `initialized: false` environment,
   contradicting the 25-site sample in §2.2?
4. Did the G4a ignored-cursor detector fire during a real full sweep? §4.1 says it should not
   be able to — the walk only ever passes page boundaries — so if it fires, the boundary model
   in the bug report is incomplete. In that case move the site list to `terminus org:site:list`
   (one call, no cursor) rather than tuning the retry, and re-run
   `reproduce-pagination-bug.sh` to see whether Pantheon's behavior has changed.
5. Did the pagination loop ever see a page that was neither 100 nor final — i.e. does the API
   ever return a short non-final page, which would break the stop condition?
