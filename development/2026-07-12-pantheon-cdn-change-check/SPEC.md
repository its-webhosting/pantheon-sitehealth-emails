# Pantheon CDN Change Check — SPEC

Status: approved design (2026-07-12). Feature prompt: `PROMPT.md` (this directory).
Standards: `prompts/new-feature-standards.md`. Conventions: `CLAUDE.md`.

## 1. Glossary

Each term is used exactly once per concept, in this spec, in the code, and in the
owner-facing notice copy.

| Term | Meaning |
|---|---|
| **legacy Pantheon GCDN (Fastly)** | Pantheon's current CDN. Its edge names live under `pantheonsite.io`. Owner-facing copy may shorten to **legacy GCDN** after first use. |
| **new Pantheon GCDN Beta (Pantheon Cloudflare)** | Pantheon's replacement CDN. Owner-facing copy may shorten to **new GCDN Beta** after first use. |
| **U-M Cloudflare** | Our (non-Pantheon) Cloudflare — the one `plugin/cloudflare`, `check/cloudflare` and `[Cloudflare]` refer to. Owner-facing term when `sc.umich_enabled()`. |
| **our (non-Pantheon) Cloudflare** | The generic (non-U-M) owner-facing term for the same thing. |
| **legacy-GCDN name** | Any DNS name whose normalized form ends in `.pantheonsite.io` (e.g. `live-bus-occb.pantheonsite.io`). |
| **custom domain** | A Pantheon domain of `type == "custom"` on the site's **live** environment, as returned by `terminus domain:list <site>.live`. Platform domains (`type == "platform"`) are never checked. |
| **origin** | The `content` of a Cloudflare-**proxied** DNS record, as captured in `fqdns.json` by `plugin/cloudflare/fqdns.py`. |
| **finding** | One custom domain that reaches a legacy-GCDN name via a CNAME chain, plus where the owner must fix it and the required records Pantheon says to use instead. |
| **required records** | The records **Pantheon** says a custom domain must have, from `terminus domain:dns <site>.live` — A/AAAA normally, or a CNAME to `fe.*.edge.pantheon.io` for a site already on the new GCDN Beta (F14). The single source of what the owner is told to use. NEVER derived by resolving the legacy-GCDN name ourselves — see §4.1. |
| **cutoff** | `2026-09-15`. Before it, U-M sites are told ITS will do the work; on/after it, U-M sites get the generic copy. |

RFC-2119-style keywords: **MUST** (required), **SHOULD** (required unless a stated reason
applies), **MAY** (optional), **NEVER** (prohibited). Lists are marked *exhaustive* or
*illustrative*; there are no open-ended denylists in this design.

## 2. Problem

Pantheon is migrating from the legacy Pantheon GCDN (Fastly) to the new Pantheon GCDN Beta
(Pantheon Cloudflare) — see
<https://docs.pantheon.io/guides/global-cdn/global-cdn-beta#setup>. A site cannot be
migrated while **any** of its custom domains reaches a legacy-GCDN name through a CNAME
record, in public DNS **or** in U-M Cloudflare. Those CNAME records MUST be replaced with A
and AAAA records.

The core script already carries a TODO describing exactly this
(`pantheon-sitehealth-emails:1655-1657`); this feature implements it and that TODO MUST be
deleted in the same change.

Verified on 2026-07-12 (live DNS + the current `fqdns.json`), and load-bearing for the
design:

- `occb.bus.umich.edu` → CNAME `live-bus-occb.pantheonsite.io` → CNAME `fe4.edge.pantheon.io`
  → A `23.185.0.4`, AAAA `2620:12a:8000::4`, `2620:12a:8001::4`. Visible in **public DNS**.
- `backstage.its.umich.edu` → public DNS shows only CNAME
  `backstage.its.umich.edu.cdn.cloudflare.net` → Cloudflare anycast addresses. The
  legacy-GCDN name is visible **only** in Cloudflare, and `fqdns.json` already has it:
  `{"origins": ["live-its-backstage.pantheonsite.io"], "zone_id": "1f39…"}` → A `23.185.0.2`,
  AAAA `2620:12a:8000::2`, `2620:12a:8001::2`.
- 245 of the 1871 FQDNs in the current `fqdns.json` have a legacy-GCDN origin.

**Why two sources are both required (not redundant):** a *proxied* FQDN's Cloudflare CNAME is
invisible in public DNS; an *unproxied* (grey-cloud) Cloudflare CNAME is absent from
`fqdns.json` (which lists proxied records only) but **is** visible in public DNS. Together
they cover every case. This also means we NEVER need to detect who operates DNS for a
domain — which the prompt explicitly forbids.

## 3. Scope

**In scope** (exhaustive):

1. A new self-registering check package `check/pantheon_cdn_change/` with one hook at the
   `site_post_dns` phase.
2. Detection of custom domains reaching a legacy-GCDN name via a CNAME chain, from both
   sources above.
3. The replacement records, from **Pantheon** (`terminus domain:dns <site>.live`), one lazy
   call per *affected* site. **NEVER** derived by resolving the legacy-GCDN name (§4.1).
4. Exactly **one** `info` notice per site listing every affected custom domain in a table.
5. Deletion of the obsolete core TODO at `pantheon-sitehealth-emails:1655-1657`.
6. Tests (unit, integration, snapshot, a fourth e2e golden) and a `docs/` page.
7. **Three changes outside the new package**, all forced by defects this design exposed
   (adversarial review, 2026-07-12):
   - `dns_classify.resolve` raises a **named** `MalformedNameError` instead of leaking
     dnspython's `dns.exception.SyntaxError` / `dns.name.NameTooLong`, and
     `classify_hostname_dns` catches it. **This is a live bug in core today** (F10): a
     Pantheon domain id like `a..b` passes `fqdn_re` (`pantheon-sitehealth-emails:89`),
     reaches `dns.resolver.resolve`, raises `dns.name.EmptyLabel`, and — because the per-site
     loop has no `try`/`except` — aborts the entire `--all` run.
   - `plugin/cloudflare/fqdns.py`'s existing staleness warning (`:219-223`) gains one sentence
     naming the consequence for this check (F12). **No new `plugin_context` contract, no
     per-site warning:** the plugin already warns exactly when the file is stale *and* the run
     will consume it, and a missing file on a consuming run is auto-refreshed
     (`decide_fqdns_update:64`), so the only honest fix is one better sentence in the module
     that owns the file.
   - The core sc-exposure block (`pantheon-sitehealth-emails:1194-1198`) gains `sc.terminus`
     and `sc.fqdn_re` — the documented way a check package reaches a core helper (CLAUDE.md:
     "extend that block for new ones"). Needed for `domain:dns` (§4.1) and for validating
     domain ids (§5).

