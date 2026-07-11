# Modular Site-Level DNS Checks — Design / Spec

**Date:** 2026-07-10
**Status:** Approved (brainstorming complete); implementation plan at
`docs/superpowers/plans/2026-07-10-modular-dns-checks.md`.
**Standards:** Written to the bar in `prompts/new-feature-standards.md`.

## 1. Goal

Move the site-level **DNS-resolution** logic and notices out of the ~3900-line
`pantheon-sitehealth-emails` core script into two focused, independently testable units,
using the existing plugin/check/config frameworks — without changing report output for the
production (U-M) run or the offline goldens.

## 2. Glossary

Each term is used exactly once per concept throughout this spec and the plan.

| Term | Meaning |
|---|---|
| **DNS engine** | `dns_classify.py`, a new top-level internal module (sibling of `script_context.py`). Pure domain-fact computation. Imports only `script_context as sc`, `ipaddress`, `dns.resolver`, `typing` (`NamedTuple`), `rich.markup` (`escape`). `fqdn_re` is passed in (no `re` import). Never imports the dash-named core script. |
| **DNS check** | `check/dns/`, a self-registering package whose `site_post_dns` hook emits DNS notices. |
| **`resolve` seam** | `dns_classify.resolve(hostname, rrtype)`, the single wrapper over `dns.resolver.resolve`. The one monkeypatch point for offline tests (mirrors `check/cloudflare/httpseam.py`). |
| **`DnsFacts`** | The `typing.NamedTuple` the engine returns from `classify_domains` — every domain-derived `site_post_dns` contract value except the raw `domains` dict. |
| **Resolution notice** | A DNS notice whose trigger comes from A/AAAA resolution: `not-in-dns`, `dns-lookup-failed`, and the three Cloudflare-classification notices. |
| **Domain-config notice** | `no-domains` and `no-primary-domain` — driven by the Pantheon domain list, not by resolution. **Stays in core.** |
| **Contract keys** | The `site_post_dns` keys in the CLAUDE.md per-phase data contract. |

## 3. Requirement keywords

**MUST** = required for correctness/acceptance. **SHOULD** = strong default, deviate only
with a written reason. **MAY** = optional. **NEVER** = prohibited.

## 4. Scope

### In scope
- Extract A/AAAA resolution + Cloudflare classification into the **DNS engine**.
- Move all five **resolution notices** into the **DNS check** at `site_post_dns`.
- Fix two latent bugs (§8).
- Gate U-M wording behind `umich_enabled()` with a generic fallback (§9).
- Aggregate the transient notice to one-per-site (§7, note c).
- Tests + docs for all of the above.

### NOT in scope (deferred — written down per Prime Directive #9)
- **Hook-DAG / producer-consumer ordering.** Rejected for now: the codebase has zero current
  reliance on intra-phase hook order (the "keys-at-phase-entry" invariant handles the one
  existing case). Revisit only when a *second* real intra-phase producer/consumer pair appears.
- **`domain:list` → Pantheon API migration.** Existing core code; switching adds independent
  auth/parity/test-seam risk. Revisit separately.
- **Relocating the two domain-config notices** (`no-domains`, `no-primary-domain`) out of core.
  Kept in core by decision — `no-primary-domain` fires a live `drush` multisite check, which
  does not belong in the offline-pure engine.

## 5. Architecture (Approach A)

The `site_post_dns` **data contract** requires its keys to exist *before* the phase fires,
because same-phase consumers (`check/cloudflare` cachecheck reads `fqdns_behind_cloudflare`)
and downstream `main()` code (`site_url` from `main_fqdn`; the favicon check reads
`fqdns_not_behind_cloudflare`) depend on them. Therefore **core produces the contract, then
fires the phase** — production is NEVER a `site_post_dns` hook.

