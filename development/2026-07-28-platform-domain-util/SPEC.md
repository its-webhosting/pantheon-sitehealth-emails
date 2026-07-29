# `find-platform-domains-dns` — Specification

**Status:** approved design, ready for implementation
**Date:** 2026-07-28
**Prompt:** `development/2026-07-28-platform-domain-util/PROMPT.md`
**Plan:** `development/2026-07-28-platform-domain-util/PLAN.md`
**Lifetime:** temporary. Delete after Pantheon completes the Fastly → Pantheon-Cloudflare CDN
migration (expected later in 2026). See §14.

---

## Glossary

Terms of art, each used exactly once per concept throughout this spec. **Platform domain**,
**Custom domain** and **Environment** are added to `CONTEXT.md` by this work (PD#11) because
they describe Pantheon and outlive this utility. The remaining six — Chain, Hit, `dns_record`,
Indeterminate, Sweep, Legacy CDN — are **spec-local** and deliberately stay out of the domain
glossary: they describe this script's internals, and `CONTEXT.md` is a domain glossary and
nothing else (`docs/agents/domain.md` states that split).

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
One execution of this utility over the requested sites. Kept distinct from `CONTEXT.md`'s
**Run** ("one execution of the tool over one or more sites for a given report date"), which
carries a report date and a dry-run/for-real duality this utility has neither of. Where this
spec says "run" in prose it means the same thing as sweep; the tables use "sweep".

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
| Skipping the domains call for `initialized: false` environments | Measured saving is ~9% of **environments**, hence ~7% of API calls (~3 min of a ~38 min sweep) and its safety rests on a 25-site sample, not a documented Pantheon guarantee. A wrong assumption produces a missing row — the one failure the output cannot reveal (PD#14). |
| A per-run DNS memo cache | API calls (~2,030 × ~1.1 s measured, §12) dominate the runtime; duplicate CNAME targets across custom domains are rare in this data. Not worth the extra state in the walk. |
| Resumability / checkpointing (`--resume-from`, a state file) | A whole re-run is ~38 minutes (§12) — longer than the ~21 first recorded here, which is why this was re-decided rather than assumed. Still not worth the machinery for a script due for deletion: the sweep is read-only, its stdout is streamed so a partial sweep's rows are already valid, and **§7.3 requires an aborted sweep to print the last site processed and the names of every site not yet reached** (amended, fix round 2 of task 5, N8: this row previously said only "the number remaining"), so an operator can resume by passing those names as `SITE` arguments. That line is the whole recovery story (PD#7). |
| Parallelism | PROMPT.md: no significant work on speed. Sequential keeps the failure taxonomy (§7) trivially attributable. |
| Recorded API fixtures / e2e tier | The script is deleted within months; hand-maintained fixtures would rot first. §10 covers the logic offline with injected fakes. |
| Importing from `psh/` | PROMPT.md: copy, do not modularize, so deletion is a `git rm` of three paths. |
| A `docs/` usage page | The script's module docstring plus §3 here is the documentation. A doc page for a doomed script is inventory, not value. |
| Percent-encoding the API-sourced path and query segments. **This list is exhaustive: there are three, not one** (corrected, residual review finding 4 — the row named only the last of them and thereby under-stated its own scope, which PD#9 forbids: "Everything deferred is written down. Vague intentions are lies."). They are, by call site in `find-platform-domains-dns`: (1) the pagination cursor, `path += f"&start={cursor}"` in `org_sites()` — a site id taken from the previous page's `site.id`; (2) `f"/sites/{site_id}/environments"` in `site_environments()`; and (3) `f"/sites/{site['id']}/environments/{env_id}/domains"` in `Sweeper.sweep_env()` | **Accepted residual, still open — nothing in this spec or the code claims it is closed** (whole-branch review m10). Unlike `org_id` (config, operator-typo-controlled, quoted since task 3's fix round) and the `SITE` argv (§3), all three come from the API's own responses, and a value that produces an invalid URL now raises `httpx.InvalidURL` — folded into `ApiSession.get`'s handler in task 5 — so it surfaces as the named `PantheonApiError`, i.e. G4/G5/G6, not as an exit-1 traceback. (1) is the weakest of the three, and is named separately for that reason: it lands in a *query string*, where an `&` or `#` in a cursor would silently change the query rather than raise, so `httpx.InvalidURL` does not backstop it — what does is §4.1's G4a detector, which exits 2 on a page contributing no new ids. There is deliberately **no test** for any of the three: constructing an API response whose ids break a URL would pin a shape Pantheon does not produce. |
| A G0 check ahead of `argparse` | **Accepted residual.** The closed-stream guard (G0) runs immediately after `parse_args`, so a run that is BOTH invoked with a closed stderr AND has a command-line typo gets argparse's own fallback: the usage message goes to stdout and the process exits 2 (verified live). That is loud, in the §7 taxonomy, and writes no CSV. Moving the check earlier costs `main()` a seventh `return` (ruff `PLR0911`) or a possibly-unbound `options` under pyright, neither of which is worth it for a typo-plus-closed-stderr combination. |

## 3. CLI contract

```
find-platform-domains-dns [-h] [-c CONFIG] [-v] [SITE ...]
```

| Flag | Default | Meaning |
|---|---|---|
| `SITE ...` | none = whole organization | Pantheon site names to sweep. Each is resolved with `GET /v0/site-names/{name}`, so a targeted sweep does **not** page the organization list. The name MUST be `urllib.parse.quote(name, safe="")`-encoded into the path — an argument containing `#`, `?` or `%` would otherwise silently change which resource is requested rather than failing — and the `site_name` written to the CSV MUST be the **canonical name from the response** (`{"id": …, "name": …}`, verified live), read with the same `_require_str` guard as `id` — a silent fallback to the argv string would reintroduce exactly the mismatch this rule exists to prevent — not the argv string, so that a differently-cased argument cannot produce CSV rows the downstream script fails to match. `_require_str`, not `_require` (amended, whole-branch review m6): presence alone let a non-str `name` reach the `shlex.join(…)` that §7.3's resume line is built with, as an unnamed `TypeError: expected string or bytes-like object, got 'list'`, i.e. an exit-1 traceback raised *while reporting an abort*. (Citation refreshed, residual review finding 3: the m2 fix replaced that call's earlier `" ".join(…)` spelling with `shlex.join`; the hazard is unchanged and verified, so the guard stays.) |
| `-c`, `--config` | `pantheon-sitehealth-emails.toml` | TOML file read **only** for `[Pantheon].org_id`, and **only on the whole-organization path** (amended, whole-branch review m1): a `SITE`-argument sweep never uses `org_id`, so reading the config there made `find-platform-domains-dns bus-occb` fail exit 2 from any directory lacking the default config — a gate on a value the run does not consume. Parsed with `tomllib`; the config-substitution engine is NOT used (that value is a literal). The value MUST be type-checked as a `str` where it is read (amended, whole-branch review C1) — TOML is a typed format, so `org_id = 12345` otherwise reaches `urllib.parse.quote` a whole session later as an unnamed `TypeError` at exit 1. |
| `-v`, `--verbose` | off | Per-site progress to stderr. `SKIPPED:`/`WARNING:`/`RETRY:` lines and the summary are printed regardless. |

The parser MUST set `allow_abbrev=False`, matching the main tool's house rule.

**Machine token resolution**, in order: `$PANTHEON_MACHINE_TOKEN` if set and non-empty;
otherwise the single JSON file in `~/.terminus/cache/tokens/`, whose `token` key is used. Zero
files, more than one file, an unreadable file, or a missing `token` key is **fatal** (exit 2)
with a message naming what was found — never a guess (PD#1).

> **PD#6 tension, stated rather than buried.** The main program NEVER reads credentials from
> the environment; everything flows through `<{secret env …}>` config substitution. This script
> reads one credential from the environment and one from the Terminus token cache. Justification:
> it is standalone, has no substitution engine, and adding a secret key to the shared production
> TOML for a script that is deleted within months is the worse outcome.
>
> **Threat model, with the properties that hold and how each is held.** (a) Neither the machine
> token nor the session token is ever logged, echoed, or written to stdout — and this is
> **instrumented**, not asserted: §10 item 12 requires a test that forces an auth failure and a
> G5 and asserts neither token appears anywhere in captured stdout+stderr. An unmeasured
> security claim is PD#14 in its design-time form. (b) The machine token goes to Pantheon in a
> POST **body**, never on argv, so it is not visible in `ps` on a shared host. (c) The session
> token rides in an `Authorization` header on an `httpx.Client` that does **not** follow
> redirects (httpx's default), so the header cannot be replayed to a redirect target; this
> default is load-bearing and MUST NOT be changed to `follow_redirects=True`. (d) No credential
> is written to any file: the script creates no files at all, so there is no umask question.
> (e) The response bodies this script receives contain other people's credentials — see the
> NEVER rule in §8.

## 4. Data sources

All Pantheon data comes from the Pantheon API (CLAUDE.md's stated preference for new code), not
Terminus. Every row below was verified live on 2026-07-28 against the real organization.

| Call | Purpose | Verified shape / behavior |
|---|---|---|
| `POST /v0/authorize/machine-token` body `{"machine_token": …, "client": "find-platform-domains-dns"}` | session token | returns `{"session": "…"}` |
| `GET /v0/organizations/{org_id}/memberships/sites?limit=100&start={last_site_id}` | site list | `limit` max 100; `start` is a site UUID, exclusive. **Read §4.1 before implementing — the cursor has a silent failure mode.** Each element: `{"id": <membership id, equal to site.id for all 408>, "site": {"id", "name", "plan_name", "framework", "frozen", …}}` |
| `GET /v0/site-names/{site_name}` | name → id for `SITE` args | `{"id": "…"}` |
| `GET /v0/sites/{site_id}/environments` | environment list | object keyed by environment id; includes multidevs (`autopilot`, `test-mark`, …); each value carries `initialized`, `php_version`, … |
| `GET /v0/sites/{site_id}/environments/{env_id}/domains` | domain list | array of `{"id", "type", "primary", "status", …}`. **`type` is `platform` or `custom` in every entry observed** (37 entries across 8 sites, 2026-07-28) — but that is an observation, not a documented enumeration, so an unrecognized value is reported and counted rather than silently skipped (G6a). An uninitialized environment returns its platform domain only. |

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
   final boundary cursor returns `[]` in every recent measurement (CASE D of the report, 7/7)
   — **but the report also records one early run in which it returned a full 100-element first
   page**, and that contradiction is not resolved. An *unrecognized* cursor returns a full
   first page rather than `[]`, so a loop with that stop condition never terminates once it
   goes off the boundary. Stop on a **short page** instead.

   **Accepted residual, from that unresolved contradiction.** An organization whose site count
   is an exact multiple of 100 is the only one that ever issues the final boundary cursor (any
   other count stops on a short page first). If that cursor misbehaves as it did in the early
   run, the loop sees a non-empty page contributing zero new ids, G4a fires, and the sweep
   **exits 2 on a listing that was actually complete**. That is a false failure, but it is a
   loud one, and the alternative — accepting an exact-multiple count as complete — cannot be
   distinguished from the silent truncation the detector exists to catch (a truncation also
   always lands on a multiple of 100). Unreachable for U-M today at 408 sites; G4a's message
   therefore names the cross-check that resolves it (§7).
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

**NEVER** write anything but CSV rows to stdout. Progress, `SKIPPED:`/`WARNING:`/`RETRY:` lines,
and the summary go to stderr, so `find-platform-domains-dns > domains.csv` yields a clean file.

**The one sanctioned exception is G0** (§7): when stderr itself is closed, the single line naming
that fact goes to stdout, because CPython's `print(…, file=None)` falls back there. That is one
line on a run that writes no CSV at all, and the alternative is total silence, which is PD#1.

## 6. Algorithm

### 6.1 Sweep flow

```
 stdout and stderr both open?  ── no ──→ G0: named message, exit 2
        │                                   (before any config or network work)
        │ yes
        v
 pantheon-sitehealth-emails.toml ──[Pantheon].org_id──┐   (read ONLY when there are no SITE
 $PANTHEON_MACHINE_TOKEN or                           │    args — the org branch below is the
 ~/.terminus/cache/tokens/<user> ──machine token──┐   │    only consumer; a str, or G1)
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
        ├── indeterminate ──→ SKIPPED: on stderr, counter += 1, no row
        └── hit ────────────→ two integrity checks (§7), then one CSV row on stdout
                              (a check that fires prints WARNING: and still writes the row)
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

A transient resolver failure is retried **once**, and the delay before the retry depends on
which failure it was — measured, not assumed:

| Exception | Time dnspython already spent | Retry delay |
|---|---|---|
| `Timeout` | ~5 s (its own lifetime) | **none** — an added delay buys nothing |
| `NoNameservers` | ~0.3 s (SERVFAIL/REFUSED comes straight back) | **`DNS_RETRY_SLEEP` = 1 s** |

The `NoNameservers` case is the one that matters at sweep scale: a sweep issues ~1,600 lookups,
and the most likely cause of a burst of SERVFAILs is the recursive resolver rate-limiting us.
Retrying 0.3 s later re-fires into the same condition, so every affected domain would become an
indeterminate for no reason (PD#3's upstream-error shadow, traced at the scale the sweep
actually runs at).

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
| G0 | `sys.stdout` or `sys.stderr` is `None` — the descriptor was closed by the caller (`>&-`, `2>&-`) (added, whole-branch review I2) | — | fatal message naming which stream, **on whichever stream still exists** (§5's one sanctioned exception) | — | — | no, **exit 2** |
| G1 | Config file missing / unparseable / `[Pantheon].org_id` absent or not a string | — | fatal message | — | — | no, **exit 2** |
| G2 | Machine token unresolvable (0 or >1 cache files, unreadable, no `token` key) | — | fatal message naming what was found | — | — | no, **exit 2** |
| G3 | `POST /authorize/machine-token` fails | — | fatal message | — | — | no, **exit 2** |
| G4 | Organization site listing fails, or a `SITE` arg's name lookup fails | 1 (per §7.1) | fatal message | — | — | no, **exit 2** |
| G4a | A **non-empty** site-list page contributes zero new ids (the cursor was silently ignored, §4.1). An **empty** page is not this condition — it is a legitimate end of collection | 3 attempts of the same cursor, `RETRY_SLEEP` apart | `RETRY: site listing cursor was ignored …` on each attempt that is followed by another (amended, fix round 1: was `SKIPPED:`, which broke §8's `SKIPPED:`-vs-`indeterminate=N` reconciliation on a retry that goes on to succeed — see §8); then a fatal message that MUST name the cross-check: `run 'terminus org:site:list <org_id> --format=json \| jq length' to check whether <N> is the true site count` — with the real org id interpolated, because `terminus org:site:list` **requires** the organization as a positional argument (verified: without it, `Not enough arguments (missing: "organization")`), and a cross-check command that fails is worse than none (§4.1's accepted residual) | — | — | no, **exit 2** after the third |
| G4b | The site-list loop exceeds 100 pages | — | fatal message | — | — | no, **exit 2** |
| G5 | `environments` call fails for a site | 1 | `SKIPPED: <site>: could not list environments: <reason>` | no | **yes** (once for the site) | yes, next site |
| G6 | `domains` call fails for an environment | 1 | `SKIPPED: <site>.<env>: could not list domains: <reason>` | no | **yes** (once for the env) | yes, next env |
| G6a | A domain entry's `type` is neither `custom` nor `platform` | — | `SKIPPED: <site>.<env> <domain>: unknown domain type '<type>'; not examined` | no | **yes** | yes, next domain |
| G7 | HTTP 401 mid-sweep (session expiry) | re-authenticate once, then retry the request | `-v` note only | — | no | yes |
| G7a | The re-authentication itself fails, or the retried request 401s again (revoked/expired machine token) | — | fatal message naming session expiry as the cause | — | — | no, **exit 2** |
| G8 | DNS `Timeout` / `NoNameservers` | 1 | `SKIPPED: <site>.<env> <domain>: transient DNS error at <name>: <Type>` | no | **yes** | yes |
| G9 | Malformed DNS name | — | `SKIPPED: … not a valid DNS name: <detail>` | no | **yes** | yes |
| G10 | Chain loops, or exceeds 8 hops | — | `SKIPPED: … CNAME chain loops at <name>` / `… exceeds 8 hops` | no | **yes** | yes |
| G11 | Custom domain is itself a platform domain | — | `SKIPPED: … is itself a platform domain; no CNAME record to replace` | no | **yes** | yes |
| G12 | Hit whose `platform_domain` resolves to no address (definitively) | — | `WARNING: … platform domain <t> does not resolve; the downstream rewrite has no addresses to use` | **yes** | no | yes |
| G13 | Hit whose `platform_domain` is not one of this environment's own platform domains | — | `WARNING: … points at <t>, which belongs to a different site/environment (expected one of: …)` | **yes** | no | yes |
| G13a | Hit whose `dns_record` is **not** the custom domain — the record to rewrite is a mid-chain alias | — | `WARNING: … the record to change is <dns_record>, not the custom domain; verify who else points at it before rewriting` | **yes** | no | yes |
| G14 | Hit, clean | — | nothing | **yes** | no | yes |
| G15 | `KeyboardInterrupt` (Ctrl-C) | — | the summary line for the work done so far, plus the last site processed and the names of every site not yet reached (§7.3; amended, fix round 2 of task 5, N8: this row previously said only "how many remain") | rows already written stay written | — | no, **exit 130** |
| G16 | `BrokenPipeError` on stdout (`… \| head`) | — | `ERROR: sweep did not complete (stdout closed (broken pipe))`, **followed by the §7.3 abort report** — this reuses the same shared abort-reporting function every exit-2/130 path calls (`report_stop`), which is why all of them share this `ERROR: sweep did not complete (<reason>)` shape rather than G16 having bespoke wording; stderr is unaffected by a closed stdout, so there is no reason to withhold it. `report_stop` MUST also flush stdout and, **if that flush fails**, `os.dup2` devnull onto its descriptor: CPython re-flushes stdout at interpreter shutdown, that flush raises again on a closed pipe, and a failed final flush becomes **exit 120**, overriding the 2 (verified live 2026-07-28). Amended, whole-branch review I1: the recipe lives in `report_stop` rather than in this arm, because the mechanism is not pipe-specific — a full disk or an over-quota redirect target reaches the G18 arm and produced the same 120 (verified live with `> /dev/full`). Making it conditional on the flush failing is equally load-bearing: unconditional, it discards a row still sitting in a healthy stdout's buffer, and under pytest's fd-level capture it repoints the session's own stdout at `/dev/null` | — | — | no, **exit 2** |
| G17 | An API response has an unexpected shape (a missing/wrongly-typed key) | — | named `PantheonApiShapeError`, reported exactly like G4/G5/G6 depending on which call produced it | no | **yes** when per-site/per-env | as per G4/G5/G6 |
| G18 | Anything else uncaught | — | the exception, then `ERROR: unexpected failure; the sweep is incomplete` | — | — | no, **exit 2** |
| G19 | A **stderr write** itself failed — a full disk, an over-quota redirect target, `2> /dev/full` (added, residual review finding 1) | — | nothing: there is nowhere left to report it. The failing stream's descriptor is repointed at `/dev/null` so neither the rest of the abort report nor CPython's shutdown flush can raise again | rows already written stay written | — | no, **exit 2** (or **130** when the abort being reported was a Ctrl-C) |

**Exit codes.** `0` = sweep completed with zero indeterminates. `1` = sweep completed with ≥1
indeterminate. `2` = the sweep could not be completed (G0, G1–G4b, G7a, G16, G18, G19, or an `argparse`
usage error). `130` = interrupted by Ctrl-C (G15), matching the main program's `abort_reason`
convention (CLAUDE.md § Database). Rationale: a cron wrapper or a human MUST be able to tell a
complete sweep from a partial one without reading stderr (PD#1).

**`1` MUST mean only what this table says it means.** Python exits 1 on any uncaught traceback,
which would be indistinguishable from a healthy sweep that merely had a few DNS timeouts — so
G15–G18 exist to route every other outcome away from that code. `main()` therefore ends with
handlers for `KeyboardInterrupt`, `BrokenPipeError` and a final catch that returns 2, and the
**only** `return 1` in the program is the indeterminate branch.

**G12 detail.** The check resolves `platform_domain` for `A`, then `AAAA`. A definitive empty
answer for both (`NoAnswer`/`NXDOMAIN`) means dead. Any transient or malformed outcome is
treated as **alive** — the check MUST NOT cry wolf on a blip, since its only job is to warn.

**G19 detail — why stderr needs a *different* probe from stdout.** Every operator message in
this program goes to stderr, and until this fix none of those writes was guarded. Three live
reproductions, all exiting **120** — a code §7's taxonomy does not contain, so a `case $?` over
0/1/2/130 in a cron wrapper falls straight through:

```
$ ./find-platform-domains-dns bus-occb    2> /dev/full > /tmp/o3.out   -> exit 120  (complete CSV)
$ ./find-platform-domains-dns -v bus-occb 2> /dev/full > /tmp/o4.out   -> exit 120  (EMPTY CSV)
$ ./find-platform-domains-dns -c /dev/null 2> /dev/full                -> exit 120
```

CPython's `flush_std_files()` at interpreter shutdown flushes **both** std streams and turns a
failure of either into exit 120, so this is the same mechanism G16's stdout recipe defends
against, pointed at the other stream. The realistic case is
`find-platform-domains-dns -v --all 2>>sweep.log > domains.csv` on a filesystem that fills.

Three rules, all measured:

1. **The two ends of the road are guarded, and only those.** `report_stop()` and
   `report_startup_failure()` write through `report_line()`, which swallows an `OSError`/`ValueError`
   from its own `print` and detaches the stream. Every other stderr write — `skipped()`,
   `warning()`, `retrying()`, `Sweeper._progress()`, the `-v` re-auth note, the summary line — stays
   **unguarded on purpose**: a failure there propagates into `main()`'s handlers and becomes a named
   abort at exit 2. Guarding them individually would hide the failure instead (PD#1).
2. **The summary print moved inside `main()`'s `try`.** Outside it, an ENOSPC on that one line
   escaped `main()` entirely — the first reproduction above. A sweep whose outcome could not be
   reported has not been reported, so it exits 2.
3. **`detach_doomed_stderr()` must NOT copy `detach_doomed_stdout()`'s flush probe.** `sys.stderr`
   is line-buffered, so its buffer is empty at the moment of the probe on every path where no
   earlier stderr write has already failed — and an empty flush *succeeds* on a filesystem that is
   100% full, reporting a doomed stream healthy (measured: the third reproduction above still exits
   120 with a flush probe). The probe is instead the caller's own failed write. What both halves
   share, and what is pinned in both directions by
   `test_a_healthy_std{out,err}_is_never_detached_on_an_abort`, is the property that matters:
   **a stream that is working is never detached.**

**Deliberately unchanged:** a `-v` run whose stderr is doomed still writes no CSV, because the
sweep really does stop at its first progress line. Continuing with the operator's output silently
going nowhere is what PD#1 forbids; the fix makes the stop *loud* (exit 2), not invisible.

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

### 7.3 Reporting where an aborted sweep stopped

On G15 and on **every** exit-2 path reached after the site loop began — G7a, G16 and G18
alike — the program MUST print, in addition to the summary line:

- where it stopped, **unconditionally**: `Stopped after <site>` when at least one site
  completed, and `Stopped during <site>` when the very first site was interrupted. A line that
  appears only once a site has completed is a MUST that silently does not apply to the first
  38 seconds of a 38-minute sweep;
- the number of sites not reached, **and their names**, space-separated on one line.

The names are the point (§2.2 rejects resumability *because* this line exists): "137 sites not
reached" is not a recovery instruction, because the operator cannot reconstruct which 137 they
were — the order is ascending by site UUID and they have no copy of that list. The sweep holds
them in `Sweeper.remaining`, so printing them costs nothing and turns the line into a
paste-able re-run. Rows already written to stdout stay valid; the sweep never rewrites or
retracts a row.

**The command MUST be rebuilt from the argv the run actually received**, with the unreached names
replacing its `SITE` positionals and **every option preserved** (amended, whole-branch review m2:
it used to be a bare `find-platform-domains-dns <names…>`, which silently discarded `-c CONFIG` —
so an operator who ran `-c prod.toml` pasted a command that reads a *different* file — and `-v`,
the only liveness signal on the re-run). The main program rebuilds its own abort hint from
`sys.argv` for exactly this reason (CLAUDE.md § Database), and the value-taking option strings are
derived from the parser rather than listed, so the list cannot rot when an option is added. A site
name occupying an option's value slot (`-c beta`) is **not** a positional and MUST survive.

**Resuming re-sweeps the site that was in flight.** `Sweeper.remaining` is recomputed only after a
site *completes*, so an interrupted site is still in the list and its already-written rows are
written again by the re-run. That is deliberate — dropping it would risk the missing row §1 calls
the expensive failure — but it means `>> domains.csv` produces **duplicate rows** for that one
site. Either redirect the resume run to a separate file, or expect duplicates and de-duplicate
before handing the CSV downstream. This directly affects §15 question 1, whose whole purpose is
spotting a `dns_record` that legitimately appears twice.

## 8. Observability (PD#5)

- **stdout**: CSV rows only.
- **stderr, always**: the per-finding lines named in §7, and a final summary line:

  Three prefixes (amended, fix round 1 of task 5), because one was ambiguous and a second turned
  out to be too broad. `SKIPPED:` marks a domain, environment or site that produced **no row and
  was counted as indeterminate**; `WARNING:` marks a finding that **still produced its row**
  (G12, G13, G13a); `RETRY:` marks the ONE retry in the program that gets a stderr line **at
  all** — the G4a ignored-cursor retry, which happens entirely inside `prepare_sweep()`, before
  any counters exist, and is **never counted**, not reported again if it eventually succeeds
  (the sweep then just proceeds normally). This is deliberately not a general "retries are
  RETRY:-prefixed" rule (fix round 2, N9: an earlier draft of this paragraph read as one): the
  DNS retry (§6.2's Timeout/NoNameservers-then-retry-once) and the API transport/401/429/5xx
  retries (§7.1) both retry **silently** — RETRY: exists to fix ONE specific reconciliation
  problem (below), not to announce every retry in the codebase. With a single `ATTENTION:`
  prefix, an operator reading `indeterminate=17` at the end of a 38-minute sweep could not `grep`
  out those 17 — the count and the log could not be reconciled, which is PD#5's "surfaced
  actionably" failing in the one place it matters. The original two-prefix design reused
  `SKIPPED:` for the G4a retry line too, which broke the same reconciliation the scheme exists to
  provide: a G4a retry that goes on to succeed is `SKIPPED:`-prefixed but never counted anywhere,
  so `grep -c SKIPPED` could exceed the final `indeterminate=N` on such a run. `RETRY:` closes
  that gap by removing the retry line from the `SKIPPED:` count entirely, rather than inventing a
  place to count it.

  `sites=N envs=N custom_domains=N rows=N indeterminate=N`. The summary is printed on **every**
  path that entered the site loop, including G15 (Ctrl-C) and the exit-2 aborts — a partial
  sweep's counts are exactly when an operator needs them (§7.3). It is not printed on G1–G4b,
  which fail before any sweeping happens and have nothing to count.
- **stderr, `-v` only**: one progress line per site (`[12/408] bus-occb`), that site's
  environment and custom-domain counts when it finishes, and the session re-authentication
  note (G7).
- **NEVER `rich`.** Plain `print(…, file=sys.stderr)`. The main program's console has two
  documented traps — markup silently deleting `[bracketed]` fragments (exactly the shape of DNS
  and API error text) and an 80-column hard wrap on a non-tty. Not importing `rich` removes
  both by construction rather than by discipline.
- **NEVER print an API response body**, at any verbosity, and never include one in an error
  message. This is a security rule, not a tidiness one: `GET /sites/{id}/environments` returns
  each environment's HTTP-lock credentials in cleartext — verified live 2026-07-28 on a real
  organization site, `"lock": {"locked": true, "username": "…", "password": "…"}`. Error
  messages carry the request path and the status code, never the payload. The obvious "dump
  the JSON at `-vv`" feature is the thing this rule exists to forbid.

## 9. Seams under test — named and agreed

Per the Spine's spec bar, these are fixed here, before implementation, because the implementer
works test-first and cannot ask.

| Seam | Form | Used by |
|---|---|---|
| `resolve(name, rrtype)` | module-level function, monkeypatched exactly as `psh.dns_classify.resolve` is today; `tests/helpers/dnsfake.make_resolver` builds the fake | every DNS test |
| `get` callable | **injected**, not patched: `org_sites(get, org_id)`, `Sweeper(get=…)` etc. take the getter as a parameter. Production passes `ApiSession.get`; tests pass a dict-driven fake | every enumeration and sweep test |
| `httpx.MockTransport` | passed into `ApiSession`'s client at construction | the retry / re-auth / JSON-error tests, and only those |
| `RETRY_SLEEP` | module-level constant, monkeypatched to `0` | the retry tests (so the suite never actually sleeps) |
| `DNS_RETRY_SLEEP` | module-level constant, monkeypatched to `0` for the NoNameservers retry-count test, or to a call-recording stand-in implementing `__index__` (never a real delay) for the Timeout-vs-NoNameservers asymmetry test | the DNS retry tests |
| the output **stream** | **injected** alongside the CSV writer: `Sweeper(get, writer, stream, …)`. Production passes `sys.stdout`; tests pass the same `io.StringIO` the writer wraps | the per-row flush requirement (§5), which is otherwise untestable — a test's writer and `sys.stdout` are unrelated objects, so nothing would pin the flush |

Six further seams are used **by tests only**, and are declared here because the Spine makes
this binding — "Seams under test are named and agreed — in the spec, before any
implementation" — and an implementer working test-first may not invent one:

| Seam | Form | Used by |
|---|---|---|
| `Path.home` | monkeypatched on the module's `Path` (a global `pathlib.Path` mutation, undone by monkeypatch) | the `machine_token()` cache-file tests |
| `dns.resolver.resolve` | monkeypatched inside the module, **not** the `resolve` wrapper | the wire-level `struct.error` test, which must execute the real `resolve()` |
| `machine_token` | monkeypatched module attribute | the `main()` tests, so no real token is read |
| `build_session` | monkeypatched module attribute | the `main()` tests, which inject a stub session |
| the injected stream's `flush` | monkeypatched on the test's own `io.StringIO` | the per-row flush test |
| `sys.stdout` / `sys.stderr` / `os.dup2` | monkeypatched on the module's own `sys` and `os` (a global mutation, undone by monkeypatch); the stream stand-in is a real-descriptor object whose flush (stdout) or write (stderr) fails, and `os.dup2` is replaced by a recorder | the exit-120 detach tests: G16's stdout half and G19's stderr half, in both directions (doomed → detached, healthy → never detached). Declared here by the residual review, which found the stdout half already using it undeclared |

Beyond those, no seam is created. In particular there is **no** patching of `time.sleep`, and
no patching of `httpx.Client` itself (the HTTP tests use `httpx.MockTransport`, which is the
library's own supported seam).

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
   still writes the row and emits `WARNING:`; G13 cross-site target still writes the row and
   emits `WARNING:`; G12 with a transient lookup emits **nothing**. Plus the wire (added,
   whole-branch review I3): `sweep_env` MUST hand `check_domain` the platform-domain set
   `partition_domains` returned — passing `set()` there makes every real hit emit a spurious G13
   and left the whole suite green.
7. Counters and exit codes: a sweep with one indeterminate returns 1; a clean sweep returns 0;
   G5 counts the site once and continues to the next site.
8. CSV mechanics: the writer emits `\n`, not `\r\n`, and each row is flushed as it is written
   (via the injected stream seam, §9).
9. **The copied `resolve()` itself**, executed for real rather than monkeypatched — it has no
   coverage otherwise, and it is copied code, which is exactly where a transcription slip ships
   green (PD#14). Three cases, ported from `tests/unit/test_dns_classify.py`: the literal text
   `"\300.com"` raises `MalformedNameError`; a `dns.resolver.resolve` monkeypatched to raise
   `struct.error` surfaces as `dns.resolver.NoNameservers` (transient), **not** as a malformed
   name — the distinction §6.3 calls load-bearing; and a `dns.resolver.resolve` monkeypatched to
   raise a real `dns.name.IDNAException` (obtained by calling the actual dnspython IDNA codec,
   not hand-constructed) is also converted to `MalformedNameError` — this is `resolve()`'s
   *second* except clause (§6.3's "unchanged copies" of the exception handling), a separate
   branch from the parse-time one the first two cases exercise, and it has no coverage of its
   own without this case.
10. `machine_token()`: `$PANTHEON_MACHINE_TOKEN` wins; the single-cache-file path; and the two
    G2 branches the plan would otherwise leave untested — an unreadable/undecodable file, and a
    file with no `token` key.
11. Observability: the G7 re-authentication note appears under `-v` and **not** without it —
    driven through `main(["-v", …])` and `main([…])`, not through `ApiSession` alone, since the
    verbosity gate lives in `main`; the per-site environment/custom-domain counts appear under
    `-v`; the summary line and the §7.3 position line are printed on an aborted sweep as well
    as a completed one, **including the broken-pipe path**.
12. **Security**: a test that forces the two failures §3 names — an **authentication failure**
    (a 401 that survives re-authentication, i.e. G7a) and a **G5** (a per-site `environments`
    call that fails) — and asserts that neither the machine token nor the session token appears
    anywhere in captured stdout+stderr (§3's threat model, property (a)). A test that merely
    fails the site listing exercises neither path and would be a green check over untraversed
    code (PD#14).
13. Aborts: `KeyboardInterrupt` mid-sweep returns 130 and prints the summary plus the last site
    processed (§7.3); a re-authentication failure (G7a) aborts with 2 rather than degrading into
    one indeterminate per remaining site; `BrokenPipeError` returns 2.
14. G13a: a mid-chain hit (`dns_record != custom_domain`) still writes its row and emits the
    shared-alias WARNING; a direct hit does not.
15. **Exit 1 is unreachable except as specified.** `main()` returns 2, not 1, for **every entry
    in this list, which is exhaustive as of the whole-branch review** — new members are added
    here as they are found, and each was an uncaught traceback (therefore exit 1) when it was:
    a config whose `[Pantheon]` is not a table (a `TypeError` from subscripting a string); a
    config that is not valid UTF-8 (a `UnicodeDecodeError`); an API response missing a key that
    `_require` guards; an unreadable `~/.terminus/cache/tokens/` (a `PermissionError`, fix round
    1 of task 5); **a wrongly-typed `[Pantheon].org_id`** (`org_id = 12345`, which reached
    `urllib.parse.quote` as `TypeError: quote_from_bytes() expected bytes` — whole-branch review
    C1, the third instance of this class this branch shipped, which is why the list is now marked
    exhaustive and why the value is validated where it is *read*); **a wrongly-typed `name`/`id`
    from `/site-names/`** (whole-branch review m6, the same class on the API side); and
    **a closed `sys.stdout`** (`csv.writer(None, …)` → `TypeError`, whole-branch review I2 / G0).
    The paired G0 half — a closed `sys.stderr` — is not an exit-1 case but a *silent* one: every
    operator line landed in the CSV at exit 0, so it is tested for the stdout content, not the
    exit code alone.
16. **Response-shape coverage is exhaustive over the keys actually read**: a site entry without
    `name`, a `/site-names/` answer without `name`, and a domains array whose element is a
    string all raise `PantheonApiShapeError` rather than `KeyError`/`AttributeError`.
17. A domains-payload shape error is a **per-environment** indeterminate, not a sweep-ending
    exception: a two-site sweep in which one environment's payload is malformed counts one
    indeterminate and still processes the second site (§7 G17).
18. G6a: a domain entry whose `type` is neither `custom` nor `platform` is reported, counted,
    and does not silently vanish.
19. **G19 — a failed stderr write never leaves the §7 taxonomy** (added, residual review
    finding 1). Five behaviors, each a live reproduction turned into a test: a completed sweep
    whose summary line cannot be written returns 2 rather than escaping `main()`; each of the four
    abort arms (`OSError`, `KeyboardInterrupt`, `SessionExpiredError`, `BrokenPipeError`) still
    returns its own code with stderr doomed; a startup failure (G1) does too; the `retrying()`
    line inside `prepare_sweep()` does too; and — the direction that must be able to go red — **a
    healthy stderr is never detached**, driven over an abort with a REAL descriptor, because a
    version of that test driven over a *completed* sweep, or over capsys's descriptor-less
    pseudo-stream, stays green against an unconditional detach (PD#14; that first draft was
    written, measured green under the mutation, and rewritten).

**Tests are load-bearing.** NEVER weaken an assertion, delete a case, or relax a fake to make
a test pass. A red test here is a finding about the code.

## 11. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | Pantheon API, not Terminus | Measured: `env:list` 7.4 s and `domain:list` 2.0–2.9 s per Terminus call, vs **~1.1 s** per API call over a reused `httpx` connection (§12); 408 sites × ~5 calls is **~2 h vs ~38 min**. The margin narrowed when the timing was re-measured honestly, but the conclusion did not change. CLAUDE.md prefers the API for new code. |
| D2 | Self-contained script, code copied not imported | PROMPT.md. Deletion is `git rm` of three paths plus three `pyproject.toml` lines (amended, fix round 2 of task 5: §14 item 2 names all three — two `[tool.ruff.lint.per-file-ignores]` entries plus the `[tool.pyright].include` one — this row previously said two). |
| D3 | Committed `find-platform-domains-dns.py` symlink | ruff, pyright, CodeGraph, and importers all key off the `.py` extension; verified 2026-07-28 that ruff 0.15.22 traverses into symlinked `.py` files and pyright 1.1.411 analyzes them. Same convention as `pantheon-sitehealth-emails.py`. |
| D4 | stderr + counted + non-zero exit for indeterminates | User decision. Keeps stdout a clean CSV while making incompleteness impossible to miss. |
| D5 | `dns_record` column | User requirement: the downstream rewriter must edit the record that actually holds the CNAME, which is not always the custom domain. |
| D6 | G13 cross-site check, row still emitted | User decision. The record must go regardless; a cross-site target is a review item, not a disqualifier. |
| D7 | G12 dead-target check, row still emitted | User decision. Turns a downstream crash into a pre-flight warning. |
| D8 | No `rich` | §8. |
| D9 | Machine token from env or Terminus cache | §3, with the PD#6 tension stated. |
| D10 | Every environment queried, uninitialized included | §2.2. |
| D12 | Ctrl-C exits 130; broken pipe, re-auth failure and anything uncaught exit 2 | User decision after round-1 review. Python exits 1 on an uncaught traceback, which collided with "completed with indeterminates" and silently retracted the guarantee that motivated the three-code scheme. 130 matches the main program's `abort_reason`. |
| D13 | G13a — warn when `dns_record != custom_domain` | User decision after round-1 review. Rewriting a mid-chain alias moves every other name pointing at it, possibly outside this organization; the CSV alone cannot reveal that. Sampled as rare (0 of 7 hits across 30 sites), so the warning will not be noisy. |
| D15 | No automatic cross-check of the site count against `terminus org:site:list` | Put to the user as an explicit option during design ("API + reset detector + terminus cross-check") and **declined** in favour of the detector alone: it would make `terminus` a hard runtime dependency of a script whose premise is using the API instead. A reviewer re-raised it; the decision stands, and §15 question 6 keeps it visible. |
| D16 | The duplicate-`dns_record` question is a closing-audit question, not a warning line | Put to the user as an explicit option ("plus a duplicate-alias warning at the end") and **declined** in favour of the per-row warning alone (D13). Sampled at 0 repeats across 30 sites. |
| D14 | No `--resume-from`, but an aborted sweep prints where it stopped | User decision after round-1 review re-opened it: the corrected 38-minute runtime made "just re-run" more expensive than the original rationale assumed, but not expensive enough to justify resume machinery in a script due for deletion. §7.3. |
| D11 | Site list stays on the API, with the G4a reset detector rather than switching to `terminus org:site:list` | User decision after the §4.1 finding was presented. The characterization has since sharpened (§4.1): the walk pattern is *structurally* safe, because it only ever passes page boundaries, and it measured 0 resets across 10+ full walks. The detector is kept anyway — it costs a `seen` set the loop needs regardless, and it converts the residual silent-truncation risk into a loud exit 2. §15 question 4 revisits it with production evidence. |

## 12. Verified facts

Everything load-bearing here was confirmed against the authority on 2026-07-28, not assumed.

| Claim | How it was verified |
|---|---|
| API pagination is `limit`≤100 + exclusive `start` cursor | swagger `GetOrganizationSiteMemberships` |
| The walk pattern (cursor = last id of the previous full page) is reliable | 10+ consecutive live full walks, 0 resets, 408 unique ids each, identical to `terminus org:site:list`'s 408 |
| The cursor is honored **only** at a page boundary; every other id silently returns page 1 with HTTP 200 (§4.1) | live positional scan, `limit=100`: honored at positions 100/200/300/400/408, ignored at 1/2/50/99/101/102/150/199/201/250/299/301/350/399/401/405/407. Reproduced 5/5 for positions 1 and 101 in the run pasted into the bug report, and again at `REPEATS=2` and (independently) `REPEATS=3` |
| The final boundary cursor returns `[]` — so an exact-multiple-of-100 organization really does end on an empty page | live: `start` = the maximum site id → empty array. The pasted run in the bug report shows CASE D `correct=5`; two later runs (`REPEATS=2`, and an independent reviewer's `REPEATS=3`) agreed. Only the first of those is in the committed artifact — cite the report for 5/5 and this row for the rest |
| An *unrecognized* cursor returns a full first page, never `[]` — which is why "loop until empty" cannot be the stop condition | the same positional scan: every ignored position returned `n=100` |
| The collection is ordered ascending by site id and stable across calls | live: every full walk's ids sorted identically; `sort -u` count equals the collected count |
| Membership id equals site id for all 408 sites (so either works as a cursor today; the swagger specifies the **site** UUID) | live: full walk comparing `.id` against `.site.id`, 0 differences |
| Nothing in these tests ever returned a 4xx or 5xx | every probe and walk recorded HTTP 200, including the failing ones. **Consequence:** the §7.1 retry policy's 5xx/429 paths have never been exercised against the real API — they are covered only by `httpx.MockTransport` in §10, item 5 |
| A Pantheon API call costs **~1.1 s** over a reused `httpx` connection, sweeping distinct sites | live: 30 distinct sites, 149 calls (`/environments` + `/domains`, the real mix), 169.8 s → 1.139 s/call. An independent reviewer measured 0.946 s/call over 25 sites the same day, so treat ~0.9–1.2 s as the range and the projection as network-dependent. So 408 sites × ~5 calls ≈ 2,030 calls ≈ **38 minutes**, plus the per-custom-domain DNS walks |
| **Correction, and how it was caught.** An earlier draft of this row claimed 0.61 s/call and a 21-minute sweep | That measurement repeated one site's calls 3× (`its-wws-test1`, 7 environments) rather than sweeping distinct sites, so it measured a cache-warm path that the real sweep never takes. Caught by the round-1 adversarial review re-measuring it. The methodology error — timing the wrong access pattern — is the one worth remembering, not the number (PD#14) |
| A site has ~4.0 environments on average | live: 25-site sample → 101 environments (4.04); 30-site sample → 119 (3.97). (`its-wws-test1` has 7, which is atypical — do not extrapolate the runtime from it) |
| Uninitialized environments are ~9% of environments and held no custom domains in any sample | live: 25 sites → 9/101 (8.9%); 30 sites → 11/119 (9.2%); a reviewer's 25-site sample → 17/95 (17.9%). It varies by sample; every sample found **0** uninitialized environments holding a custom domain, which is the only part §2.2's decision rests on |
| `GET /sites/{id}/environments` returns environment HTTP-lock credentials in **cleartext** | live, on a real organization site: `"lock": {"locked": true, "username": "…", "password": "…"}`. This is why §8 forbids printing any response body at any verbosity |
| `GET /site-names/{name}` returns the canonical site name, not just the id | live: `{"id": "9cf2c790-…", "name": "its-wws-test1"}` — so §3 can require the CSV's `site_name` to come from the response rather than from argv |
| `/environments` includes multidevs | live: `its-wws-test1` → `autopilot, dev, live, test, test-jpr, test-mark, test-md` |
| Domain entries carry `type: platform\|custom` | live: `its-wws-test1.live` → 1 platform + 2 custom |
| An uninitialized environment exposes only its platform domain | live: `vpao-accopp.live` (`initialized: false`) |
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

# 8. Broken pipe (G16): a named message on stderr, exit 2, no Python traceback.
#    `head -0`, NOT `head -1`: with -1 the single row is consumed before the pipe closes, so
#    BrokenPipeError never fires and the command passes without testing anything (PD#14).
./find-platform-domains-dns bus-occb | head -0; echo "exit=${PIPESTATUS[0]}"
```

A full-organization sweep is NOT an acceptance step: it takes ~38 minutes and its output is
operational data, not evidence of correctness. Run it when you actually want the list.

## 14. Deletion checklist (post-migration)

1. `git rm find-platform-domains-dns find-platform-domains-dns.py tests/unit/test_find_platform_domains_dns.py`
   — but **first relocate `_sigint_handler_is_never_left_ignored_at_session_end`** (the
   session-scoped autouse fixture at the top of that test file) to `tests/conftest.py`. It is a
   **repo-wide** instrument: it asserts the whole pytest session ends with SIGINT not left at
   `SIG_IGN`, and the main program's `abort_run()` sets `SIG_IGN` for the same reason this
   utility's `report_stop()` does. `git rm`-ing the file deletes that guard along with the
   utility it happened to be written for (added, whole-branch review m7). Its function-scoped
   sibling `_restore_sigint_handler` goes with the file — it exists only for this utility's own
   tests.
2. Remove **both** `find-platform-domains-dns.py` and `find-platform-domains-dns` entries from
   `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml` (the extension-less entry exists
   because `.claude/hooks/ruff-check.sh` hands ruff the real, extension-less path at edit time,
   not the symlink), the `find-platform-domains-dns.py` entry from `[tool.pyright].include`, and
   the `"$REPO_ROOT/find-platform-domains-dns")` arm from that hook's `case` statement.
3. Remove the CLAUDE.md paragraph describing the utility.
4. Leave `CONTEXT.md`'s glossary additions in place — those terms describe Pantheon, not this
   script.
5. **Leave this whole directory in place** — `development/` is a permanent per-feature archive
   (`development/README.md`), so nothing here is ever deleted, and this item singles out three
   files only because they stay *operationally useful* after the utility is gone, not because
   the rest may be removed (clarified, whole-branch review m8). Those three are
   `pantheon-api-pagination-bug-report.txt`, `reproduce-pagination-bug.sh` **and
   `bug-report.txt`**. `bug-report.txt` is the operator's hand-edited copy
   for sending to Pantheon (commit `b65776d`), with the script attached separately rather than
   inlined; it is deliberately a second copy and will drift from the generated one, so treat
   the generated pair as the record and `bug-report.txt` as the thing that was actually sent. They document a defect in **Pantheon's API**, not in this utility, and stay
   useful (and re-runnable) for as long as that endpoint is paginated — including for whoever
   next writes a paginated consumer here.

## 15. Closing audit questions (answer after implementation)

1. On the first full-organization sweep: how many rows had `dns_record != custom_domain`
   (G13a), and did any `dns_record` value appear in more than one row? A repeated `dns_record`
   means one rewrite affects two sites, which the CSV cannot show — sampled at 0 of 7 hits
   across 30 sites, but that is a small sample of a case the column exists for.
2. On the first full-organization sweep: how many rows, and how many indeterminates? If
   indeterminates are more than a handful, is the cause a systematic one (a resolver limit, an
   API pattern) rather than genuinely broken domains?
3. Did G13 (cross-site targets) fire at all? If it did, were those rows safe to hand to the
   downstream rewriter?
4. Did any custom domain turn out to be attached to an `initialized: false` environment,
   contradicting the 25-site sample in §2.2?
5. Did the G4a ignored-cursor detector fire during a real full sweep? §4.1 says it should not
   be able to — the walk only ever passes page boundaries — so if it fires, the boundary model
   in the bug report is incomplete. In that case move the site list to `terminus org:site:list`
   (one call, no cursor) rather than tuning the retry, and re-run
   `reproduce-pagination-bug.sh` to see whether Pantheon's behavior has changed.
6. Did the pagination loop ever see a page that was neither 100 nor final — i.e. does the API
   ever return a short non-final page, which would break the stop condition? The detector
   (G4a) catches a *repeated* page, not a short non-final one, so this remains an accepted
   exposure (D15). Check it on the first full sweep with
   `terminus org:site:list <org_id> --format=json | jq length` — note the **required**
   organization argument.