**NOT in scope** (exhaustive — each was considered and rejected):

- Non-live environments (dev/test/multidev). The prompt restricts this to live.
- Any special handling of the primary domain vs. other custom domains — the prompt says
  they are treated identically.
- Detecting whether Cloudflare (versus another provider) operates DNS for an FQDN — the
  prompt says to assume the owner knows.
- A run-level operator summary of affected sites/FQDNs (offered, declined 2026-07-12):
  `-notices.csv` already carries the per-site work list.
- Making the cutoff configurable (the prompt forbids it) or emitting a run-level count.
- Explaining Pantheon's migration process, Orange-to-Orange, or Pantheon-vs-our-Cloudflare
  in the notice.

## 4. Architecture

New package, seven files, plus the three out-of-package changes listed in §3.

```
check/pantheon_cdn_change/
  __init__.py   registers ONE hook at site_post_dns, unconditionally (no config gate)
  model.py      PURE: the Finding NamedTuple (imports nothing but typing)
  chain.py      CNAME-chain walker (DETECTION only); resolves ONLY via dns_classify.resolve
  pantheon.py   Pantheon's REQUIRED RECORDS per custom domain, via sc.terminus("domain:dns", …)
  detect.py     custom domains + fqdns.json origins + required records -> [Finding]
  notices.py    PURE: [Finding] -> one notice dict (U-M / generic x before / on-or-after cutoff).
                Imports only html + model -- NEVER detect/chain/pantheon, so it pulls in neither
                dnspython nor terminus.
  hook.py       the site_post_dns entry point; owns the cutoff constant + today() seam
```

### 4.1 Where the replacement records come from — and where they MUST NOT

**The addresses come from Pantheon, per domain**, via `terminus domain:dns <site>.live`. They
are NEVER derived by resolving the legacy-GCDN name the broken record points at.

*Why this is not a style preference.* The obvious design — "resolve
`live-bus-occb.pantheonsite.io` and print its A/AAAA" — is wrong precisely in the cases this
check exists to catch. When a record points at a **stale** legacy-GCDN name (the site was
renamed on Pantheon, a Cloudflare origin was never updated, a domain moved between Pantheon
sites), that name belongs to a **different Pantheon site**, and resolving it yields *that
site's* edge addresses. We would email an owner someone else's IP addresses, with confidence.
Pantheon answers per-domain and is never stale:

```
$ terminus domain:dns bus-occb.live --format=json          # verified 2026-07-12
occb.bus.umich.edu     A     23.185.0.4          | Add this required record
occb.bus.umich.edu     AAAA  2620:12a:8000::4    | Add this required record
occb.bus.umich.edu     AAAA  2620:12a:8001::4    | Add this required record
occb.bus.umich.edu     CNAME (detected: live-bus-occb.pantheonsite.io) | Remove this detected record
```

It also **auto-follows Pantheon's own migration**: `its-wws-test1` is already on the new GCDN
Beta and `domain:dns` returns `fe.cfp2c.edge.pantheon.io` / `185.178.196.3` / `2a0a:6c80::3`
for it. A DNS-derived address would have frozen the legacy values into an email that ages badly.

*Why `terminus` and not the Pantheon API.* The API has the same endpoint —
`GET /v0/sites/{site_id}/environments/{env_id}/domains/dns` (verified 2026-07-12, returns the
same per-domain rows) — and CLAUDE.md prefers the API for new code. But the script has **no
Pantheon API client**: adopting it here means building machine-token → session-token auth, a
session cache, an HTTP seam, and new offline fixtures, for a check that gets deleted after the
migration. `terminus()` is the established wrapper and `run_terminus()` is the harness's mock
seam, so this rides the existing offline test machinery at zero cost. CLAUDE.md explicitly
allows `terminus` when it is "significantly cleaner or significantly simpler" — it is. **When
the API client is eventually built, `pantheon.py` is a one-function swap.**

*This is a deliberate deviation from the prompt*, which said to look up the A/AAAA of the
`*.pantheonsite.io` target (`PROMPT.md:19`). The prompt's method is correct **only** when that
target is the site's own live name; the failure above is invisible until it isn't. Pantheon's
own answer is strictly better and never stale, so this design takes it. Flagged explicitly so
the deviation is a decision, not a drift.

*Cost.* One extra `terminus` call **per affected site only** — `required_records()` is called
lazily, after detection finds ≥1 candidate. A clean site pays nothing. Measured at **~2.7 s**
per call, so an `--all` run adds ≈9 minutes across today's ≈200 affected sites — acceptable on a
run that is already terminus-bound, and it shrinks to zero as owners fix their records.

*An already-migrated site answers with a CNAME, not addresses* (F14). Verified live on
`its-wws-test1`, 2026-07-12: `domain:dns` returns `CNAME fe.cfp2c.edge.pantheon.io`, `status:
okay`, and **no A/AAAA rows at all**. That is an *answer*, not a failure, and it MUST NOT be
collapsed into the same empty result as a terminus error. `Required` therefore carries `cname`
alongside `a`/`aaaa`, and the notice shows whatever Pantheon requires.

*Detection is unaffected.* `domain:dns` reports only the record it detects **at the FQDN**
(for `backstage.its.umich.edu` it sees `…cdn.cloudflare.net`, not the Cloudflare-side origin),
so it can neither see through Cloudflare nor follow a CNAME chain. Both detection sources and
the chain walk stay exactly as designed.

Registration is **unconditional** (like `check/dns/`): every site this tool reports on is a
Pantheon site, so the check always applies. The Cloudflare-origin source self-gates on
`sc.cloudflare_enabled()`, so an institution with no Cloudflare still gets the DNS half.

### 4.2 Per-site data flow (`site_post_dns`)

