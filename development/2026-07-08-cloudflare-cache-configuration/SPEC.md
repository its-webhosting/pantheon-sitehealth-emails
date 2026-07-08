# SPEC: Cloudflare cache-configuration check + named-phase hook system

Status: draft for adversarial review → user approval → implementation.
Source: `PROMPT.md` (this directory) + interview decisions (2026-07-08, all binding) +
approved plan (`~/.claude/plans/development-2026-07-08-cloudflare-cache-optimized-cocke.md`).
Audience: Claude Code (implementer) and humans (record of what was decided and why).
This file is a record, not primary documentation — the code, CLAUDE.md, and `docs/` are.

---

## 1. Goals

1. **Part A (prerequisite)**: generalize the hardcoded `setup`/`check` hook pair into an
   ordered list of named phases with a **documented per-phase data contract** — the seam every
   future check relocation codes against.
2. **Part B**: new `check/cloudflare/` package that (a) verifies once per run that the
   program's egress IP is on an institutional Cloudflare allowlist, and (b) per site, probes
   each proxied FQDN's pages/assets over HTTP and reports cache-configuration problems as
   actionable "Cloudflare caching" notices.
3. **Part C (accepted expansion)**: recursive `gate_disabled_sections()`.
4. **Accepted expansion**: relocate the existing umich fqdns-gated WP/Drush checks into
   `check/umich/` at the new `site_post_gather` phase.
5. **Docs deliverables**: end-user doc, config samples, CLAUDE.md/README updates, and U-M
   documentation suggestions incl. a drafted new page (§13).

### NOT in scope (decided, written down per prime directive 7)

- Persisting cache-check results to the DB (revisit when a consumer exists; the per-run
  notices CSV is the record).
- A diagnostic-only CLI mode (fast single-site cache check) — `--only-warn SITE` remains the
  diagnosis path; noted as future work.
- An http→https redirect probe — belongs to the future Cloudflare/security-scoring work.
- Any MISS→HIT verification beyond the §8.6 retry protocol.
- Asset discovery beyond `script[src]`, `link[rel=stylesheet][href]`, `img[src]` (no `srcset`,
  `<source>`, `<video poster>`, CSS `url()` — PROMPT's "including but not limited to"
  deliberately narrowed; extend later if owners report gaps).
- Moving the large date-driven annual-billing notices / user-agent checks / template branding
  (still deferred per CLAUDE.md; `site_post_gather` is now their documented future home).

---

## 2. Binding decisions (from the interview)