```
main() per-site loop (core)
  ├─ terminus("domain:list") ──fatal/None──▶ log + continue (skip site)          [unchanged]
  │      │ ok: domains dict
  │      ▼
  ├─ facts = dns_classify.classify_domains(domains, cloudflare_enabled(), cf_v4_nets,
  │            cf_v6_nets, proxied_fqdns, fqdn_zone_conflicts, fqdn_re)
  │      │  per domain: skip platform → fqdn_re validate → resolve() A/AAAA
  │      │             → count CF-range vs elsewhere → transient? → classify
  │      ▼  DnsFacts(custom_domains, primary_domain, main_fqdn, not_in_dns,
  │                  fqdns_behind_cloudflare, fqdns_not_behind_cloudflare,
  │                  behind_cloudflare_not_proxied, proxied_in_multiple_zones, dns_transient)
  ├─ core stuffs site_context["domains"]=domains + every DnsFacts field  (contract keys)
  ├─ core emits domain-config notices from facts.custom_domains / facts.primary_domain
  │      (no-domains; no-primary-domain incl. its live drush multisite check)      [stays in core]
  ├─ sc.invoke_hooks("site_post_dns", site_context)
  │      ├─ check.cloudflare.cache        reads fqdns_behind_cloudflare            [existing]
  │      └─ check.dns.emit_dns_notices    reads the resolution-notice keys         [NEW]
  └─ core continues: site_url ← main_fqdn; favicon check ← fqdns_not_behind_cloudflare [unchanged]
```

**Why the engine returns `custom_domains`/`primary_domain`/`main_fqdn` too (DRY):** these are
computed in the *same* iterate→skip-platform→validate loop as the resolution lists. Computing
them a second time in core would duplicate that logic and risk divergence. The engine owns the
**data**; core owns the domain-config **notices** and `site_url`; the check owns the resolution
**notices**. "Resolution only" describes where the *notices* split, not where the pure list
computation lives.

## 6. Component interfaces (normative)

### 6.1 DNS engine — `dns_classify.py`

```python
def resolve(hostname: str, rrtype: str):
    """The one seam over dns.resolver.resolve. Tests monkeypatch dns_classify.resolve."""

def classify_hostname_dns(
    hostname: str,
    cloudflare_enabled: bool,
    cf_v4_nets: list,      # list[ipaddress._BaseNetwork]
    cf_v6_nets: list,
) -> (int, int, bool):     # (points_at_cloudflare, points_elsewhere, transient)
    ...

class DnsFacts(NamedTuple):
    custom_domains: list                 # list[str]
    primary_domain: list                 # list[str]  (matches current list-typed value)
    main_fqdn: str
    not_in_dns: list
    fqdns_behind_cloudflare: list
    fqdns_not_behind_cloudflare: list
    behind_cloudflare_not_proxied: list
    proxied_in_multiple_zones: list
    dns_transient: list

def classify_domains(
    domains,                             # the terminus domain:list result (dict, or non-dict)
    cloudflare_enabled: bool,
    cf_v4_nets: list,
    cf_v6_nets: list,
    proxied_fqdns,                       # membership-tested (dict keys or set)
    fqdn_zone_conflicts: dict,
    fqdn_re,                             # compiled regex
) -> DnsFacts:
    ...

def stuff_dns_contract(site_context, domains, facts: DnsFacts) -> None:
    """Pure mapping of `facts` -> the ten site_post_dns contract keys (plus raw `domains`).
    Extracted from main() so the value mapping is unit-testable; main() calls it just before
    invoke_hooks('site_post_dns')."""
    ...
```

- `stuff_dns_contract` MUST be covered by a unit test that constructs a `DnsFacts` with a
  **distinct sentinel value per field** and asserts each contract key received the correct field
  — this is the only guard against a value-swap mis-map (goldens run with empty DNS lists and
  would not catch one).

- `classify_hostname_dns` MUST drop the old `site_name` parameter and MUST NOT build any
  notice dict — presentation leaves the engine entirely.
- `classify_domains` MUST return an all-empty `DnsFacts` (empty lists, `main_fqdn=""`) when
  `domains` is not a `dict` — preserving the current `isinstance(domains, dict)` guard.