The phase guarantees `custom_domains` (and the rest of the DNS contract) is populated — see
CLAUDE.md, "Per-site report pipeline".

```
 site_context["custom_domains"]  (live env only; [] when none/malformed)
            │
            ├─ for each FQDN ──────────────────────────────────────────────────────────┐
            │                                                                          │
            │   ① PUBLIC-DNS SOURCE                  ② CLOUDFLARE SOURCE               │
            │      chain.walk(fqdn)                     origins for fqdn from           │
            │      = follow CNAME hops via              plugin_context['plugin.         │
            │        dns_classify.resolve               cloudflare']['proxied_fqdns']   │
            │            │                              (skipped when [Cloudflare] off) │
            │            │                                  │ for each origin that is   │
            │            │                                  │ a hostname (not an IP):   │
            │            │                                  ▼ chain.walk(origin)        │
            │            ▼                                  ▼                           │
            │   reaches *.pantheonsite.io?          reaches *.pantheonsite.io?          │
            │            │ yes                              │ yes                       │
            │            ▼                                  ▼                           │
            │        where="dns"                    where="cloudflare"                  │
            │            └──────────────┬──────────────────┘                            │
            │                           │  both fired -> where="both"                   │
            │                           ▼   (targets differ -> still ONE row, but an     │
            │                 candidate(fqdn, where)   operator ATTENTION: F11)          │
            └───────────────────────────┬──────────────────────────────────────────────┘
                                        ▼
                    candidates? ── no ──▶ nothing (no notice, no console noise, NO
                          │ yes            terminus call -- a clean site costs nothing)
                          ▼
        pantheon.required_addresses(site_id)  ── ONE `terminus domain:dns <site>.live`
                          │                       Pantheon's AUTHORITATIVE per-domain A/AAAA.
                          │                       NEVER resolve the legacy target ourselves (§4.1).
                          ▼
              Finding(fqdn, where, target, a[], aaaa[])   -- addresses keyed by fqdn
                          ▼
        umich = sc.umich_enabled();  before_cutoff = today() < UMICH_MAINTENANCE_CUTOFF
                          ▼
        site_context.add_notice(cdn_change_notice(site, findings, umich=…, before_cutoff=…))
                          ▼
                  exactly ONE info (🔎) notice, csv key `pantheon-cdn-change`
```

### 4.3 The CNAME walk (state machine)

`chain.walk(start)` checks `start` itself first (so a Cloudflare origin that already *is* a
legacy-GCDN name is a hit with zero queries), then follows CNAME hops.

```
     start ──▶ [ is it a legacy-GCDN name? ] ── yes ──▶ HIT(name)
                        │ no
                        ▼
             [ resolve(name, "CNAME") ]
                  │        │          │
       NoAnswer / │        │ CNAME    │ Timeout / NoNameservers
       NXDOMAIN   │        │ target   │
                  ▼        ▼          ▼
              NO-HIT   (loop back  TRANSIENT (result UNKNOWN;
                        with the    console ATTENTION; FQDN is
                        target)     NOT reported)
                        │
       depth > 8, or the target was already seen (CNAME loop)
                        └──▶ NO-HIT + console ATTENTION
```

## 5. Interfaces

Exhaustive public surface of the new package.

```python
# check/pantheon_cdn_change/model.py
class Finding(NamedTuple):
    fqdn: str          # the site's custom domain
    where: str         # "dns" | "cloudflare" | "both"  (canonical machine values)
    target: str        # the legacy-GCDN name reached (operator context only)
    a: list            # Pantheon's required A records     -- all three empty when domain:dns
    aaaa: list         # Pantheon's required AAAA records     failed or had no row (F4)
    cname: list        # Pantheon's required CNAME values  -- non-empty only for a site already
                       #                                      on the new GCDN Beta (F14)

# check/pantheon_cdn_change/chain.py    (DETECTION only -- no address lookups live here)
LEGACY_GCDN_SUFFIX = ".pantheonsite.io"
MAX_CNAME_DEPTH = 8

class ChainResult(NamedTuple):
    target: str        # the legacy-GCDN name reached; "" when none
    transient: bool    # True: the walk hit a transient resolver error -> result UNKNOWN

def normalize(name: str) -> str          # lowercase, strip one trailing dot
def is_legacy_gcdn(name: str) -> bool    # normalized name endswith LEGACY_GCDN_SUFFIX
def is_hostname(value: str) -> bool      # False for an IPv4/IPv6 literal, True otherwise
def walk(start: str) -> ChainResult

# check/pantheon_cdn_change/pantheon.py
class Required(NamedTuple):
    a: list            # Pantheon's required A records,    in the order Pantheon returned them
    aaaa: list         # Pantheon's required AAAA records  (NEVER re-sorted: a sort key over
    cname: list        # Pantheon's required CNAME values   remote strings is a crash class)

EMPTY = Required([], [], [])

def required_records(site_id: str, site_name: str = "") -> dict
    # {normalized fqdn: Required} from `terminus domain:dns <site_id>.live`.  Rows with an empty
    # `value` ("Remove this detected record") carry no requirement and are skipped; A, AAAA and
    # CNAME rows are all kept -- an already-migrated site answers with a CNAME to
    # fe.*.edge.pantheon.io and NO A/AAAA (verified live on its-wws-test1, 2026-07-12), and that
    # is an ANSWER, not a failure (F14).  A terminus failure returns {} + a console ATTENTION --
    # NEVER fatal to the site (F4).  site_name is used only for the operator message: site_id is
    # a UUID in production.

# check/pantheon_cdn_change/detect.py
def cloudflare_origins(fqdn: str, proxied_fqdns: dict) -> list   # tolerates both fqdns.json forms
def find_findings(site_id: str, custom_domains: list, proxied_fqdns: dict,
                  cloudflare_on: bool) -> list
    # Detects candidates first; calls pantheon.required_addresses(site_id) ONLY if there is at
    # least one (a clean site issues no terminus call at all).

# check/pantheon_cdn_change/notices.py
DOCS_URL = "https://docs.pantheon.io/guides/global-cdn/global-cdn-beta#setup"
def where_label(where: str, *, umich: bool) -> str   # raises ValueError on an unknown `where`
def cdn_change_notice(site_name: str, findings: list, *, umich: bool, before_cutoff: bool) -> dict

# check/pantheon_cdn_change/hook.py
UMICH_MAINTENANCE_CUTOFF = datetime.date(2026, 9, 15)
def today() -> datetime.date             # the seam tests monkeypatch
def check_pantheon_cdn_change(site_context) -> None    # the site_post_dns hook
```