| # | Decision |
|---|---|
| D1 | Clean rename `check`→`site_pre`; no alias; unknown bare phase name = loud fatal error. |
| D2 | `site_post_dns` fires immediately after `custom_domains`/`primary_domain` are computed, BEFORE site_url/WP-network detection and the existing DNS notice blocks. |
| D3 | `[Cloudflare.cachecheck].enabled` defaults **false** (opt-in). Missing `account_id`/`list_name` while enabled → fatal. |
| D4 | Egress check verifies **both IP families**; a family with no connectivity is skipped (console note); fatal if no family yields an IP or any obtained IP is off-list. |
| D5 | Redirects: per-URL chain, max 5 same-FQDN hops. |
| D6 | RNG seeded `random.Random(f"{site_name}:{report_date_iso}")` — reproducible reruns, monthly rotation. |
| D7 | Full GET bodies; no size caps. |
| D8 | Tests: integration tier via ONE monkeypatchable HTTP seam + syrupy snapshot of notice HTML through the real template path; NO new golden. (The PROMPT's single-seam rule applies to the per-site cache battery — `httpseam.fetch` — plus its `httpseam.sleep` timer seam; the egress check has its own `egress.probe` seam because its probes need family-forcing transports.) |
| D9 | MISS-retry: only when headers otherwise cacheable; sleep 2s → refetch → still MISS → sleep 2s → third fetch → still MISS → `miss-persistent` item. EXPIRED/STALE/REVALIDATED/UPDATING/HIT never retry. |
| D10 | Relocate umich fqdns-gated WP/Drush checks to `check/umich/cloudflare_cms.py` at `site_post_gather`. |
| D11 | `gate_disabled_sections` becomes recursive. |
| D12 | U-M doc deliverables: anchor/edit suggestions + full draft of a new "Understanding your Cloudflare cache report" page (§13). |
| D13 | Exhausting the 5-hop same-FQDN redirect budget produces a `too-many-redirects` result item (interpretation: PROMPT's "everything else → console note, no item" covers cross-FQDN targets only; a 6th same-FQDN redirect is a probable loop worth reporting). |
| D14 | `site_pre` stays at the current seam (:1598, after the traffic gather and the `--update`/`--import-older-metrics` continues) — rename-only, zero behavior change. The phase is documented honestly as "first per-site seam, adjacent to site_post_traffic", NOT "right after SiteContext creation" (PROMPT's sketch was aspirational; moving it would make SiteLens run on data-refresh paths). |
| D15 | U-M notice variants use CMS-appropriate links where relevant: `site_context["site"]["framework"]` is available from the start of the per-site loop, so `notices.py` takes a `framework` parameter and links node/5114 (WordPress) / node/4242 (Drupal) on framework-relevant items, CMS-neutral pages otherwise. |

## 3. Verified facts (implementer: trust these; re-verify only the two flagged ⚠ items)

- Hook system `script_context.py:34-65`; the only invocations are `sc.invoke_hooks("setup")`
  (main script :1236) and `sc.invoke_hooks("check", site_context)` (:1598); dotted event
  `'setup.umich.portal'` invoked from `plugin/umich/portal.py:55`.
- **`--create-tables` runs setup hooks** (its exit :1271-1273 is after :1236).
- `--update` `continue`s at :1575-1577, `--import-older-metrics` at :1573 (both before :1598);
  `--only-warn` `continue`s at :2991 after all checks. Consequences: site phases through
  `site_post_gather` run on full-report and `--only-warn` paths only; `site_pre_render` runs on
  the full-report path only.
- DNS locals init :1619-1625; `custom_domains` :1695; `primary_domain` :1698; existing DNS
  notice blocks :1806-1918. No `dns_transient` list exists yet (transient flag used inline).
- Relocation extents: WP block :1993-2003 (`umich_enabled() and len(fqdns_behind_cloudflare) > 0`,
  uses `plugins`); Drupal 4× `check_drupal_module` :2338-2379, same guard, in the `else:` of
  `if drupal_version.startswith("7."):` (:2303).
- Cloudflare SDK 5.4.0: `client.rules.lists.list(account_id=…)`,
  `client.rules.lists.items.list(account_id=…, list_id=…)` (auto-paginating iterators).
- `gate_disabled_sections` :861-876, top-level only, `enabled is False` identity semantics.
- httpx 0.28.1 present only transitively; beautifulsoup4 absent; `cloudflare` extra is
  `["cloudflare"]`.
- `escape_url` :253-254; house link pattern `f'<a href="{escape_url(u)}">{html.escape(t)}</a>'`.
- Only `run_terminus` uses `sc.console.status` (:269) — no rich Live-nesting conflict at the
  `site_post_dns` call site.
- Tests hardcoding hook names: `tests/conftest.py:119`, `tests/integration/test_terminus_seam.py:52-56`,
  `tests/integration/test_regressions.py:64`; `test_plugin_umich_portal.py:73` uses the dotted
  event (stays valid).
- U-M doc anchors: node/5114 none; node/4242 `#useragent` only; node/4241 none; node/5110 ids
  `rule 1`…`rule 4` (must be encoded `#rule%201`…).
- ⚠ Line numbers drift as edits land — re-locate anchors by the quoted code, not the number.
- ⚠ Generic-variant external doc URLs in §12 must be spot-checked (WebFetch) during
  implementation; do NOT add code that fetches them at runtime (PROMPT: never fetch docs).

---

## 4. Architecture overview

```
                 ┌──────────────────────── one run ────────────────────────┐
 config parse → gate_disabled_sections → plugin import (gated self-registration)
   → process_config pass 1 → check import (gated self-registration)
   → invoke_hooks("setup") ───────────────────────────────────── egress-IP check (B1)
   → deferred substitution pass → DB connect → [--create-tables exits here — AFTER setup]
   → per-site loop:
        skips (portal / not requested / Sandbox) → SiteContext created
        plan validation → env:list → traffic gather + DB merge
        [--import-older-metrics continue] [--update continue]
        traffic window query
        ── site_pre ───────────────── (old 'check' seam, D14: sitelens etc.;
        ── site_post_traffic ───────   adjacent — site_pre guarantees no keys)
        domain:list → domain loop (DNS classification, proxied membership)
        custom_domains / primary_domain computed
        ── site_post_dns ─────────── cache-configuration check (B2)
        site_url / WP-network detection, DNS notice blocks, WP/Drush gather
        ── site_post_gather ──────── umich cloudflare CMS checks (relocated, D10)
        [--only-warn continue]
        traffic aggregation → chart → plan recommendation
        ── site_pre_render ────────── (no consumer yet; seam for the future)
        template render → inline CSS → .eml → [SMTP send]
```

Per-FQDN cache-check flow (B2):

```
 for fqdn in sorted(fqdns_behind_cloudflare):
     GET https://{fqdn}/  ──error?──▶ transport item, next fqdn's URL list continues
        │ok
        battery(main page, is_main_page=True) ──▶ items
        extract links → filter → dedupe → sort → rng pick ≤3
        for page in [main] + picks:
            (picks fetched + battery'd; main already done)
            extract assets(page html) → rng pick ≤1 js, ≤1 css, ≤1 img
            for asset in picks: GET → battery(asset) ──▶ items
     items grouped per fqdn ──▶ consolidation (§9) ──▶ 1 notice per signature group
```

Redirect decision (per fetch, manual loop):

```
 response 3xx?
   ├─ no → return response
   ├─ Location same-URL http→https upgrade → follow
   ├─ Location same-FQDN (any path)        → follow (max 5 hops total)
   ├─ hops exhausted                       → error='too_many_redirects' → result item
   └─ Location other-FQDN (incl apex↔www)  → error='cross_fqdn_redirect'
                                              → console note, drop URL, NO item
```

MISS-retry state machine (D9):

```
 battery ran, Cf-Cache-Status == MISS, should_retry_miss()?
   ├─ no  → done (no retry, no item)
   └─ yes → sleep(2) → refetch → status != MISS → done (cache warmed; no item)
                        └─ MISS → sleep(2) → refetch → status != MISS → done
                                              └─ MISS → item: miss-persistent
```

---

## 5. Part C — recursive `gate_disabled_sections()`

File: `pantheon-sitehealth-emails` (:861-876).

```python
def gate_disabled_sections(config: dict) -> dict:
    """(update docstring) Applies recursively: any table at any depth whose `enabled`
    is the boolean False is reduced to {'enabled': False} before substitution resolution,
    so a disabled feature (or sub-feature like [Cloudflare.cachecheck]) never forces its
    <{secret ...}> values to exist. A disabled parent drops its nested tables entirely.
    `enabled` keys that are missing, True, or non-boolean (e.g. the string "false") leave
    the table untouched (identity check: `is False`)."""
    for name, value in list(config.items()):
        if isinstance(value, dict):
            if value.get("enabled") is False:
                sc.debug(f"Section [{name}] is disabled; keeping only 'enabled', dropping other keys")
                config[name] = {"enabled": False}
            else:
                gate_disabled_sections(value)
    return config
```

Shadow paths: empty dict (no-op), non-dict values at depth (skipped by isinstance),
disabled parent containing enabled child (child dropped with parent's keys — parent wins).

Tests → `tests/unit/test_section_gating.py` (extend): nested `enabled=false` sub-table reduced;
sub-table under a disabled parent removed entirely; nested `enabled=true` untouched while its
own nested disabled grandchild is gated; string `"false"` at depth untouched; existing top-level
cases unchanged.

---

## 6. Part A — named ordered phases

### 6.1 `script_context.py`

Replace :34-37 and :53-65 with:

```python
# Ordered lifecycle phases. 'setup' runs once per run (NOTE: including --create-tables,
# which exits later); the site_* phases run once per processed site, in this order, each
# receiving the SiteContext — but a per-site fatal error (e.g. the domain:list failure
# `continue` at :1611-1615) skips that site's remaining phases; hooks must not assume a
# later phase always follows an earlier one. Phases through site_post_gather run on full-report and
# --only-warn paths; site_pre_render only on the full-report path; --update and
# --import-older-metrics never reach any site_* phase. Dotted names (e.g.
# 'setup.umich.portal') are plugin-defined events: allowed, not ordered here.
# The per-phase site_context data contract lives in CLAUDE.md ("Per-site report pipeline").
PHASES = (
    'setup',
    'site_pre',            # first per-site seam (rename of the old 'check' seam; fires
                           # after the traffic gather, just before site_post_traffic —
                           # no per-phase keys guaranteed; see D14)
    'site_post_traffic',
    'site_post_dns',
    'site_post_gather',
    'site_pre_render',
)

hooks = {phase: [] for phase in PHASES}


def _valid_hook_name(hook_name: str) -> bool:
    return hook_name in PHASES or '.' in hook_name


def add_hook(hook_name: str, target: dict) -> None:
    if not _valid_hook_name(hook_name):
        console.print(f'[bold red]ERROR: add_hook: unknown phase "{hook_name}" '
                      f'(known phases: {", ".join(PHASES)}; dotted names are plugin events)')
        sys.exit(1)
    hooks.setdefault(hook_name, []).append(target)


def invoke_hooks(hook_name: str, *args, **kwargs) -> None:
    if not _valid_hook_name(hook_name):
        console.print(f'[bold red]ERROR: invoke_hooks: unknown phase "{hook_name}"')
        sys.exit(1)
    debug(f'[bold magenta]=== Calling hooks for {hook_name}:')
    for hook in hooks.get(hook_name, []):
        debug(f'Invoking {hook_name} hook target {hook["name"]}')
        hook['func'](*args, **kwargs)
```

Named errors: unknown bare phase in `add_hook`/`invoke_hooks` → red console error +
`sys.exit(1)` (house style; matches `SiteContext.add_notice`'s missing-message handling).
Empty valid phase → silent no-op (contract, tested). Within-phase ordering: `find_modules`
sorts module paths; registration order = import order; lists preserve insertion order.

### 6.2 Main-script changes

All site-phase hooks receive exactly `(site_context)`. Insertion points (anchors quoted from
current code; re-locate by content):

1. `:1598` → `sc.invoke_hooks("site_pre", site_context)` (rename only).
2. Immediately after, stuff + invoke:
   ```python
   site_context["traffic_rows"] = results
   site_context["start_date"] = start_date
   site_context["end_date"] = end_date
   sc.invoke_hooks("site_post_traffic", site_context)
   ```
3. In the domain-loop init (:1619-1625) add `dns_transient = []`; in the loop, append
   `hostname` whenever `classify_hostname_dns` returns `transient=True`.
4. Immediately AFTER the `if isinstance(domains, dict):` block that ends with the
   `len(custom_domains) == 0` notice (i.e. dedented to loop level, right after the block
   closes ~:1712) — NOT inside it, so the phase fires once per processed site even on
   malformed domain data (refines D2: the essence — domain data ready, before WP-network
   detection and the :1806+ DNS notice blocks — holds; the "before the no-domains notice"
   detail is dropped because that notice lives inside the block, and it is irrelevant in
   practice: no custom domains ⇒ no proxied FQDNs ⇒ the cache check adds nothing):
   ```python
   site_context["domains"] = domains
   site_context["custom_domains"] = custom_domains
   site_context["primary_domain"] = primary_domain
   site_context["main_fqdn"] = main_fqdn
   site_context["fqdns_behind_cloudflare"] = fqdns_behind_cloudflare
   site_context["fqdns_not_behind_cloudflare"] = fqdns_not_behind_cloudflare
   site_context["not_in_dns"] = not_in_dns
   site_context["behind_cloudflare_not_proxied"] = behind_cloudflare_not_proxied
   site_context["proxied_in_multiple_zones"] = proxied_in_multiple_zones
   site_context["dns_transient"] = dns_transient
   sc.invoke_hooks("site_post_dns", site_context)
   ```
   ⚠ `custom_domains`/`primary_domain` are assigned inside the `isinstance` block —
   initialize both to `[]` alongside :1619-1625 so the contract keys always exist (with the
   dedented invoke above, every processed site gets the phase with `[]` defaults when domain
   data is malformed).
5. Initialize `plugins = None`, `mods = None`, `wordpress_version = None`,
   `drupal_version = None` immediately before the framework if/elif chain (~:1920). After the
   chain ends (~:2610, before the `--only-warn` continue at :2991 — verify exact end):
   ```python
   site_context["framework"] = site["framework"]
   site_context["site_url"] = site_url
   site_context["wordpress_version"] = wordpress_version
   site_context["wordpress_plugins"] = plugins if isinstance(plugins, list) else None
   site_context["drupal_version"] = drupal_version
   site_context["drupal_modules"] = mods if isinstance(mods, list) else None
   sc.invoke_hooks("site_post_gather", site_context)
   ```
6. Immediately before `template_dict = dict(` (~:3920):
   `sc.invoke_hooks("site_pre_render", site_context)`.
7. Helper exposure (after the defs of `check_wordpress_plugin` / `check_drupal_module` /
   `escape_url`, top level):
   ```python
   # Expose for check/ packages, which cannot import this dash-named script.
   # Same convention as sc.plugin_context['plugin.cloudflare']['get_client'].
   sc.escape_url = escape_url
   sc.check_wordpress_plugin = check_wordpress_plugin
   sc.check_drupal_module = check_drupal_module
   sc.umich_enabled = umich_enabled
   ```
   (`sc.umich_enabled` replaces the earlier idea of a private `_umich_enabled()` copy in
   `cache.py` — one definition, monkeypatchable in standalone-module tests like the others.)

### 6.3 Normative data contract (goes into CLAUDE.md verbatim)

| Phase | Guaranteed new site_context keys (beyond `site`, `notices`, `sections`, `attachments`) |
|---|---|
| `site_pre` | — |
| `site_post_traffic` | `traffic_rows` (PantheonTraffic rows), `start_date`, `end_date` (date) |
| `site_post_dns` | `domains` (raw terminus dict), `custom_domains`, `primary_domain`, `main_fqdn` (str, may be `""`), `fqdns_behind_cloudflare`, `fqdns_not_behind_cloudflare`, `not_in_dns`, `behind_cloudflare_not_proxied`, `proxied_in_multiple_zones`, `dns_transient` (all `list[str]`; classification lists are `[]` when `[Cloudflare]` disabled or DNS transient) |
| `site_post_gather` | `framework` (str), `site_url` (str, may be `""`), `wordpress_version` (str\|None), `wordpress_plugins` (list\|None), `drupal_version` (str\|None), `drupal_modules` (list\|None) — None means "not that framework or the gather failed" |
| `site_pre_render` | everything above (full-report path only) |

### 6.4 Rename fallout (D1)

- `check/umich/__init__.py`: 2× `add_hook('check', …)` → `'site_pre'`.
- `tests/conftest.py:119`: `sc.hooks = {phase: [] for phase in sc.PHASES}`.
- `tests/integration/test_terminus_seam.py:52-56`: `"check"` → `"site_pre"`, rename test to
  `test_site_pre_hook_runs_against_a_site_context`.
- `tests/integration/test_regressions.py:64`: `sc.hooks["check"]` → `sc.hooks["site_pre"]`.
- `test_plugin_umich_portal.py:73`: unchanged (dotted event).
- Final `grep -rnE "['\"]check['\"]" pantheon-sitehealth-emails script_context.py plugin/ check/ tests/`
  for stragglers (both quote styles — conftest itself uses double quotes).

---

## 7. Relocation — `check/umich/cloudflare_cms.py` (D10)

```python
import script_context as sc

DOC_WP = "https://documentation.its.umich.edu/node/5114"
DOC_DRUPAL = "https://documentation.its.umich.edu/node/4242"


def check_cloudflare_cms_integrations(site_context) -> None:
    """site_post_gather hook: recommend the U-M Cloudflare CMS integrations on sites that
    have FQDNs proxied behind Cloudflare. Relocated from the main script (was inline in the
    WP/Drush gather); the umich_enabled() gate is implied by the check.umich package gate."""
    site = site_context["site"]["name"]
    if not site_context.get("fqdns_behind_cloudflare"):
        return
    framework = site_context.get("framework") or ""
    if framework.startswith("wordpress"):
        plugins = site_context.get("wordpress_plugins")
        if plugins is None:
            return  # wp failure already produced its own alert notice in the gather
        site_context.add_notices(sc.check_wordpress_plugin(
            site, plugins, "umich-cloudflare",
            "University of Michigan: Cloudflare Cache", DOC_WP,
            "Needed for automatically clearing Cloudflare's caches when content is updated.",
        ))
    elif framework.startswith("drupal"):
        mods = site_context.get("drupal_modules")
        drupal_version = site_context.get("drupal_version") or ""
        if mods is None or drupal_version.startswith("7."):
            return  # drush failure already noticed; D7ES sites keep their own module set
        for slug, title, description, kwargs in (
            ("cloudflare", "CloudFlare",
             "Necessary for automatically clearing Cloudflare's caches when content is updated.", {}),
            ("cloudflarepurger", "CloudFlare Purger",
             "Necessary for automatically clearing Cloudflare's caches when content is updated.", {}),
            ("purge_processor_lateruntime", "Late runtime processor (purge_processor_lateruntime)",
             "Necessary for automatically clearing Cloudflare's caches when content is updated.", {}),
            ("purge_processor_cron", "Purge Cron Processor (purge_processor_cron)",
             "Recommended as a fallback for clearing Cloudflare's caches when content is updated.",
             {"level": "info"}),
        ):
            site_context.add_notices(sc.check_drupal_module(
                site, mods, slug, title, DOC_DRUPAL, description, **kwargs))
```

⚠ Copy titles/descriptions byte-for-byte from :1993-2003 and :2338-2379 (including the
"CloudFlare" capital F), then DELETE those blocks. Registration in `check/umich/__init__.py`
inside the existing UMich gate:

```python
from .cloudflare_cms import check_cloudflare_cms_integrations
sc.add_hook('site_post_gather', {
    'name': 'check.umich.cloudflare_cms.check_cloudflare_cms_integrations',
    'func': check_cloudflare_cms_integrations})
```

Behavior notes (accepted): these notices now append after all mainline gather notices for
U-M+Cloudflare runs; goldens unaffected (Cloudflare disabled ⇒ `fqdns_behind_cloudflare == []`
⇒ blocks were already no-ops).

---

## 8. Part B — `check/cloudflare/` package

### 8.1 Layout & registration

```
check/cloudflare/
  __init__.py   gate + import guard + config validation + hook registration
  cfg.py        config accessor + defaults + validation
  httpseam.py   FetchResult + fetch()/sleep seams + redirect loop
  headers.py    PURE per-URL header battery
  pages.py      PURE link/asset extraction + selection + classify_redirect
  notices.py    PURE item→language (U-M/generic) + consolidation + notice build
  egress.py     setup-phase egress-IP allowlist check
  cache.py      site_post_dns orchestration + console output
```

`__init__.py` (find_modules imports it unconditionally; all gating inside):

```python
import sys
import script_context as sc

_cf = sc.config.get('Cloudflare', {})
_cachecheck = _cf.get('cachecheck', {})
if _cf.get('enabled') and isinstance(_cachecheck, dict) and _cachecheck.get('enabled'):
    try:
        from .egress import check_egress_ip
        from .cache import check_cloudflare_cache
    except ImportError as e:
        sc.console.print(
            f"[bold red]ERROR: [Cloudflare.cachecheck] is enabled but the Python package "
            f"'{e.name}' is not installed.  Install this check's dependencies with:\n"
            f"    uv pip install .[cloudflare]")
        sys.exit(1)
    from .cfg import validate_cachecheck_config
    validate_cachecheck_config()
    sc.add_hook('setup', {'name': 'check.cloudflare.egress.check_egress_ip',
                          'func': check_egress_ip})
    sc.add_hook('site_post_dns', {'name': 'check.cloudflare.cache.check_cloudflare_cache',
                                  'func': check_cloudflare_cache})
else:
    sc.console.print('[bold yellow] Skipping check.cloudflare because [Cloudflare] and/or [Cloudflare.cachecheck] is not enabled')
```

Notes: startup order is gate_disabled_sections (:1189) → plugin import (:1192) →
process_config pass 1 (:1198) → **check import (:1201)** → setup hooks (:1236) → deferred
substitution pass (:1239). So at this package's import time, pass-1 substitutions are already
resolved; only DEFERRED substitutions (today: `plugin.umich`'s) are still markers. Therefore
**`[Cloudflare.cachecheck]` values must be pass-1-resolvable** — the same invariant as the
Cloudflare creds (the egress setup hook at :1236 runs before the deferred pass); documented in
`docs/cloudflare-cachecheck.md`. The gate reads only booleans; `validate_cachecheck_config`
checks key **presence** only. Part C guarantees a disabled `cachecheck` arrives as
`{'enabled': False}`.

### 8.2 `cfg.py`

```python
DEFAULTS = {
    "user_agent": "pantheon-sitehealth-emails (Linux; UMich WWS 0.1) webmaster@umich.edu",
    "timeout": 5,           # seconds, per HTTP request
    "report_doc_url": "https://documentation.its.umich.edu/cloudflare-cache-report",
}
REQUIRED = ("account_id", "list_name")

def cachecheck_config() -> dict     # DEFAULTS | sc.config['Cloudflare']['cachecheck']
def validate_cachecheck_config() -> None
    # sys.exit(f"ERROR: [Cloudflare.cachecheck] is enabled but missing required setting(s): "
    #          f"{', '.join(missing)}") when any REQUIRED key is absent
```

`report_doc_url` is the (future) U-M "Understanding your Cloudflare cache report" page; the
config override makes publishing it a one-line toml edit. Default is a placeholder the user
will create (§13.1); acceptable because it is U-M's own namespace and U-M controls it.

Config samples — `sample-pantheon-sitehealth-emails.toml` (documented, all commented except
`enabled=false`) and the private live config (real U-M values, `enabled=true` when rolling out):

```toml
[Cloudflare.cachecheck]
# Per-site Cloudflare cache-configuration checks (see docs/cloudflare-cachecheck.md).
enabled = false
# Cloudflare account whose IP list authorizes this program's egress address:
#account_id = "b6a4063d6fa89fba31cf8bf99540d7e5"   # U-M example
#list_name = "um_networks"
# Sent on every request to sites so owners can identify us in their logs:
#user_agent = "pantheon-sitehealth-emails (Linux; UMich WWS 0.1) webmaster@umich.edu"
#timeout = 5
#report_doc_url = "https://documentation.its.umich.edu/..."
```

### 8.3 CLI flag

`build_arg_parser()` next to `--only-warn` (:194-199):

```python
args_parser.add_argument(
    "--allow-any-source-ip", action="store_true", default=False,
    help="skip the Cloudflare egress-IP allowlist check that normally runs before site cache checks",
)
```

### 8.4 Dependencies

`pyproject.toml`: `cloudflare = ["cloudflare", "httpx", "beautifulsoup4"]`; add `"httpx"` and
`"beautifulsoup4"` to the `test` extra (integration tests parse canned HTML with real bs4).
README setup line already says `.[mysql,aws,cloudflare]` — note the new transitive-made-direct
deps there.

### 8.5 `httpseam.py` — the single HTTP seam

```python
import dataclasses, time
import httpx
import script_context as sc
from .pages import classify_redirect

MAX_REDIRECTS = 5

@dataclasses.dataclass
class FetchResult:
    url: str                    # originally requested URL
    final_url: str              # after followed redirects
    status_code: int | None     # None on transport failure
    headers: dict               # lowercased keys; 'set-cookie' -> list[str]
    text: str
    error: str | None           # None | 'timeout' | 'cert' | 'challenge' | 'connection'
                                #      | 'cross_fqdn_redirect' | 'too_many_redirects'
    redirect_chain: list        # URLs followed
    insecure: bool = False      # result came from the verify=False retry

def _fetch(url: str, *, fqdn: str, timeout: float, user_agent: str,
           verify: bool = True) -> FetchResult: ...

fetch = _fetch          # THE monkeypatch seam (tests replace check module attr)
sleep = time.sleep      # seam for the MISS-retry pauses
```

Implementation requirements:
- Fresh `httpx.Client(follow_redirects=False, verify=verify, timeout=timeout,
  headers={"user-agent": user_agent}, trust_env=False)` per fetch — no cookies ever sent
  (no cookie jar reuse), no env proxies.
- Manual redirect loop: on 3xx with `Location`, resolve relative Locations against the current
  URL; `classify_redirect(current, location, fqdn)`; `'follow'` up to `MAX_REDIRECTS` hops
  (D5), then `error='too_many_redirects'` (D13); `'cross'` → `error='cross_fqdn_redirect'`
  (§8.8: console note, drop URL, NO item — PROMPT rule). A 3xx WITHOUT a `Location` header is
  treated as the final response (the battery's `http-error` rule then fires on the 3xx status).
- The `cf-mitigated: challenge` header (case-insensitive value match) is checked on EVERY
  response, including each redirect hop, regardless of status code (PROMPT); it short-circuits
  the chain → `error='challenge'` (battery skipped; single result item).
- Exception mapping (named, per prime directive 2): `httpx.TimeoutException` → `'timeout'`;
  `httpx.ConnectError` whose `__cause__`/message indicates TLS/SSL certificate verification →
  `'cert'`; any other `httpx.TransportError`/`httpx.HTTPError` → `'connection'`. No bare
  `except Exception` — let non-httpx bugs crash loudly.
- Headers dict: keys lowercased; multi-value `Set-Cookie` preserved as a list under
  `'set-cookie'`.
- Full body read (D7).

### 8.6 `headers.py` — pure battery

```python
ACCEPTABLE_CACHE_STATUSES = {"HIT", "MISS", "EXPIRED", "STALE", "REVALIDATED", "UPDATING"}
MIN_CACHE_SECONDS = 3 * 86400            # 3-day floor
RECOMMENDED_MAX_AGE = 31536000           # 1 year
MISS_RETRY_DELAY_SECONDS = 2
MISS_RETRY_ATTEMPTS = 2                  # after the initial request (3 requests total)

def parse_cache_control(value: str) -> dict      # tolerant: lowercased directives,
    # int values where parseable, True for valueless; NEVER raises on garbage
def cache_seconds(cc: dict) -> int | None        # max(max-age, s-maxage); None if neither parseable
def parse_expires(value: str) -> datetime | None # email.utils.parsedate_to_datetime; None on garbage
    # `_test_url` passes now=datetime.now(timezone.utc); a naive parsed Expires is treated
    # as UTC (both sides aware -> comparisons never raise TypeError)
def evaluate_headers(headers: dict, *, is_main_page: bool, kind: str,  # 'page'|'asset'
                     now: datetime, status_code: int) -> list[dict]
def should_retry_miss(headers: dict, items: list[dict]) -> bool
```

Item shape: `{"id": str, "kind": "page"|"asset", "url": <set by caller>, "params": dict}`.
Battery rules, in order (each = one item id; §12 defines all language):

| id | Trigger |
|---|---|
| `http-error` | final status not 2xx (after redirect policy). **Stop testing this URL** (no other items). |
| `cf-status-missing` | no `Cf-Cache-Status` header |
| `cf-status-uncacheable` | `Cf-Cache-Status` not in ACCEPTABLE (params: `status`, e.g. DYNAMIC/BYPASS/NONE/UNKNOWN) |
| `no-cache-control` | no `Cache-Control` header. **Skip remaining Cache-Control rules.** |
| `no-max-age` | CC present, neither max-age nor s-maxage parseable. **Skip remaining CC rules.** |
| `short-cache-time` | `cache_seconds < MIN_CACHE_SECONDS` (params: `seconds`) |
| `cc-private` / `cc-no-cache` / `cc-no-store` / `cc-proxy-revalidate` | directive present (independent items; all that apply) |
| `cc-must-revalidate` | directive present AND NOT `is_main_page` (main page: allowed — U-M emergency-alert convention; the generic variant explains the same page-freshness rationale) |
| `expires-short` | `Expires` present AND (CC absent OR neither max-age nor s-maxage **parseable** — same predicate as `no-max-age`, so `max-age=garbage` counts as absent for both) AND parsed value < now + 3 days (unparseable `Expires` ⇒ no item) |
| `set-cookie` | `Set-Cookie` present and `Cf-Cache-Status` ≠ BYPASS |
| `set-cookie-bypass` | `Set-Cookie` present and `Cf-Cache-Status` == BYPASS — **replaces** the `cf-status-uncacheable` item for this URL |

Transport items (built by cache.py from `FetchResult.error`, same shape): `timeout`,
`invalid-cert`, `challenge`, `request-failed` (params: `reason`), `too-many-redirects`.
Retry item: `miss-persistent`.

`should_retry_miss(headers, items)` → True iff `Cf-Cache-Status == "MISS"` AND
`cache_seconds(cc) is not None and cache_seconds >= MIN_CACHE_SECONDS` AND no item in
{`http-error`, `no-cache-control`, `no-max-age`, `short-cache-time`, `cc-private`,
`cc-no-cache`, `cc-no-store`, `cc-proxy-revalidate`, `set-cookie`, `set-cookie-bypass`} was
produced (`http-error` in the set prevents burning retries on e.g. a cacheable 404 whose
testing already stopped).
(`cc-must-revalidate` alone does not block the retry — the object is still cacheable.)

Shadow paths: headers dict empty (→ `cf-status-missing` + `no-cache-control`); garbage CC value
(tolerant parse; unparseable numerics treated as absent); duplicate headers (httpx folds all but
Set-Cookie); status_code None never reaches the battery (transport error short-circuits).

### 8.7 `pages.py` — pure extraction/selection

```python
EXCLUDED_PATH_PREFIXES = ("/api/", "/wp-admin", "/wp-login", "/login", "/logout",
    "/user/login", "/account/", "/auth/", "/profile", ".authorize", "/token", "/userinfo",
    "/callback", "/end_session", "/register", "/signup")

def extract_page_links(html_text: str, fqdn: str, base_url: str) -> list[str]
def choose_pages(links: list[str], rng) -> list[str]              # up to 3
def extract_assets(html_text: str, fqdn: str, base_url: str) -> dict  # {'js':[], 'css':[], 'img':[]}
def choose_assets(assets: dict, rng) -> list[tuple[str, str]]     # [(class, url)] ≤1 per class
def classify_redirect(current_url: str, location: str, fqdn: str) -> str  # 'follow'|'cross'
```

`extract_page_links` (bs4, `html.parser` backend — no lxml dependency): all `a[href]`;
`urljoin(base_url, href)`; keep only scheme `https` and host == fqdn (exact, case-insensitive;
`www.fqdn` is a DIFFERENT fqdn); drop the main page itself (path `/` or empty, regardless of
query/fragment — PROMPT: "including fragments/anchors"); drop URLs whose PATH contains any
`EXCLUDED_PATH_PREFIXES` entry that starts with `/` as a prefix-of-path match, and the
`.authorize` entry as a substring-of-path match (it's an extension-style marker, not a prefix);
strip fragments; dedupe; sort lexicographically (PROMPT — stable RNG input). Malformed hrefs
(ValueError from urljoin/urlsplit) are skipped.

`choose_pages(links, rng)`: `rng.sample(links, min(3, len(links)))`. Zero links ⇒ `[]` (skip
step f — PROMPT).

`extract_assets`: `script[src]` → js; `link[rel~=stylesheet][href]` → css; `img[src]` → img;
same https/same-FQDN/relative filters; dedupe; sort per class. `choose_assets`: `rng.choice`
per non-empty class.

`classify_redirect`: parse both URLs; `'follow'` if (a) http→https upgrade with identical
host+path+query, or (b) target scheme is https AND target host == fqdn (any path/query);
else `'cross'` (explicitly including apex↔www). Non-https same-FQDN target (https→http
downgrade) → `'cross'` (never probe insecurely on purpose). Note: rule (a) is unreachable in
practice — all initial URLs are https and downgrades classify `'cross'` — it exists to honor
the PROMPT rule verbatim; don't hunt for an http entry point.

RNG (D6): in `cache.py`, `make_rng = lambda site_name, date_iso: random.Random(f"{site_name}:{date_iso}")`
as a module attribute (test seam), `date_iso = sc.options.date.isoformat()`.

### 8.8 `cache.py` — orchestration

```python
def check_cloudflare_cache(site_context) -> None:
    fqdns = site_context.get("fqdns_behind_cloudflare") or []
    if not fqdns:
        return
    cfg = cachecheck_config()
    rng = make_rng(site_context["site"]["name"], sc.options.date.isoformat())
    items_by_fqdn = {}
    for fqdn in sorted(fqdns):
        items_by_fqdn[fqdn] = _check_fqdn(fqdn, cfg, rng)
    for notice in build_cache_notices(site_context["site"]["name"], items_by_fqdn,
                                      umich=sc.umich_enabled(), doc_url=cfg["report_doc_url"],
                                      framework=site_context["site"].get("framework", "")):
        site_context.add_notice(notice)
```

`_check_fqdn(fqdn, cfg, rng) -> list[items]`:
1. `main = _test_url(f"https://{fqdn}/", fqdn, cfg, is_main_page=True, kind="page")` —
   returns `(items, fetch_result)`.
2. If main's fetch errored, was dropped (cross-FQDN), or returned non-2xx → return collected
   items (link/asset steps need a successful body; PROMPT: "move on to the next request").
3. `links = extract_page_links(main.text, fqdn, main.final_url)`; `picks = choose_pages(links, rng)`.
4. For each page in `[main] + [ _test_url(p, …, kind="page", is_main_page=False) for p in picks ]`
   with a successful (2xx, non-errored) response — where "page" here is the FetchResult
   element of each `_test_url` return (items go straight into the accumulator):
   `assets = extract_assets(page.text, fqdn, page.final_url)`;
   for each `(cls, url)` in `choose_assets(assets, rng)`:
   `_test_url(url, …, kind="asset", is_main_page=False)`.
5. All requests sequential (PROMPT); items accumulate in request order.

`_test_url` responsibilities (single place for transport policy):
- Call `httpseam.fetch(...)`. Map `FetchResult.error` → transport item (`timeout`,
  `challenge`, `request-failed`, `too-many-redirects`) and return, EXCEPT:
  - `'cert'`: emit `invalid-cert` item, then `fetch(..., verify=False)` and continue the
    battery on that insecure response (PROMPT); `_test_url` returns the retry's FetchResult
    (`insecure=True`). If the insecure retry itself fails, map ITS error to the corresponding
    transport item and return it (the URL then counts as errored for §steps 2-4).
  - `'cross_fqdn_redirect'`: console note only (`sc.console.print`), NO item, return.
- Run `evaluate_headers(...)`; on `Cf-Cache-Status == MISS` run the D9 retry protocol using
  `httpseam.sleep(MISS_RETRY_DELAY_SECONDS)` guarded by `should_retry_miss`. Retry fetches are
  examined for `Cf-Cache-Status` ONLY — they are never re-run through the battery (the
  original response was already evaluated; a `Set-Cookie` appearing only on a retry is
  ignored). ANY `FetchResult.error` on a retry fetch (transport, cert, challenge, redirect
  outcomes alike) ends the protocol with neither `miss-persistent` nor a transport item
  (console note at `-v`); no insecure retry is ever attempted for retry fetches. If the
  battery ran on an insecure (`verify=False`) response, its MISS-retry fetches use
  `verify=False` too — same connection conditions as the response being verified.
- Non-2xx final response: `http-error` item only (battery stops per §8.6), AND the page's body
  is NOT mined for links/assets — a non-2xx page contributes nothing to steps 3-4 (PROMPT:
  "do not check anything else, move on").
- Set `kind`/`url` on every item; print each item to console the moment it is created
  (always, any verbosity — §10).

U-M gating uses `sc.umich_enabled()` (exposed per §6.2 item 7 — one definition; standalone
tests monkeypatch the `sc` attribute).

Shadow paths: `fqdns_behind_cloudflare` missing/empty → return (hook is registered only when
cachecheck enabled, but `--only-warn` + transient DNS can leave it empty); main page
unparseable HTML → bs4 returns what it can, zero links is normal; every transport error →
named item + move on (zero silent failures); user interrupt (Ctrl-C) → KeyboardInterrupt
propagates (no swallowing).

### 8.9 `egress.py` — setup hook

```python
TRACE_URLS = {4: "https://1.1.1.1/cdn-cgi/trace", 6: "https://[2606:4700:4700::1111]/cdn-cgi/trace"}
FALLBACK_RADAR = "https://ip-check-perf.radar.cloudflare.com/"   # JSON: ip_address
FALLBACK_IFCONFIG = "https://ifconfig.me/ip"    # bare IP body (the bare / path
                                                # content-negotiates on User-Agent and can
                                                # return HTML with our UA; /ip is always bare)
LOCAL_ADDR = {4: "0.0.0.0", 6: "::"}

def _probe(url: str, family: int, timeout: float) -> str | None
probe = _probe          # module attr = the egress-check monkeypatch seam (see D8 note)
def _discover_ip(family: int, timeout: float) -> str | None       # trace → radar → ifconfig
def _fetch_allowlist(cfg: dict) -> list[ipaddress._BaseNetwork]
def check_egress_ip() -> None
```

`check_egress_ip()` flow:
1. Early return (debug message) if any of `sc.options.update`, `.import_older_metrics`,
   `.create_tables`, `.allow_any_source_ip` — the check runs only on report paths (full
   report / `--only-warn`). **The `create_tables` return is REQUIRED**: setup hooks run on
   that path (verified fact).
2. `ips = {fam: _discover_ip(fam, timeout) for fam in (4, 6)}` — per family, try trace URL
   (parse the `ip=` line), then radar (JSON `ip_address`), then ifconfig (stripped body must
   parse as `ipaddress.ip_address`); each probe result is validated to be an address OF THAT
   family (a mismatched-family answer counts as probe failure). Hostname fallbacks force the
   family via `httpx.HTTPTransport(local_address=LOCAL_ADDR[fam])` — ⚠ verify during
   implementation that `local_address="::"` actually pins the connection to IPv6 with the
   installed httpx/anyio (happy-eyeballs subtlety); the mismatched-family validation above is
   the backstop either way. All three failing →
   family = None + console note `no IPv{fam} connectivity; skipping IPv{fam} egress check`.
3. `if not any(ips.values()): sys.exit("ERROR: could not determine this host's external IP address (all probe endpoints failed for both IPv4 and IPv6)")`.
4. `nets = _fetch_allowlist(cfg)`: `client = sc.plugin_context['plugin.cloudflare']['get_client']()`
   (shared lazy client — house rule; guaranteed present because `[Cloudflare].enabled` gates
   this package). `client.rules.lists.list(account_id=cfg["account_id"])`, match `.name ==
   cfg["list_name"]` → not found → `sys.exit` naming the list and account;
   `client.rules.lists.items.list(account_id=…, list_id=…)` → `ipaddress.ip_network(item.ip,
   strict=False)` per item (skip+warn items without an `ip` attribute — redirect-type lists).
   `cloudflare.CloudflareError` (SDK base) → `sys.exit` with the API error text (matches
   `ips.py`/`fqdns.py` fatal style). Empty list → `sys.exit` (an empty allowlist can never
   pass; likely a scope/name problem — mirrors the zero-zones-fatal convention).
5. Membership: for each discovered `ip`, `any(ip_address(ip) in n for n in nets if n.version == fam)`;
   failure → `sys.exit(f"ERROR: this host's IPv{fam} egress address {ip} is not in Cloudflare "
   f"list '{list_name}' (account {account_id}). Cache checks would see challenge/external "
   f"behavior. Run from an allow-listed network, update the list, or pass --allow-any-source-ip.")`.
6. Success → one console line: `Egress IP check passed: {ips}` (+ ephemeral status while running).

Note: Lists API needs a token scope beyond DNS:Read (Account Filter Lists: Read) — documented
in `docs/cloudflare-cachecheck.md` (§11) and surfaced by the API-error fatal path.

---

## 9. Consolidation + notices (`notices.py`)

- Item **consolidation key**: `(item["id"], item["kind"], tuple(sorted(item["params"].items())))`
  — the URL is excluded (PROMPT step 3: notices "varying only in which URLs were tested" merge).
- Per-FQDN **signature** = `frozenset(consolidation keys)`. FQDNs with equal signatures form
  one group; each group → ONE notice. (Singleton groups degrade to today's per-FQDN notice.)
- `build_cache_notices(site_name, items_by_fqdn, *, umich, doc_url, framework) -> list[notice]`:
  FQDNs with empty item lists are dropped; groups ordered by first FQDN alphabetically;
  `framework` drives the D15 CMS-appropriate U-M links.
- Notice dict:
  - `type: "warning"`, `short: "improve Cloudflare caching"`,
  - `csv: f"{site_name},cloudflare-cache,{'+'.join(sorted(group_fqdns))},{'+'.join(sorted(ids))}"`
    (ALL notices from this check use csv key `cloudflare-cache` — PROMPT).
  - `message` (HTML): intro paragraph (why caching matters — cost/performance/protection), then
    one `<li>` block per distinct item (language per §12, variant per `umich`), each listing the
    triggering URL(s) grouped per FQDN, page/asset labeled. All dynamic strings escaped:
    URLs via `sc.escape_url` in `href` + `html.escape` for display text; header values and
    reasons via `html.escape`. **Injection rule: every remotely-derived string (URL, header
    value, redirect target, error text) passes through `html.escape` (display) and/or
    `escape_url` (href) — no exceptions.**
  - `text`: omitted (auto-generated by `add_notice` via html2text) unless rendering proves
    poor, in which case hand-write like the existing DNS notices.
  - NEVER suggests disabling/bypassing caching or removing Cloudflare rules (PROMPT hard rule).
- Standalone (non-FQDN) notices: none are currently produced (egress failures are fatal), but
  `build_cache_notices` is the documented place to add them with the same csv key.

---

## 10. Console & verbosity

| Verbosity | Behavior |
|---|---|
| 0 | `with sc.console.status(...)` per FQDN, `status.update(f"Cloudflare cache check: {fqdn} — {step}")` per URL/step (ephemeral — PROMPT). Entered only at verbosity 0. |
| `-v` (≥1) | No status spinner; non-ephemeral step lines via `sc.debug(...)` (level 1): check start, per-FQDN start, URL selection results, per-URL step. |
| `-vvv` (≥3) | Additionally `sc.debug(..., level=3)`: request method+URL, redirect hops, final status code, and ALL response headers per request. |
| always | Every result item printed the moment it occurs via `sc.console.print` — concise technical wording (§12 console column): URL, page/asset, test, problem. Cross-FQDN redirect drops and family-skip notes likewise always printed. |

The status context wraps only this check's own HTTP work (no terminus calls inside), so no
rich Live nesting is possible.

## 11. Error inventory (prime directive 2)

| Failure | Named trigger | Caught | User sees | Tested |
|---|---|---|---|---|
| Missing check dep | `ImportError` in `__init__.py` deferred import | yes | red error naming package + install cmd; exit 1 | integration |
| Missing required config | `validate_cachecheck_config` | n/a | red error listing missing keys; exit | integration |
| Unknown phase name | `add_hook`/`invoke_hooks` validation | n/a | red error listing known phases; exit 1 | integration |
| All IP probes fail (both families) | `_discover_ip` returns None twice | `check_egress_ip` | fatal, names all endpoints | integration |
| One family unreachable | per-family probe chain exhausted | yes | console note, family skipped | integration |
| Egress IP off-list | membership test | n/a | fatal naming IP/list/account + `--allow-any-source-ip` hint | integration |
| List not found / empty / API error | Lists API result / `cloudflare.CloudflareError` | yes | fatal with API/list detail | integration |
| Per-URL timeout | `httpx.TimeoutException` | `_fetch` → `error='timeout'` | console + `timeout` item | integration |
| Invalid certificate | `httpx.ConnectError` (TLS verify) | `_fetch` → `'cert'` | `invalid-cert` item, insecure retry continues battery | integration |
| Challenge | `cf-mitigated: challenge` header | `_fetch` → `'challenge'` | `challenge` item, URL abandoned | integration |
| Other transport failure | other `httpx.TransportError`/`HTTPError` | `_fetch` → `'connection'` | `request-failed` item (reason param) | integration |
| Cross-FQDN redirect | `classify_redirect` → `'cross'` | cache.py | console note only, NO item | integration |
| >5 redirects | hop counter | `_fetch` → `'too_many_redirects'` | `too-many-redirects` item | integration |
| Non-2xx | status check | battery | `http-error` item, URL testing stops | unit |
| Garbage Cache-Control/Expires | tolerant parsers | headers.py | treated as absent; no crash | unit+Hypothesis |
| Ctrl-C | `KeyboardInterrupt` | NOT caught | normal abort | — |

No catch-all `except Exception` anywhere in the new code.

---

## 12. Result-item language catalog

Rules: console = one line, concise/technical, no doc links, URL + page/asset + test + problem
(PROMPT). HTML = short, plain-language, actionable, one primary doc link (U-M variant links to
`{doc_url}#<item-id>` — the §13.1 page uses item ids as anchors — plus at most one supporting
link; generic variant uses public docs and **never emits `{doc_url}`** — its default is a U-M
URL that means nothing to other institutions). Where a generic row has no natural public doc
(`timeout`, `request-failed`), the PROMPT's alternative applies: the item text itself carries
the shortest concise next step ("check the server/network serving this URL with your web
team") and no doc link — mark these "steps only" in the implementation. Per D15, the
CMS-appropriate U-M link (WP node/5114 / Drupal node/4242) is ADDED to each of the five
framework-relevant rows (`no-cache-control`, `no-max-age`, `short-cache-time`, `set-cookie`,
`set-cookie-bypass`) — the table below spells it out only on `no-cache-control` for brevity.
`{url}` is the escaped URL, `{kind}` is "page" or
"static asset". Implementer: keep wording within ±copyediting of this table; the snapshot test
freezes the final form. ⚠ Spot-check the external URLs (marked ✓ = high confidence) during
implementation; never fetched at runtime.

Shared generic links: MDN Cache-Control `https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control` ✓;
MDN Set-Cookie `…/Web/HTTP/Headers/Set-Cookie` ✓; MDN Expires `…/Web/HTTP/Headers/Expires` ✓;
Cloudflare cache responses (`Cf-Cache-Status` values) `https://developers.cloudflare.com/cache/concepts/cache-responses/`;
Cloudflare default cache behavior `https://developers.cloudflare.com/cache/concepts/default-cache-behavior/`;
Cloudflare challenges `https://developers.cloudflare.com/cloudflare-challenges/`;
Pantheon+Cloudflare `https://docs.pantheon.io/cloudflare`.

| id | Console (format string) | HTML gist — U-M variant | HTML gist — generic variant |
|---|---|---|---|
| `http-error` | `{url} ({kind}): HTTP {status}, cannot check caching` | This {kind} returned an error (HTTP {status}) so its caching could not be checked. Fix the error, then re-check. Link: `{doc_url}#http-error`. | Same text; link MDN HTTP status codes `…/Web/HTTP/Status` ✓. |
| `cf-status-missing` | `{url} ({kind}): no Cf-Cache-Status header — response may not be served via Cloudflare` | Cloudflare did not report a cache status for this {kind}; it may not be fully protected/accelerated by Cloudflare. Investigate so you get Cloudflare's full protection and savings. Link `{doc_url}#cf-status-missing`. | Same; link Cloudflare cache-responses doc. |
| `cf-status-uncacheable` | `{url} ({kind}): Cf-Cache-Status {status} — not being cached` | Cloudflare reports status <code>{status}</code>, meaning this {kind} is not served from cache. Investigate to ensure full protection, cost savings, and performance. U-M cache rules may need attention: node/5110. Also `{doc_url}#cf-status-uncacheable`. | Same; link Cloudflare cache-responses + default-cache-behavior. |
| `no-cache-control` | `{url} ({kind}): no Cache-Control header` | The {kind} sends no <code>Cache-Control</code> header, so caching is unpredictable. Configure your site to send one allowing caching for 31536000 seconds (1 year). Links: `{doc_url}#no-cache-control`; WP → node/5114 / Drupal → node/4242 (CMS-appropriate, when framework known — see note below). | Same; link MDN Cache-Control. |
| `no-max-age` | `{url} ({kind}): Cache-Control has no max-age/s-maxage` | Add <code>max-age=31536000</code> (1 year) so Cloudflare can cache this {kind}. Link `{doc_url}#no-max-age`. | Same; MDN Cache-Control. |
| `short-cache-time` | `{url} ({kind}): cache time {seconds}s < 3 days` | Cache time is only {human_seconds}; increase to 31536000 seconds (1 year) for full benefit. Link `{doc_url}#short-cache-time` + node/4241. | Same; MDN Cache-Control. |
| `cc-private` | `{url} ({kind}): Cache-Control contains private` | Remove <code>private</code> from public content — it prevents Cloudflare from caching. `{doc_url}#cc-private`. | Same; MDN. |
| `cc-no-cache` | analogous | analogous (remove `no-cache`) | MDN |
| `cc-no-store` | analogous | analogous (remove `no-store`) | MDN |
| `cc-proxy-revalidate` | analogous | analogous (remove `proxy-revalidate`) | MDN |
| `cc-must-revalidate` | `{url} ({kind}): Cache-Control contains must-revalidate (non-main page)` | Remove <code>must-revalidate</code> from pages other than your home page (on the home page it is intentionally used so emergency alerts appear promptly). `{doc_url}#cc-must-revalidate`. | Remove `must-revalidate` unless you have a freshness requirement on this specific {kind}; MDN. |
| `expires-short` | `{url} ({kind}): Expires < 3 days and no max-age` | Replace the legacy <code>Expires</code> header with <code>Cache-Control: max-age=31536000</code>. `{doc_url}#expires-short`. | Same; MDN Expires. |
| `set-cookie` | `{url} ({kind}): Set-Cookie on public content` | The site sets a cookie on public content, which prevents caching. Configure it not to set cookies for anonymous visitors. `{doc_url}#set-cookie` + node/5110 (`#rule%202` — session-cookie bypass list). | Same; link Pantheon `https://docs.pantheon.io/cookies` (⚠ verify) + MDN Set-Cookie. |
| `set-cookie-bypass` | `{url} ({kind}): Cf-Cache-Status BYPASS caused by Set-Cookie` | Cloudflare is bypassing cache **because** the site sets a cookie here. Stop setting cookies for public content to restore caching. `{doc_url}#set-cookie-bypass` + node/5110 `#rule%202`. | Same; Cloudflare cache-responses + MDN Set-Cookie. |
| `miss-persistent` | `{url} ({kind}): still MISS after 3 attempts — cacheable but never cached` | Headers allow caching but Cloudflare never served this {kind} from cache across three attempts; something (e.g. a `Vary` header or a cache rule) is preventing storage. Investigate with your web team. `{doc_url}#miss-persistent`. | Same; Cloudflare default-cache-behavior. |
| `timeout` | `{url} ({kind}): no response within {timeout}s` | The {kind} did not respond within {timeout} seconds; visitors likely see the same slowness. Investigate performance/availability. `{doc_url}#timeout`. | Same. |
| `invalid-cert` | `{url} ({kind}): TLS certificate invalid` | The HTTPS certificate failed validation; browsers will warn visitors. Renew/fix the certificate. `{doc_url}#invalid-cert` + Pantheon `https://docs.pantheon.io/guides/custom-certificates` (⚠ verify). | Same. |
| `challenge` | `{url} ({kind}): Cloudflare challenge (cf-mitigated) — cannot check` | Cloudflare presented a security challenge to our checker, so caching could not be verified. If unexpected for public content, review your security settings with your web team. `{doc_url}#challenge`. | Same; Cloudflare challenges doc. |
| `request-failed` | `{url} ({kind}): request failed ({reason})` | The {kind} could not be fetched ({reason}); visitors may be affected. `{doc_url}#request-failed`. | Same. |
| `too-many-redirects` | `{url} ({kind}): more than 5 redirects` | This {kind} redirects more than 5 times — likely a redirect loop. Fix the redirect configuration. `{doc_url}#too-many-redirects` + MDN redirections ✓. | Same. |

Table footnote: a generic-column "Same." means the same wording MINUS any `{doc_url}` link
(per the rules paragraph above — generic variants never emit `{doc_url}`); `timeout` and
`request-failed` are the steps-only rows (no doc link at all in the generic variant).

Note on CMS links (D15): `site_context["site"]["framework"]` comes from the Pantheon site
record and is available from the start of the per-site loop (it is NOT gather data), so
`build_cache_notices` takes a `framework` argument and the U-M variants link CMS-appropriate
install docs — WordPress → node/5114, Drupal → node/4242 — on framework-relevant items
(`no-cache-control`, `no-max-age`, `short-cache-time`, `set-cookie`, `set-cookie-bypass`),
falling back to the CMS-neutral pages (`doc_url`, node/4241, node/5110) for other frameworks.
The relocated §7 check still owns the "install the integration" nudge; these links are
"how to fix headers in your CMS" pointers.

---

## 13. U-M documentation deliverables (manual work for Mark; NOT program-fetched)

### 13.1 New page draft: "Understanding your Cloudflare cache report"

To publish at a URL of your choosing (then set `report_doc_url`). Structure: intro (what the
monthly "Cloudflare caching" notice is, why caching matters — cost, performance, protection);
"How we test" (main page + up to 3 linked pages + up to 1 JS/CSS/image per page; requests come
from `user_agent` string, from U-M networks); then ONE SECTION PER ITEM ID above, each with
heading id equal to the item id (e.g. `<h2 id="set-cookie-bypass">`), containing: what we saw,
why it matters, how to fix (WordPress: umich-cloudflare plugin steps/link node/5114; Drupal:
node/4242; general: node/4241, node/5110), and what "fixed" looks like next month. Full draft
text to be generated at implementation step 9 as `development/2026-07-08-cloudflare-cache-
configuration/umich-doc-drafts.md` (kept out of `docs/` — it is U-M-site content, not program
docs).

### 13.2 Suggested edits to existing pages

- **node/5114 (WP plugin)** & **node/4241 (Managing caching)**: add `id` attributes to all
  section headings so reports can deep-link (list of suggested ids in the draft file).
- **node/5110 (Cache rules)**: rename anchor ids `rule 1`…`rule 4` to `rule-1`…`rule-4`
  (spaces in ids require `%20` and are fragile); if renamed, update §12 links accordingly —
  the spec assumes the CURRENT ids with `%20` until you confirm the rename.
- **node/4241**: add a short "Recommended Cache-Control values" section (31536000 for static
  content; the must-revalidate main-page convention) that `short-cache-time`/`no-max-age`
  items can cite.

---

## 14. Tests

Harness rules honored: only `run_program` for subprocess runs (never `--all`/`--for-real`);
modules loaded standalone via SourceFileLoader; fake `cloudflare` injected in `sys.modules`
where the SDK is imported; goldens untouched (all three have `[Cloudflare].enabled=false`).

### Unit (`tests/unit/`)
- `test_cachecheck_headers.py` — table-driven battery: every §8.6 row; must-revalidate
  main-vs-other; Expires-only path (with/without CC, unparseable Expires, and
  `Cache-Control: max-age=garbage` + short Expires → BOTH `no-max-age` and `expires-short`
  fire — the shared "parseable" predicate); BYPASS+Set-Cookie
  replacement; `should_retry_miss` matrix (MISS+cacheable → True; MISS+short → False;
  HIT/EXPIRED → False; must-revalidate alone → True); http-error short-circuit.
  Hypothesis: `parse_cache_control` never raises on arbitrary text; `cache_seconds` ==
  max of directives when both parseable; `evaluate_headers` deterministic.
- `test_cachecheck_pages.py` — each exclusion prefix; `.authorize` substring rule; cross-FQDN
  and non-https links dropped; main-page/fragment exclusion; dedupe+sort; relative resolution;
  asset extraction per tag; `classify_redirect`: http→https upgrade follow, same-FQDN follow,
  apex↔www cross, https→http downgrade cross. Hypothesis: output ⊆ candidates; no excluded
  prefix in output; permutation-stability (sorted first).
- `test_cachecheck_consolidation.py` — equal signatures merge; differing params split;
  groups partition the FQDN set (Hypothesis); csv format.
- `test_section_gating.py` — §5 cases.
- `test_argparse_contract.py` — `--allow-any-source-ip` present, default False.

### Integration (`tests/integration/`)
- `test_hooks_phases.py` — PHASES order/content; unknown bare name → SystemExit on both
  add_hook and invoke_hooks; dotted event registers+invokes; empty valid phase no-op;
  reset_sc uses sc.PHASES.
- `test_check_cloudflare_egress.py` — monkeypatch `egress.probe` + fake lists client via
  `sc.plugin_context['plugin.cloudflare']['get_client']`: both families pass; one family
  dead → skipped note; off-list IP → SystemExit (message names IP+list); all probes dead →
  SystemExit; each gating flag (`--update`, `--import-older-metrics`, `--create-tables`,
  `--allow-any-source-ip`) → early return, zero probes; list missing → SystemExit; empty
  list → SystemExit; mismatched-family probe answer treated as failure.
- `test_check_cloudflare_cache.py` — monkeypatch `httpseam.fetch` + `httpseam.sleep` with
  canned FetchResults (real HTML strings, parsed by real bs4): happy path zero items → zero
  notices; MISS-retry (sleep called 2×, third MISS → miss-persistent; HIT on 2nd → no item;
  EXPIRED first → no retry); cert → invalid-cert + insecure battery continues; challenge
  short-circuits; cross-FQDN redirect → no item, URL dropped; non-2xx → http-error only;
  two FQDNs identical-except-URLs → one consolidated notice; different items → two notices;
  RNG determinism (same site+date → same picks; different date → may differ); every notice
  has csv starting `{site},cloudflare-cache,`; U-M vs generic variant selection; D15
  CMS-link selection (wordpress → node/5114 link present, drupal → node/4242, other → neither).
- `test_check_cloudflare_init.py` — disabled configs register nothing (each of: no
  [Cloudflare], enabled=false, no cachecheck, cachecheck.enabled=false); enabled+missing
  account_id/list_name → SystemExit; enabled+deps present → two hooks registered;
  ImportError path → SystemExit with install hint (inject a broken submodule import).
- `test_check_umich_cloudflare_cms.py` — WP with/without plugin list; Drupal 9 runs 4 module
  checks; Drupal 7 skipped; empty fqdns → no notices; None plugins/mods → no notices
  (monkeypatch `sc.check_wordpress_plugin`/`sc.check_drupal_module` recorders).
- `test_cachecheck_notice_render.py` — build a representative consolidated notice (several
  item types incl. set-cookie-bypass and miss-persistent), render through the real template
  path in-process, syrupy snapshot (U-M and generic variants). Assert all remotely-derived
  strings appear escaped (inject `<script>` in a URL/param and assert `&lt;script&gt;`).

### E2E
- Existing 3 goldens must remain byte-identical through steps 1–4 (phase system + relocation)
  and 5–9 (check disabled in their configs). Full `./run-tests` in CI order per §15.

---

## 15. Implementation sequence & acceptance criteria

Each step ends green before the next starts. **When you change the program, add/adjust tests
in the same step** (house rule).

| Step | Work | Gate |
|---|---|---|
| 1 | §5 recursive gating + unit tests | `./run-tests --fast` green |
| 2 | §6.1 registry + D1 rename + §6.4 fallout + `test_hooks_phases.py` (atomic commit — the only breaking rename) | full `./run-tests` green |
| 3 | §6.2 seams + data stuffing + helper exposure (no behavior change) | full `./run-tests`; goldens byte-identical |
| 4 | §7 relocation (+delete old blocks) + its tests | full `./run-tests`; goldens byte-identical |
| 5 | §8.1-8.4 skeleton: deps, flag, tomls, cfg, gated `__init__` + import guard + no-op stub `egress.py`/`cache.py` defining the two hook functions (filled in at steps 7-8, so `__init__`'s imports and the "two hooks registered" test pass) + `test_check_cloudflare_init.py`, argparse test | `./run-tests --fast` |
| 6 | §8.6/8.7/§9 pure helpers + unit/Hypothesis tests | `./run-tests --fast` |
| 7 | §8.9 egress + integration tests | `./run-tests --fast` |
| 8 | §8.5/8.8 httpseam + cache orchestration + integration + snapshot tests | full `./run-tests` |
| 9 | §12 language finalization, docs (§16), umich-doc-drafts.md (§13), CLAUDE.md/README | final full `./run-tests` + `--coverage` |

Acceptance criteria ("done" means all of):
1. `./run-tests` fully green (all tiers available offline; live tier as available).
2. All three goldens byte-identical to pre-change (`git diff --stat tests/e2e/__snapshots__`
   empty; no `--update-goldens` run anywhere).
3. `./pantheon-sitehealth-emails --help` shows `--allow-any-source-ip`.
4. With a local config enabling cachecheck (test copy, real creds):
   `./pantheon-sitehealth-emails --date 20260331 its-wws-test1 -v` →
   egress check runs and passes (or fatals correctly off-network); per-FQDN cache steps
   logged; result items appear immediately; consolidated "Cloudflare caching" notice in
   `build/its-wws-test1.html`; re-run selects identical URLs (D6).
5. Same command with `--update` → no egress probe, no cache checks (gating).
6. `--create-tables` with a scratch config → exits "Tables created." with zero HTTP probes.
7. `-vvv` run shows full request/status/response-header debug for each URL.
8. Config with `[Cloudflare.cachecheck].enabled=false` → yellow skip line, nothing registered.
9. Config enabled but missing `list_name` → fatal naming the missing key.

## 16. Documentation updates (in-repo)

- **New `docs/cloudflare-cachecheck.md`** (end-user, model `docs/cloudflare-fqdns.md`):
  what the check does; when it runs (report paths only; opt-in flag table); configuration
  reference (§8.2 keys, incl. the pass-1-resolvable substitution invariant); the egress
  allowlist test (incl. required token scope: Account Filter Lists Read;
  `--allow-any-source-ip`; and an explicit warning that **the list must contain ranges for
  every IP family the host can egress on** — an IPv6-capable runner with an IPv4-only list
  fatals every report run per D4); how URLs are chosen (seeded determinism,
  monthly rotation); result-item glossary (id → meaning, console + report); U-M vs generic
  language selection.
- **`sample-pantheon-sitehealth-emails.toml`**: §8.2 block.
- **README.md**: mention new check + flag in the feature list/TODO cleanup; note the
  `cloudflare` extra now includes httpx+beautifulsoup4.
- **CLAUDE.md**: replace the setup/check hook description with the PHASES list + §6.3
  contract table; note unknown-phase fatal + dotted events; note `sc.escape_url`/
  `sc.check_wordpress_plugin`/`sc.check_drupal_module` exposure; relocate note for
  cloudflare_cms; `[Cloudflare.cachecheck]` summary + opt-in default + egress gating flags;
  recursive gate_disabled_sections (update the "top-level only" sentence); new test files;
  update the "Still not yet relocated" paragraph (WP/Drush fqdns-gated checks now moved;
  billing notices/user-agent checks/template branding still pending, seam now exists).

## 17. Risks, partial states, rollback

- Steps land independently; Part B is dark until a config opts in (D3) — partial deployment
  is safe by construction. Rollback of any step = revert its commit.
- Step 2 is the only breaking rename; it lands atomically with its test updates.
- Steps 3–4 must produce byte-identical goldens — any golden diff there is a bug, stop.
- Line numbers in this SPEC drift as steps land; anchors are the quoted code.
- The egress probes and cache checks run only against: three fixed probe endpoints, and FQDNs
  already proxied through the institution's own Cloudflare zones — no new outbound surface
  beyond that; UA identifies us (config).
- Threat model for the `verify=False` retry (§8.5/§8.8): it happens only AFTER the invalid
  cert has been flagged as a result item, sends no cookies/credentials (fresh client,
  `trust_env=False`), and the response is used solely to report cache headers back to the
  site owner. `FetchResult.insecure=True` marks such responses. This is PROMPT-mandated
  diagnostic behavior, not a trust decision; nothing else in the program disables TLS
  verification.
- Rollout preconditions for flipping `enabled=true` in the live config (record in the docs and
  the private-config commit): (a) `um_networks` covers every IP family the runner can egress
  on (D4 fatals otherwise); (b) the §13.1 page is published and `report_doc_url` set to it —
  enabling earlier ships dead links in every notice.
- Deferred (written down): §1 NOT-in-scope list; `site_pre_render` ships without a consumer
  (documented seam); node/5110 anchor rename decision is Mark's (§13.2).