- The engine MAY print observability lines via `sc.console`/`sc.debug` (logging, not report
  notices). It MUST catch only the specific `dns.resolver` exceptions listed in §10 — NEVER a
  bare/catch-all `except`.

### 6.2 DNS check — `check/dns/`

- `check/dns/__init__.py` MUST register `emit_dns_notices` on `site_post_dns`
  **unconditionally** (no config gate — DNS checks are not disable-able).
- `check/dns/notices.py` holds **pure** builder functions (one per notice) that take
  primitives (`site_name`, hostname lists, `umich: bool`) and return a notice dict. Each
  returned notice MUST carry a `csv` key (several report paths read `n["csv"]`).
- `emit_dns_notices(site_context)` reads the contract keys, calls the builders, gates the
  Cloudflare trio on `sc.cloudflare_enabled()`, selects wording via `sc.umich_enabled()`, and
  adds each notice via `site_context.add_notice(...)`.

### 6.3 Core exposure

Add `sc.cloudflare_enabled = cloudflare_enabled` to the `sc.*` exposure block (checks cannot
import the dash-named script; this mirrors `sc.umich_enabled`).

## 7. Notice inventory (exhaustive) and gating

| `csv` code | Type | Trigger | Owner | Gate |
|---|---|---|---|---|
| `dns-lookup-failed` | warning | any transient (Timeout/NoNameservers) host | DNS check | none (universal) |
| `not-in-dns` | alert | host with 0/0 counts, not transient | DNS check | none (universal) |
| `not-behind-cloudflare` | warning | host with 0 CF addrs or any non-CF addr | DNS check | `cloudflare_enabled()`; U-M vs generic wording |
| `behind-cloudflare-not-proxied` | warning | host at CF but FQDN absent from proxied set | DNS check | `cloudflare_enabled()`; U-M vs generic wording |
| `proxied-in-multiple-zones` | warning | proxied FQDN in `fqdn_zone_conflicts` | DNS check | `cloudflare_enabled()` |
| `no-domains` | alert | `len(custom_domains) == 0` | **core** | none |
| `no-primary-domain` | info | `>1` custom domains, no primary, not `wordpress_network`, not Drupal multisite | **core** | none |

Notes:
- (a) **Gate is boolean-only.** The Cloudflare trio keys off `cloudflare_enabled()` — the
  feature existing, not a DNS-disable switch. There is NO new config key.