Changes to existing modules (exhaustive):

```python
# pantheon-sitehealth-emails  -- extend the sc-exposure block at :1194-1198 (the documented way
# a check reaches a core helper; CLAUDE.md: "extend that block for new ones")
sc.terminus = terminus     # so check/pantheon_cdn_change/pantheon.py can call domain:dns
sc.fqdn_re  = fqdn_re      # so the check validates domain ids with the SAME regex core uses
```

```python
# dns_classify.py  -- NEW named exception + the seam that raises it (F10)
class MalformedNameError(Exception):
    """`hostname` is not a syntactically valid DNS name.  Raised by resolve() in place of
    dnspython's dns.exception.SyntaxError (EmptyLabel/LabelTooLong/BadEscape) and
    dns.name.NameTooLong (a dns.exception.FormError), which no dns.resolver.* except clause
    catches and which therefore abort the whole run."""

def resolve(hostname, rrtype)            # now raises MalformedNameError; otherwise unchanged
# classify_hostname_dns() catches MalformedNameError -> console ATTENTION, returns (0, 0, False)
# (definitive: the name cannot be in DNS -> the site's existing not_in_dns alert, whose remedy
#  "remove these domains from the Pantheon live environment, or add them to DNS" is correct
#  for a malformed id).  The DnsFacts contract is UNCHANGED -- no new list, no new notice.

# plugin/cloudflare/fqdns.py  -- publish what update_and_load_proxied_fqdns already computes (F12)
sc.plugin_context['plugin.cloudflare']['proxied_fqdns_age_seconds'] = <float | None>  # None: no file
sc.plugin_context['plugin.cloudflare']['proxied_fqdns_stale'] = <bool>                # age > STALE_SECONDS
# 0.0 / False immediately after a refresh.  Consumers read the BAG, never the file (no new import).
```

**Ordering invariant:** `find_findings` MUST preserve the order of `custom_domains`, and
`walk` MUST return the *first* legacy-GCDN name reached. Both keep the notice deterministic
for snapshots.

**One row per FQDN.** Because the addresses come from Pantheon *per domain* (§4.1), both the
DNS record and the Cloudflare record for an FQDN need the **same** replacement values — so a
finding is always one table row, even when the two sources disagree about which legacy-GCDN
name they reach (F11: that disagreement gets an operator ATTENTION, not a second row, because
the owner's *action* is identical either way).

**Validated input (F13).** `find_findings` MUST skip any custom-domain id that fails
`sc.fqdn_re` **or contains `,`, `\r`, or `\n`**, with a `sc.debug` line.

The scope of this guard is exactly one thing: **CSV integrity**. `custom_domains` comes straight
from `domains.keys()` (`dns_classify.py:164-165`), is never validated there, and flows into
`n["csv"]`, which the report writer splits and re-joins on commas with **no escaping**
(`fields = n["csv"].split(",")`, `pantheon-sitehealth-emails:3924-3926`). A comma or a newline in
a domain id would shift or break every column of the ITS maintenance work list.

Two facts about `fqdn_re` that this design depends on (verified 2026-07-12 — do **not** assume
otherwise):
- it **rejects** a comma (`has,comma.example.org` → no match) — that is the guard that matters;
- it **accepts** `a..b`, and its `$` also accepts a trailing newline. So `fqdn_re` alone is NOT
  a validity check: `a..b` is handled by **F10** (the `MalformedNameError` seam), and the
  trailing newline is why this rule adds the explicit `,\r\n` reject rather than trusting the
  regex.

## 6. Gates and preconditions (canonical table)

Every gate in this feature, stated once. No negation chains elsewhere.

| Gate | Condition | Effect when false |
|---|---|---|
| Hook registration | always | n/a — the package registers unconditionally |
| Phase | `site_post_dns` | Never runs on `--update` / `--import-older-metrics` / `--create-tables` (they reach no site phase); runs on both the full-report and `--only-warn` paths |
| Environment | live only | Guaranteed: `custom_domains` comes from `terminus domain:list <site>.live` |
| Domain eligibility | `type == "custom"` | Platform domains are already excluded from `custom_domains` by `dns_classify.classify_domains()` |
| Domain id validity | `sc.fqdn_re.match(id)` **and** no `,` / `\r` / `\n` in it | The id is skipped (with a `sc.debug` line) — never resolved, never shown, never written to the CSV. This is a CSV-integrity guard, not a DNS-validity check; see §5 |
| Pantheon `domain:dns` call | ≥ 1 detection candidate for the site | Not called at all — a clean site issues no extra terminus call |
| Cloudflare source ② | `sc.cloudflare_enabled()` | Source ② skipped entirely; source ① still runs |
| Notice emitted | ≥ 1 finding | No notice, no console output |
| U-M copy | `sc.umich_enabled()` **and** `today() < UMICH_MAINTENANCE_CUTOFF` | Generic copy (also used for every non-U-M run) |

## 7. Failure modes (every error named; zero silent failures)

| # | Trigger | Named handling | Operator sees | Owner sees | Tested by |
|---|---|---|---|---|---|
| F1 | `dns.resolver.Timeout` / `NoNameservers` during a walk | caught in `chain.walk` → `ChainResult(target="", transient=True)` | red `ATTENTION: could not check <fqdn> for a legacy-GCDN CNAME (transient DNS error)` | nothing — an unknown NEVER becomes a finding | `test_chain.py::test_transient_*` |
| F2 | `dns.resolver.NXDOMAIN` / `NoAnswer` during a walk | caught → chain ends, `ChainResult("", False)` | nothing (this is the healthy case) | nothing | `test_chain.py::test_no_cname_is_no_hit` |
| F3 | CNAME loop, or depth > `MAX_CNAME_DEPTH` (8) | walk stops, `ChainResult("", False)` | red `ATTENTION: CNAME chain for <name> loops or exceeds 8 hops` | nothing | `test_chain.py::test_loop_*`, `::test_depth_cap` |
| F4 | `terminus domain:dns` fails, times out, returns unparseable JSON, or has **no row at all** for a given FQDN | `pantheon.required_records` returns `{}` (or the FQDN is absent from the map) → `pantheon.EMPTY`. **NEVER fatal to the site** — this is an enrichment call, not a gate. Distinct from F14: "no answer" ≠ "an answer of a different shape". | red `ATTENTION: could not fetch Pantheon's required DNS records for <site name>: <errors>` (the **name**, never the UUID) | the finding's row is **still shown**, with the records cell reading `unavailable — please contact us` (U-M) / `unavailable` (generic). A missing record NEVER hides a CNAME that must be fixed. | `test_pantheon.py::test_terminus_failure_yields_empty`, `test_detect.py::test_finding_without_records_still_reported`, snapshot |
| F5 | `custom_domains == []` (no custom domains, or `domains` was malformed) | contract guarantees the key exists as `[]` → zero findings | nothing | nothing | `test_check_pantheon_cdn_change.py::test_no_custom_domains` |
| F6 | `[Cloudflare]` disabled, or `plugin_context` has no `proxied_fqdns` | source ② skipped via `.get` chains — NEVER a `KeyError` | nothing | DNS-side findings only | `::test_cloudflare_disabled` |
| F7 | `fqdns.json` entry is in the legacy bare-array form (`{"fqdn": ["origin", …]}`) | `cloudflare_origins` accepts both the array and `{"origins": [...]}` object forms | nothing | correct findings | `test_detect.py::test_legacy_array_form` |
| F8 | A Cloudflare origin is an IP literal (a proxied A/AAAA record) | `is_hostname` → False → no lookup attempted | nothing | nothing (correctly not a finding) | `test_detect.py::test_ip_origin_skipped` |
| F9 | A custom domain id contains markup/HTML metacharacters | `html.escape` on every HTML text node. This notice has exactly one href — the constant `DOCS_URL` — so `sc.escape_url` is NOT used (unlike `check/dns/notices.py`, which builds `https://{hostname}/` links). If a per-domain link is ever added, it MUST go through `sc.escape_url`. | n/a | escaped text | `test_notices.py::test_fqdn_html_escaped`; the rendered-email snapshot |
| F10 | A **malformed** name — a Pantheon domain id or a Cloudflare origin that is not a syntactically valid DNS name (`a..b`, a label > 63 octets, a name > 255 octets). Verified 2026-07-12: `dns.resolver.resolve("a..b", "CNAME")` raises `dns.name.EmptyLabel`, **and `fqdn_re` matches `a..b`**, so no upstream gate stops it. | **Core fix:** `dns_classify.resolve` catches `dns.exception.SyntaxError` and `dns.name.NameTooLong` and re-raises the named `dns_classify.MalformedNameError`. `chain.walk` catches it → no-hit. `classify_hostname_dns` catches it → `(0, 0, False)`. **Neither the check nor the core may ever let it escape:** the per-site loop has no `try`/`except`, so an escaped exception aborts the whole run. | red `ATTENTION: <name> is not a valid DNS name (<ExceptionName>)` | For core: the existing `not-in-dns` alert (correct remedy for a malformed id). For this check: nothing — a name that cannot be in DNS cannot be CNAME'd to the legacy GCDN. | `tests/unit/test_dns_classify.py` (core path) + `test_pantheon_cdn_change_chain.py::test_malformed_name_*` |
| F11 | Both sources hit but reach **different** legacy-GCDN names (a site renamed on Pantheon; a stale Cloudflare origin; a domain moved between Pantheon sites) | ONE finding, `where="both"`, with **Pantheon's** addresses for that domain — correct for both records (§4.1). The disagreement itself is an operator signal, not an owner-facing distinction: the owner's action is the same either way. **This is why the addresses must not be DNS-derived** — the stale target belongs to a *different Pantheon site*, so resolving it would print that site's addresses. | red `ATTENTION: <fqdn> reaches DIFFERENT legacy-GCDN names in DNS (<t1>) and Cloudflare (<t2>) — the records disagree; check the site` | one row, Pantheon's addresses | `test_detect.py::test_split_targets_warn_but_emit_one_row` |
| F12 | Source ② is running on **stale** data: `[Cloudflare]` enabled and `fqdns.json` > 24h old. **This is the normal state of a single-site run** — `decide_fqdns_update` (`plugin/cloudflare/fqdns.py:66`) only refreshes a stale file when `multi_site` is true. Consequence: a newly-proxied FQDN is missed (false negative), or an already-fixed one is still nagged (false positive). *(A **missing** file is NOT a failure mode: any run that reaches a site phase auto-refreshes it — `decide_fqdns_update:64`. That branch is unreachable; do not write code for it.)* | The plugin **already** warns, once, exactly when the file is stale *and* the run will consume it (`fqdns.py:219-223`). This feature adds ONE sentence to that message naming the consequence for this check. **No new `plugin_context` contract, no per-site warning, no module-level "warned" flag** — all three were designed, reviewed, and cut as duplication of a warning that already exists in the module that owns the file. | red, once per run, from the plugin: `ATTENTION: fqdns.json is more than a day old; Cloudflare-side CNAME checks may be answering from stale data — run --update-cloudflare-fqdns` | nothing (the DNS half is unaffected and still correct) | `tests/integration/test_plugin_cloudflare_fqdns.py` (the existing staleness tests, message updated) |
| F13 | A custom-domain id containing `,`, `\r`, or `\n`, or otherwise failing `sc.fqdn_re` | Skipped in `find_findings` before any resolution, with a `sc.debug` line (see §5). **Scope: CSV integrity** — `-notices.csv` splits on commas with no escaping (`pantheon-sitehealth-emails:3924-3926`). NOTE: `fqdn_re` **accepts** `a..b`; that case belongs to F10, not here. | `-v`: `skipping invalid domain id <id>` | nothing | `test_detect.py::test_invalid_domain_id_skipped` |
| F14 | `domain:dns` answers for the FQDN with **no A/AAAA rows** — only a CNAME (`fe.*.edge.pantheon.io`). This is what an already-migrated site returns (verified live on `its-wws-test1`, 2026-07-12: `status: okay`, CNAME only), and it **will** occur as Pantheon flips sites mid-campaign. | `Required.cname` is populated, `a`/`aaaa` empty. This is an **answer**, not a failure: it MUST NOT collapse into F4's empty result, MUST NOT render as "unavailable", and MUST NOT be silent. The notice shows the record Pantheon actually requires, whatever its type. | red `ATTENTION: Pantheon requires no A/AAAA for <fqdn> — it requires CNAME <value>; the site may already be on the new GCDN Beta` | the row's records cell reads `CNAME fe.cfp2c.edge.pantheon.io` (Pantheon's answer) instead of A/AAAA | `test_pantheon.py::test_cname_only_answer_is_kept`, `test_detect.py::test_cname_only_finding_warns`, snapshot |

`except Exception` and bare `except` are NEVER used. The exceptions caught anywhere in this
feature are exactly, and exhaustively: `dns.resolver.NoAnswer`, `dns.resolver.NXDOMAIN`,
`dns.resolver.NoNameservers`, `dns.resolver.Timeout`, and `dns_classify.MalformedNameError`
(which is where `dns.exception.SyntaxError` and `dns.name.NameTooLong` are converted — inside
the `dns_classify.resolve` seam, once, so no caller can forget them).

## 8. Notice copy

One `info` notice (🔎, `sc.icon['info']`), `csv` = `f"{site},pantheon-cdn-change,"` + the
affected FQDNs comma-joined (this is what gives ITS the maintenance work list out of
`-notices.csv`). `short` = `Pantheon CDN change: replace CNAME records`.

The HTML table reuses the markup the core's existing notices use (verified at
`pantheon-sitehealth-emails:2521`), so it inherits the template's mobile-stacking styles and
survives the Emogrifier + `!important` passes unchanged:

```html
<div class="container">
<table class="responsive-table site-updates">
<thead><th class="rt-plan">Domain</th><th class="rt-plan">Change it in</th><th class="rt-plan">Replace the CNAME record with</th></thead>
<tbody>…rows…</tbody>
</table>
</div>
```

The notice supplies its own `text` (as every other notice builder does), so `add_notice` does
not run `html_to_text` on it. Plaintext renders each finding as an indented block rather than
an ASCII table — three addresses per row do not survive a text table legibly:

```
  occb.bus.umich.edu  (change it in DNS)
      A      23.185.0.4
      AAAA   2620:12a:8000::4
      AAAA   2620:12a:8001::4
```

`where_label` (the "Change it in" cell), exhaustive. Any other value MUST raise `ValueError` —
these are the canonical machine values (§5), and a silent fall-through would print a *wrong
instruction* to a site owner:

| `where` | `umich=True` | `umich=False` |
|---|---|---|
| `"dns"` | `DNS` | `DNS` |
| `"cloudflare"` | `U-M Cloudflare` | `our (non-Pantheon) Cloudflare` |
| `"both"` | `DNS and U-M Cloudflare` | `DNS and our (non-Pantheon) Cloudflare` |
| anything else | `ValueError` | `ValueError` |

Each affected FQDN appears in exactly **one** row (§5). The third column shows **Pantheon's
required records** for that domain (§4.1), so it is correct for the DNS record and the
Cloudflare record alike. Its content is exhaustively one of:

| Pantheon's answer | Cell shows |
|---|---|
| A and/or AAAA rows (the normal case) | `A 23.185.0.4` / `AAAA 2620:12a:8000::4` / … (one per line) |
| CNAME only — an already-migrated site (F14) | `CNAME fe.cfp2c.edge.pantheon.io` |
| nothing (call failed, or no row for this FQDN — F4) | `unavailable — please contact us` (U-M) / `unavailable` (generic) |

The heading stays **"Replace the CNAME record with"** in all three cases: the owner's action is
always "replace the legacy CNAME with what this cell says".

**Body, U-M before the cutoff** (`umich and before_cutoff`):

> Pantheon is [making a change to their CDN](DOCS_URL), from the legacy Pantheon GCDN
> (Fastly) to the new Pantheon GCDN Beta (Pantheon Cloudflare). Before **{site}** can move to
> the new GCDN Beta, each of its custom domains must resolve through A and AAAA records
> instead of a CNAME record.
>
> These domains for **{site}** still use a CNAME record:
>
> *(table)*
>
> ITS will make these changes for you during an upcoming maintenance, which we will schedule
> and announce. If you would rather make the changes yourself before then, you are welcome
> to.

**Body, generic** (every non-U-M run, and U-M on/after the cutoff): identical first three
blocks, with the closing paragraph replaced by:

> Please replace each CNAME record above with the A and AAAA records shown.

The notice says nothing else about the migration — no Orange-to-Orange, no Pantheon process,
no Pantheon-versus-our-Cloudflare explanation (prompt requirement).

**Cutoff removal (written down, per Prime Directive #9):** `UMICH_MAINTENANCE_CUTOFF` is a
single dated constant in `hook.py`, flagged with a comment naming both future edits: (a)
change the date once the maintenance is scheduled; (b) after it passes, delete the constant,
the `today()` seam, `before_cutoff`, and the U-M branch of `cdn_change_notice`, leaving only
the generic copy. The whole feature is deleted with `git rm -r check/pantheon_cdn_change`
once Pantheon's migration completes.

## 9. Observability

- **Verbosity 0**: the `ATTENTION` lines of F1/F3/F4/F10/F11/F14 (F12's comes from the plugin),
  plus — when a site has any findings — one summary line, `ATTENTION: <site> has N custom
  domain(s) still CNAME'd to the legacy GCDN`. Every other DNS/Cloudflare problem in this
  codebase announces itself at verbosity 0 (`dns_classify.py:138-162`,
  `plugin/cloudflare/fqdns.py:119-136`); this one MUST too. It also covers the single-site case,
  where `-notices.csv` is not written at all (`pantheon-sitehealth-emails:3936-3948` writes it
  only under `--all`), so the console is the operator's only channel.
- **Operator messages identify a site by its NAME, never its `id`.** `site["id"]` is a UUID
  (`live_site = site["id"] + ".live"`, `pantheon-sitehealth-emails:1540`); an ATTENTION reading
  "could not fetch … for 9cf2c790-…" is not actionable.
- `-v` (`sc.debug`): one line per custom domain — `checking <fqdn> for legacy-GCDN CNAMEs`;
  one line per finding — `<fqdn> reaches <target> via <where>`.
- `-vv`: each CNAME hop taken, and each origin read from `fqdns.json`.
- All console strings that embed a remotely-derived name MUST be `rich.markup.escape`d (the
  `check/cloudflare/cache.py` / `dns_classify.py` convention) — an unescaped `[/…]` sequence
  in a hostname raises `rich.errors.MarkupError` and aborts the run.

## 10. Security

No new credentials, no new network protocol, no new outbound HTTP, no new API calls (source ②
reads data already fetched by the existing `plugin.cloudflare` setup hook). Both new inputs
are remote-derived and untrusted — custom-domain ids (Pantheon) and CNAME targets/origins
(DNS/Cloudflare) — and are escaped at every boundary: `html.escape` for HTML text nodes,
`rich.markup.escape` for the console (the notice's only href is the constant `DOCS_URL`; see
F9). Resolution is bounded (depth 8, loop-guarded), so a hostile CNAME chain cannot hang the
run — but see F10: a *malformed* name must not be allowed to abort the run either.

## 11. Performance

Per custom domain: 1 CNAME query (source ①) plus ≤1 per Cloudflare origin (source ②) —
typically 1–2 queries. Per distinct legacy-GCDN target: 2 queries (A + AAAA), memoized per
site, so a site with 10 affected domains issues 2, not 20. A full `--all` run over ~1000
sites adds low thousands of DNS queries, alongside the several thousand
`dns_classify.classify_domains` already issues.

## 12. Testing

**NEVER-block — tests are load-bearing.** Goldens and snapshots are behavior contracts. A
golden or snapshot MUST NEVER be regenerated to make a failing test pass. If output changes,
the diff MUST be read and justified in the commit message before `--update-goldens` is run.

| Tier | File | Covers |
|---|---|---|
| unit | `tests/unit/test_pantheon_cdn_change_chain.py` | `normalize`, `is_legacy_gcdn`, `is_hostname`; `walk` hit at depth 0/1/3, no-hit, NXDOMAIN, NoAnswer, transient (F1), loop (F3), depth cap (F3), malformed name (F10); `addresses` success + empty (F4) + malformed (F10). Fake `dns_classify.resolve` — NEVER real DNS. |
| unit | `tests/unit/test_pantheon_cdn_change_pantheon.py` (**new module**) | `required_records` parses `domain:dns` rows into `{fqdn: Required}` (A, AAAA **and** CNAME kept; empty-`value` "remove this record" rows skipped); the CNAME-only answer of an already-migrated site (F14); multiple domains per site; a `fatal`/`None`/garbage result → `{}` + ATTENTION, never an exception (F4); Pantheon's row order is preserved (records are NEVER re-sorted — a sort key over remote strings is a crash class); the operator message names the SITE, not the UUID. Drives a fake `sc.terminus`. |
| unit | `tests/unit/test_pantheon_cdn_change_detect.py` | DNS-only / Cloudflare-only / both-agreeing / neither; **split targets → ONE row + ATTENTION (F11)**; **CNAME-only answer → row + ATTENTION, never "unavailable" (F14)**; **no terminus call when there are no candidates**; order preservation; legacy array form (F7); IP origin (F8); Cloudflare disabled (F6); a finding whose FQDN is absent from Pantheon's answer still reported (F4); **invalid domain id skipped — comma/newline, NOT `a..b` (F13)**. |
| unit | `tests/unit/test_pantheon_cdn_change_notices.py` | exactly one notice; `csv` shape; `type == "info"`; `short`; `where_label` matrix **+ `ValueError` on an unknown value**; U-M-before / U-M-after / generic copy differences; no `U-M`/`ITS` anywhere in the generic HTML **or** text; HTML escaping (F9); the docs URL is present. |
| unit | `tests/unit/test_dns_classify.py` (existing file, extended) | **Core F10 fix:** `resolve` converts `dns.name.EmptyLabel` / `LabelTooLong` / `NameTooLong` into `MalformedNameError`; `classify_hostname_dns` catches it and returns `(0, 0, False)` instead of letting it escape. Without this, a malformed Pantheon domain id aborts an `--all` run today. |
| integration | `tests/integration/test_check_pantheon_cdn_change.py` | package loads standalone (SourceFileLoader + probe package, per `test_check_cloudflare_init.py`); registers exactly one `site_post_dns` hook, unconditionally, with **no** `[Cloudflare]`/`[UMich]` config; the hook adds one notice given a `SiteContext` with the contract keys and a patched `plugin_context`; no custom domains → no notice (F5); missing plugin bag → no `KeyError` (F6); **absent/stale `fqdns.json` → ATTENTION (F12)**; the cutoff branch selected via a monkeypatched `hook.today`. |
| integration | `tests/integration/test_pantheon_cdn_change_notice_render.py` | The notice pushed through the **real** `SiteContext.add_notice` and the **real** `email_template.html` Jinja render, then snapshotted — the `tests/integration/test_cachecheck_notice_render.py` precedent. Variants: U-M-before, U-M-after, generic, the F4 `unavailable` row, the F11 split-target double row, and an injected-markup domain id (F9) proving the escaped text cannot break out of the table cell. |
| e2e | `tests/e2e/test_golden_cdn_change.py` (**new, 4th golden**) | The check driven through the **real `main()`**: a `domain:list` fixture for `its-wws-test1` carrying a **custom** domain, a matching hand-built `domain:dns` fixture, and a subprocess DNS shim. Proves what no other test can — that `main()` populates `custom_domains` with the strings the hook consumes, that the `domain:dns` call is wired through `terminus()`, that the notice survives Jinja → Emogrifier → the `!important` pass → the `.eml`, and that its `csv` survives the `fields.insert(1, contacts)` splice at `pantheon-sitehealth-emails:3924-3926`. **Two scope limits, stated not hidden:** (a) `[Cloudflare]` stays **disabled** (enabling it makes `plugin/cloudflare/ips.py:17` call the live Cloudflare API), so this golden covers **source ① only** — source ② keeps its unit + integration coverage; (b) `minimal.toml` has **no `[UMich]` section**, so the golden pins the **generic** copy — the U-M-before-cutoff copy is pinned by the Task-8 render snapshot instead. The golden MUST assert which variant it is, so the distinction cannot rot silently. |
| e2e | the three existing goldens | MUST stay **byte-identical**: their `domain:list` fixtures contain only the platform domain, so `custom_domains` is `[]` and this check emits nothing. Asserted by running the suite, not assumed. Note these goldens can only prove the check stays **silent** — which is exactly why the 4th golden above exists. |

Every test resolves through a monkeypatched `dns_classify.resolve` (CLAUDE.md: "the one
monkeypatchable DNS seam"); the offline tier NEVER touches real DNS or Cloudflare.

**Shared test helpers (DRY):** the fake resolver (`FakeCname` / `FakeAddress` /
`make_resolver`) and the probe-package loader are used by **every new test file in this
change**. They live once, in `tests/helpers/dnsfake.py` and `tests/helpers/checkload.py` —
NEVER copy-pasted per test file. Scope limit, stated deliberately: the **existing**
`check/dns` / `check/cloudflare` / `test_dns_classify` suites keep their own fixtures. Porting
them is a mechanical, unrelated refactor that would inflate this diff and put working tests at
risk; `tests/helpers/` is where they go when someone next touches them.

**Console assertions** use the recording-Console pattern the repo already has
(`tests/integration/test_plugin_cloudflare_fqdns.py:73-75`: `Console(file=io.StringIO(),
record=True, width=200)` + `export_text()`), NOT `capsys`. `capsys` does capture rich output,
but rich wraps at width 80 on a non-tty, so a substring assertion breaks the moment a message
grows and the wrap lands mid-phrase.

## 13. Acceptance criteria

Exact commands. Expected output MUST be pasted (not summarized) into the implementation's
final report.

```bash
./run-tests --fast          # every offline tier: PASS, incl. the 3 unchanged goldens + the new 4th
./run-tests                 # adds the live tier: PASS
git status --short tests/e2e/   # MUST show only the NEW golden -- the 3 existing ones unmodified
```

Plus a manual live check against the two verified example sites (read-only, no `--for-real`).
`--update-cloudflare-fqdns` is REQUIRED here, not optional: a single-site run does not refresh
`fqdns.json` (F12), so without it the Cloudflare half of the `its-backstage` check would be
validated against whatever stale file is on disk — which would not test what we think it tests.

```bash
./pantheon-sitehealth-emails --date 20260630 --update-cloudflare-fqdns bus-occb
# notice row: occb.bus.umich.edu | DNS | A 23.185.0.4, AAAA 2620:12a:8000::4, AAAA 2620:12a:8001::4

./pantheon-sitehealth-emails --date 20260630 --update-cloudflare-fqdns its-backstage
# notice row: backstage.its.umich.edu | U-M Cloudflare | A 23.185.0.2, AAAA 2620:12a:8000::2, AAAA 2620:12a:8001::2
```

## 14. Documentation deliverables

- `docs/pantheon-cdn-change.md` — what the check does, the two detection sources, why the
  addresses come from `terminus domain:dns` and never from resolving the legacy target (§4.1),
  the cutoff constant and how to change/remove it, the `fqdns.json` freshness dependency (F12),
  and how to delete the whole check after the migration. It MUST also record that the addresses
  in a sent email are **Pantheon's recommendation at send time**: they track Pantheon's own
  state (a site already on the new GCDN Beta gets the new edge's records), so whoever performs
  the maintenance re-runs the report rather than trusting a months-old email. And it MUST note
  that the "A and AAAA, not CNAME" requirement is Pantheon's *pre-migration* rule — the
  target-state record type is Pantheon's to define (`its-wws-test1`, already migrated, is
  offered a CNAME to `fe.cfp2c.edge.pantheon.io`).
- `CLAUDE.md` — add `check.pantheon_cdn_change` to the `find_modules()` package list, the
  check-module list, and the DNS-tests note; record `dns_classify.MalformedNameError` as part
  of the DNS-seam contract; **correct the `fqdns.json` note that says only the keys are
  consumed** (the `origins` are consumed now).
- `plugin/cloudflare/fqdns.py:17-20` — the same stale claim lives in the source comment
  ("The main program consumes only the KEYS … the zone_id is stored for a near-future feature
  and is not read yet"). It MUST be corrected in the same change. A stale comment is worse
  than no comment.
- `pantheon-sitehealth-emails:1655-1657` — the obsolete TODO is removed.

## 15. Closing audit questions (answer after implementation)

1. Did any of the three pre-existing goldens change? (They MUST NOT.) Was the new golden's
   content read line-by-line before being committed?
2. Does the generic notice contain `U-M`, `ITS`, or `umich`, in HTML or plaintext? (It MUST
   NOT.)
3. Is `dns_classify.resolve` the only resolution path in the new code? (`grep -rn
   "dns.resolver\|import dns" check/pantheon_cdn_change/` MUST return nothing but the
   `dns_classify` import and the caught exception classes.)
4. Does any new code path catch `Exception` or use a bare `except`? (It MUST NOT.) Is every
   caught exception one of the five named in §7?
5. Is the cutoff constant a single line, commented with both future edits?
6. Can a malformed domain id still abort a run? (Feed `a..b` through `classify_hostname_dns`
   and through `chain.walk`; both MUST survive.)
7. Does `notices.py` import anything but `html` and `model`? (It MUST NOT — that is what keeps
   it PURE and dnspython-free.)
8. Does any record shown to an owner come from resolving a `*.pantheonsite.io` name rather than
   from `terminus domain:dns`? (It MUST NOT — §4.1. `grep -rn "addresses\|required"
   check/pantheon_cdn_change/chain.py` MUST return nothing.)
9. Does a clean site issue a `domain:dns` call? (It MUST NOT — the call is lazy, gated on ≥1
   detection candidate.)
10. Which copy variant does the 4th golden actually pin? (The **generic** one — `minimal.toml`
    has no `[UMich]` section. Confirm the golden asserts this explicitly rather than leaving it
    to chance.)
11. Does a CNAME-only `domain:dns` answer (an already-migrated site) render as "unavailable"?
    (It MUST NOT — F14. Feed a CNAME-only answer through `find_findings` and read the row.)
12. Does any owner-facing CSV line contain a comma or newline that came from a domain id?
    (It MUST NOT — F13.)