- (b) **Ordering.** `check.cloudflare` sorts before `check.dns` in `find_modules`, so the
  cachecheck hook runs before `emit_dns_notices`. `emit_dns_notices` emits **transient FIRST**,
  then not-behind-cloudflare → behind-cloudflare-not-proxied → proxied-in-multiple-zones →
  not-in-dns. Rationale: the renderer picks the email subject from the first notice after a type
  sort (`sorted_notices[0]["short"]`), so emitting the transient warning first keeps a
  warning-only site's subject as "DNS lookup failed (transient)", matching the pre-refactor loop
  (which added the transient notice first). `test_transient_emitted_before_cloudflare_warnings`
  pins the **in-hook** emission order (transient before the Cloudflare warnings); it does not
  assert the renderer's subject derivation or the cachecheck residual below. **Accepted residuals
  (Prime Directive #9)** — two narrow, non-golden-covered subject-line reorderings, both accepted
  by the maintainer:
  1. With an opt-in `[Cloudflare.cachecheck]` run enabled, that check's warnings are added by the
     earlier-running cachecheck hook and now precede the transient notice (they did not
     pre-refactor). Affects only a warnings-only site whose DNS also failed transiently *while the
     cache check is enabled*.
  2. The `not-in-dns` **alert** now fires inside `invoke_hooks` (before the `wordpress_network`
     `network_home_url` block that can add a "fix WP CLI error" alert), whereas pre-refactor it
     was added after it. Affects only a `wordpress_network` site whose `network_home_url` fetch
     fails **and** which has a not-in-DNS domain — the two alerts swap, changing the subject.
     (Neither test site is a network site, so no golden is affected.)
- (c) **Transient aggregation (cleanup).** Today the transient notice is emitted per host (N
  notices). It MUST become ONE `dns-lookup-failed` notice per site listing all transient FQDNs,
  matching every other aggregated DNS notice. Golden-safe (no transient hosts in fixtures).

## 8. Bug fixes (both confirmed by reading `pantheon-sitehealth-emails`)

- **Bug #1 — suppressed notices.** `behind-cloudflare-not-proxied` and
  `proxied-in-multiple-zones` are currently emitted **inside** `if
  len(fqdns_not_behind_cloudflare) > 0:` (core lines ~1948/1976/2008), so a site whose domains
  are *all* correctly behind Cloudflare never sees a "not proxied" or "multiple zones" warning.
  Fix: in the DNS check each of the three Cloudflare notices MUST be emitted from its own
  independent `if <list>:` guard.
- **Bug #2 — wrong plaintext list.** The `behind-cloudflare-not-proxied` **plaintext** body
  iterates `fqdns_not_behind_cloudflare` (core line ~2002) while its HTML body correctly uses
  `behind_cloudflare_not_proxied`. Fix: the plaintext MUST list `behind_cloudflare_not_proxied`.

The e2e goldens keep `[Cloudflare].enabled = false`, so neither fix alters a golden; both change
real U-M-run behavior for the better.

## 9. U-M vs generic wording

The Cloudflare notices currently hardcode U-M URLs (`its.umich.edu/...`,
`documentation.its.umich.edu/node/4237`). The builders MUST take a `umich: bool` and, when
false, produce generic, actionable copy ("put these domains behind Cloudflare" / "turn on
proxying") with NO U-M links. Same pattern as `check/cloudflare/notices.py` (`umich=` flag).
`emit_dns_notices` passes `umich=sc.umich_enabled()`.

## 10. Error handling & shadow paths (Prime Directive #3)

| Path | Behavior |
|---|---|
| **nil** — `terminus` fatal or `domains is None` | core logs + `continue` (skips site); engine not called. Unchanged. |
| **empty** — platform-only / no custom domains | engine → all-empty `DnsFacts`; no resolution notices; core's `no-domains` fires; contract keys present as `[]`/`""`. |
| **malformed** — `domains` not a dict | engine → all-empty `DnsFacts` (isinstance guard preserved). |
| **transient** — Timeout/NoNameservers | host excluded from `not_in_dns` AND from Cloudflare classification (P4); one aggregated `dns-lookup-failed` warning. |
| **definitive** — NXDOMAIN/NoAnswer, 0/0 counts | host → `not_in_dns`. |

**Named exceptions.** No new exception classes. The engine catches exactly
`dns.resolver.NoAnswer`, `dns.resolver.NXDOMAIN`, `dns.resolver.NoNameservers`,
`dns.resolver.Timeout` (as today). Any other resolver exception propagates (fail loud) —
unchanged behavior. NEVER add a catch-all to mask it.

## 11. Observability

`classify_hostname_dns` keeps the per-address console lines (green CF IP / red elsewhere);
`classify_domains` keeps the `ATTENTION: … not in DNS / not behind Cloudflare / not proxied /
multiple zones` console lines, via `sc.console`/`sc.debug` at existing verbosity. Console output
is not captured by goldens, so this is behavior-neutral for tests.

- **Accepted observability delta (invalid domain):** the engine's invalid-domain log becomes
  `ERROR: Invalid domain: {hostname}` (no site name), because the engine intentionally takes no
  `site_name` (it is pure). The bad hostname still uniquely identifies the domain, and the
  per-site loop already prints which site it is processing, so the line stays contextualized.
- **Injection hardening:** that log MUST pass the (un-`fqdn_re`-validated) hostname through
  `rich.markup.escape` before interpolation — a bracket sequence in an arbitrary domain id would
  otherwise be parsed as rich markup. Matches the `rich_escape` convention already used in
  `check/cloudflare/cache.py`. This is console-only; email-facing hostnames are separately
  `html.escape`'d + `sc.escape_url`'d in the notice builders (§6.2).

## 12. Config

No new config. DNS checks have no enable flag. The Cloudflare trio keys off the existing:

```toml
[Cloudflare]
enabled = true      # false (or section absent) ⇒ the three Cloudflare-DNS notices never emit
```

## 13. Testing strategy (tests follow the change)

**NEVER-block (tests are load-bearing):** the offline e2e goldens are the primary regression
guard. They MUST remain byte-identical (Cloudflare disabled + platform-only fixture domains ⇒
zero DNS-resolution notices). Regenerating a golden requires a reviewed diff and an explicit
reason; a green run after `--update-goldens` is NOT self-justifying.

| Tier | File | Covers |
|---|---|---|
| unit | `tests/unit/test_dns_classify.py` | `classify_hostname_dns` (ported from `test_dns.py`, new seam/signature); `classify_domains` multi-domain; platform/invalid-fqdn skip; **bug #1 regression** (fully-proxied + zone conflict → `proxied_in_multiple_zones` populated with empty `fqdns_not_behind_cloudflare`); non-dict → empty; Hypothesis: transient host never in `not_in_dns`; **`stuff_dns_contract` value-swap guard** (distinct sentinel per `DnsFacts` field → each contract key gets the correct field). |
| unit | `tests/unit/test_dns_notices.py` | pure builders: wording, csv keys, U-M vs generic, **bug #2 regression** (not-proxied plaintext lists `behind_cloudflare_not_proxied`). |
| integration | `tests/integration/test_check_dns.py` | unconditional `site_post_dns` registration (probe-load pattern from `test_check_cloudflare_init.py`); `emit_dns_notices` adds the right notices from a populated `SiteContext`; `cloudflare_enabled()` gating (trio absent when disabled); transient aggregation asserted as **exactly one** `dns-lookup-failed` notice. |
| render (snapshot) | `tests/integration/test_dns_notice_render.py` | syrupy snapshots of every builder's returned **notice dict** (which carries the `message` HTML + `text` plaintext), U-M and generic variants — the human-checked guard on the moved copy, since these notices never appear in the e2e goldens. NOTE: this snapshots the builder output, not a full `email_template.html` Jinja render (unlike `test_cachecheck_notice_render.py`). Refresh with `--update-goldens` (reviewed `.ambr` diff). A separate unit assertion (`test_dns_notices.py`) proves hostnames are `html.escape`'d in the display text. |
| e2e | existing goldens via `./run-tests` | byte-identical (the NEVER-block). |

Retire `tests/integration/test_dns.py` (its cases move to `tests/unit/test_dns_classify.py`).

## 14. Docs

Update `CLAUDE.md`: add `check.dns` to the `find_modules` inventory and the `check/`
description; note DNS-resolution notices now live in `check/dns` while `no-domains`/
`no-primary-domain` remain in core; note the `dns_classify.py` engine + `sc.cloudflare_enabled`
exposure. The `site_post_dns` data-contract table is unchanged (same keys, same guarantees).

## 15. Acceptance criteria

Run and paste actual output (never summarize):

1. `./run-tests --fast` — all offline tiers pass; goldens unchanged.
2. `./run-tests` — full suite (incl. render) passes.
3. `git grep -n "classify_hostname_dns" pantheon-sitehealth-emails` — no matches (moved out).
4. `git grep -n "import dns" pantheon-sitehealth-emails` — no match if the core no longer uses
   `dns.resolver` (verify and remove the now-unused import).

## 16. Post-implementation audit questions

- Did any golden change? If so, why, and is the diff reviewed and justified?
- Are all five resolution notices reachable independently (bug #1)?
- Does a non-U-M config (`minimal-nonumich.toml`) produce generic wording with no `umich.edu`
  links in the DNS notices?
- Is `dns_classify.py` free of any import of the dash-named core script?
