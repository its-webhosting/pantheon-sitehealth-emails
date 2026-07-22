# SPEC — Increment I10: gather (Drupal half) + `check/drupal/` + `check/addon_updates/` + UA check → `check/umich/`

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I10 (B30, B35, B39, B48; baseline lines 740–791 =
`check_drupal_module`, now `psh/_legacy.py:270–319`). Tier-1 assignment: §3.1 row
`psh/gather.py` (this increment delivers the Drupal half plus `check_drupal_module`).
Tier-2 assignments: §3.2 rows `check/drupal/` ("PAPC module check, D7 EOL + tag1_d7es,
multisite probe (from B30/B35)" at `site_post_dns` (multisite) / `site_post_gather`),
`check/addon_updates/` ("add-on updates table notice (B39)" — the B48 half is **amended
out**, D-i10-1), and `check/umich/` ("Drupal UA check (B35)"). Config: §5
(`[Check.drupal]`, `[Check.addon_updates]`, both default **true**). What stays in
`main()`: §3.3 (+ the D-i10-1 amendment). Obligations: §7. Behavior bar: §8. Invariants:
§9 (esp. 1, 3, 8, 9). Ratchet: §13.

**CAMPAIGN.md amendments this increment ships (user-approved 2026-07-22, this session;
applied to the document in the closing commit + ledgered, per the preamble rule):**

1. **B48's *emission* stays in `main()`; only its builder moves** (amends §3.2 row
   `check/addon_updates/`, §11 row I10, §3.1 row `psh/gather.py`, §3.3). Reason
   (D-i10-1): a `site_post_gather` smells hook cannot be ordered after the
   `wp_smell`/`drush_smell` in-place mutators — D-i9-3 deliberately made rebinds
   DAG-invisible (declaring `produces: ['wp_smell']` is a §4-condition-2 fatal against
   the core registry), and registration order is alphabetical package order, which puts
   `check/addon_updates` **first** in the phase; relocation would also add smell rows to
   `--only-warn` csv output (B48 sits after that gate, `psh/_legacy.py:2004`, today) — a
   §8 surface change. A `mutates` hook declaration that would dissolve this class is
   **post-campaign work → README TODO** (user decision).
2. **§4 gains the hook-produced-key definition** (one paragraph): hooks MAY produce
   keys of their own — declared in `produces`, validated for duplicate producers,
   cycles, and phase position by the existing conditions — and such keys are
   **DAG-declared, not registry-owned**: they are present only when the producing hook
   ran, are read with `.get()`, and are NOT part of the guaranteed per-phase contract
   (whose §4 new-keys list stays exhaustive for registry keys). Reason (D-i10-3): the
   multisite probe introduces the campaign's first such keys; without the amendment,
   CAMPAIGN.md's glossary ("Contract — the per-phase **guaranteed** keys") and §4's
   exhaustive list would silently contradict shipped code — the preamble's
   never-a-silent-divergence rule requires the edit.
3. No other amendment. Everything else lands per the frozen architecture.

**Carried notes this spec honors** (LEDGER I9 "Open questions for I10" + earlier):
`gather_drupal` mirrors the I9 shape (`DrupalGather` NamedTuple; `check_drupal_module`
joins its sibling in `psh/gather.py`); B39/B48 `site_context` reads are already in place
(B48 repointed at I9; B39 reads the same list object the stuffer publishes); the
`stuff_gather_contract` docstring correction is discharged here (D-i10-11); the
pyright-scope decision **D-i8-7/D-i9-8 is inherited** (D-i10-9); `Notice`-class adoption
for extra-csv notices stays deferred (D-i10-13 — candidates now I12/I14); LEDGER I1
Obs. 4 (composer-smell 8-space indentation) is discharged here (D-i10-8); smell-overwrite
order is analyzed the D-i9-4 way (D-i10-4 — result: **no** §8 amendment needed).

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I9), `CLAUDE.md`
(§ Plugin / check module system, § Per-site report pipeline, § Testing), `BLOCKMAP.md`
rows B30, B35, B36, B39, B42, B48, `prompts/directives.md`,
`prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's)

- **Drupal gather core** — the data-fetching part of B35 that feeds contract keys and
  `site_results`: core-status (version), pm:list (modules), D7 pm:updatestatus add-on
  collection, D8+ composer dry-run + composer audit add-on collection (including the
  abandoned-packages print). Moves to `psh/gather.py` as `gather_drupal`.
- **The checks** — the notice-emitting probes interleaved in B30/B35 today: PAPC module,
  D7 EOL + tag1_d7es, multisite probe (→ `check/drupal/`) and the Drupal UA check
  (→ `check/umich/`).
- **Probe keys** — `drupal_multisite` / `drupal_multisite_smell`, the campaign's first
  **DAG-declared produced keys** (amendment 2: declared in the multisite hook's
  `produces`, not in the core `CONTRACT` registry, present only when the hook probed —
  NOT guaranteed contract keys), read by `main()` with `.get()` after the
  `site_post_dns` phase (D-i10-3).
- **`DrupalGather`** — the new NamedTuple `gather_drupal()` returns (D-i10-2).

## 1. Scope (exhaustive) and non-scope

In scope (current `psh/_legacy.py` lines, verified 2026-07-22):

1. **`psh/gather.py` grows** (already born gated): `check_drupal_module` (`:270–319`,
   moved verbatim modulo ratchet dispositions), `gather_drupal` (B35 gather core:
   banner + core-status fetch + version derivation + `site_results` entry data
   `:1492–1518`, pm:list fetch `:1519–1532`, D7 pm:updatestatus add-on collection
   `:1580–1618`, D8+ composer dry-run + `composer-update` alert + parse `:1619–1664`,
   composer audit + advisories + abandoned print `:1665–1735`) returning `DrupalGather`,
   and `build_smell_notices` (`:871–948`, per amendment 1; with the D-i10-8 composer
   de-indent fix). Re-imported into `psh/_legacy.py` (I2–I9 pattern) so `main()`'s call
   sites, the `sc.check_drupal_module` exposure line (`:398`), and the
   `psh.build_smell_notices` / `psh.check_drupal_module` test references resolve
   unchanged.
2. **New package `check/drupal/`** (born gated): `__init__.py` (config-gated
   registration, default true) + `multisite.py` (B30 probe, `:1396–1421`, a
   `site_post_dns` hook producing the probe keys), `papc.py` (`:1533–1542`),
   `d7_eol.py` (`:1543–1576` — the `drupal7-eol` notice AND the tag1_d7es module check,
   one hook), the latter two at `site_post_gather`.
3. **New package `check/addon_updates/`** (born gated): `__init__.py` + `table.py` —
   the B39 add-on updates table notice (`:1825–1900`, including the verbose
   `pprint(add_on_updates)` preamble) as a `site_post_gather` hook.
4. **`check/umich/` grows**: `drupal_ua.py` (`:1736–1807`), a `site_post_gather` hook
   registered after `hummingbird` under the existing `[UMich].enabled` gate
   (D-i10-6 — a deliberate gating change, the D-i9-6 precedent).
5. **`main()` rewiring**: the Drupal branch collapses to the D-i10-2 threading; the
   no-primary-domain emission moves below `invoke_hooks("site_post_dns")` via the NEW
   pure helper `no_primary_domain_notice` (D-i10-3, the Spine's named extraction),
   reading `drupal_multisite`; `drush_smell` is seeded from `drupal_multisite_smell`
   there (D-i10-3); B36 (unknown framework) and the B33 init stay verbatim.
6. **Named fixes** (test-first, RED shown on old behavior): the B35 updatestatus
   `type in u` builtin-vs-string bug (D-i10-7) and the composer-smell baked-in
   indentation (D-i10-8, LEDGER I1 Obs. 4).
7. **`sc` façade additions**: `sc.drush_php_script`, `sc.drush_error` (D-i10-10) —
   needed by the relocated multisite/UA checks; added to the exposure block
   (`:396–404`), CLAUDE.md's documented-names list, and
   `test_documented_sc_facade_names_exist`.
8. **Config**: `[Check.drupal]` and `[Check.addon_updates]`, `enabled` defaulting
   **true** (§5, D-i8-6 shape); documented blocks added to
   `sample-pantheon-sitehealth-emails.toml` after `[Check.wordpress]`.
9. **`stuff_gather_contract` docstring correction** (D-i10-11, the LEDGER I9
   obligation). No `CONTRACT` registry change — I10 adds no core-stuffed keys.
10. **New tests** per §7-Tests (test-first, `mattpocock-skills:tdd`, at the named
    seams), including the mandated `test_hook_dag.py` `ALL_PACKAGES` extension (§7 —
    it is missing I8/I9's packages today, a ledgered discovered task).
11. **Docs**: CLAUDE.md (module map, package lists, contract-table notes, sc-façade
    list, still-hardcoded-U-M list — the Drupal UA check leaves it (now gated), the
    `updates-addons` body's its.umich.edu support link joins the
    "living in the generic check packages" half), CAMPAIGN.md amendments (header),
    README TODO (`mutates` DAG extension), ledger entry, auto-memory.

NOT in scope:

- **B36 (unknown-framework fallback), B33 init, the framework dispatch, smell resets
  (`:1238–1240`), `live_site` (`:1317`)** — loop skeleton, stays in `main()` (§3.3;
  I6 D-i6-1 reading).
- **B48's emission call (`:2374–2378`)** — stays in `main()` verbatim (amendment 1);
  only the builder moves.
- **`escape_url`** stays in `_legacy.py` (§3.1 assigns it to `psh/render.py`, I12).
  `gather_drupal` and `check_drupal_module` each need it → the same call-time bridge
  import `check_wordpress_plugin` already carries (`# noqa: PLC0415`, D-i6-2/I9
  precedent). **I12 obligation** (already ledgered at I9): replace all bridges with one
  module-level `from psh.render import escape_url`.
- **`Notice`-class adoption**: none (D-i10-13). Every moved notice keeps the legacy
  dict form — several carry extra csv fields (`not-installed,{name}`,
  `turned-off,{name}`, `updates-addons,{num_updates}`, `drupal-ua,{ua}`, the three
  smell csvs).
- **De-U-M-ifying moved notice bodies**: the `updates-addons` body's its.umich.edu
  support link moves **verbatim** into the generic `check/addon_updates/` package (the
  I8/I9 precedent; CLAUDE.md list updated). The `drupal-ua` body's
  documentation.its.umich.edu link moves to `check/umich/` where U-M content belongs.
- **The `mutates` DAG extension** — post-campaign (README TODO, user decision).
- No golden/fixture refreshes (Invariants 1, 10); no artifact-structure change (§8); no
  `_legacy.py` import removals beyond what this change orphans (I3 rule — expectation:
  NONE fully orphaned; `html`/`re`/`pprint`/`json` all have surviving users —
  implementer grep-verifies).

## 2. Architecture decisions

### D-i10-1: the four-way split of B30/B35/B39/B48 (+ the B48 amendment)

Per §3.1/§3.2 and amendment 1: contract-feeding data gathering is Tier-1
(`psh/gather.py`); notice-emitting probes are Tier-2 hooks; the smell-notice *builder*
is Tier-1 beside its sibling gathers, its *emission* stays in `main()` (it summarizes
end-of-phase smell state, which no hook position can guarantee under the D-i9-3 rebind
design, and it must stay behind the `--only-warn` gate). The failed-gather notices
(exhaustive: `core-status`, `pm-list`, `pm-updatestatus`, `composer-update`) move WITH
the fetches — they describe the gather, not a check (the I9 rule).

Flow (PD#8) — where each moved region lands relative to today:

```
main() per site:
   domain:list → classify_domains → no-domains (stays)
   [B30 gate+probe+no-primary MOVES DOWN, splits:]
   stuff_dns_contract → invoke_hooks("site_post_dns")
     ──► cloudflare.cache → dns.* → drupal.multisite ◄─[B30 probe moves]
         → pantheon_cdn_change.*        (produces drupal_multisite, drupal_multisite_smell)
   main(): drush_smell ← drupal_multisite_smell (seed, if non-empty)
   main(): no-primary-domain emission (gate + literal verbatim, now reads drupal_multisite)
   wordpress_network_url / B33 init (stay)
   if wordpress: gather_wordpress() (I9)
   elif drupal:
       gather_drupal() ◄─[B35 gather core moves]
         = core-status + pm:list + (D7: pm:updatestatus | D8+: composer dry-run + audit)
       main(): drupal_version/mods/add_on_updates/drush_smell/composer_smell/site_results ← DrupalGather
   else: B36 (stays)
   stuff_gather_contract(…)  (unchanged params; docstring fixed)
   invoke_hooks("site_post_gather")
     ──► addon_updates.table ◄─[B39 moves]  → drupal.papc ◄─[moves] → drupal.d7_eol ◄─[moves]
         → pantheon.updates → pantheon.php_eol
         → umich.cloudflare_cms → umich.oidc_login → umich.hummingbird
         → umich.drupal_ua ◄─[B35 UA check moves]  (updates site_context["drush_smell"] in place)
         → wordpress.papc → sessions → ocp → favicon  (update site_context["wp_smell"] in place)
   B42 --only-warn gate (stays)
   … chart/plan … B48 emission (STAYS; builder now lives in psh/gather.py)
```

### D-i10-2: `psh/gather.py` shapes (the I9 pattern)

```python
class DrupalGather(NamedTuple):
    drupal_version: str     # "unknown" when the core-status fetch failed (real here, unlike WP)
    modules: object         # raw drush pm:list result (dict | None | junk)
    add_on_updates: list    # D7: pm:updatestatus entries; D8+: composer audit entries
    drush_smell: str        # last-wins stderr across core-status/pm:list; "" if none
    composer_smell: str     # composer dry-run stderr; "" if none
    results_entry: dict     # {"framework", "version", "plan_name"} for site_results


def gather_drupal(site, live_site, site_context) -> DrupalGather:
    # B35 gather core verbatim: banner, core-status fetch (+drush_error on fatal, smell),
    # version derivation, results entry, pm:list fetch (+drush_error, smell), verbose
    # pprints; D7: pm:updatestatus collection (+drush_error on fatal; stderr deliberately
    # NOT a smell -- pm:updatestatus always emits verbose progress output);
    # D8+: composer dry-run (+inline composer-update alert on fatal, composer_smell),
    # package_updates parse, composer audit (advisories -> add_on_updates, abandoned print).
```

`main()` threading (exact semantics — preserves today's last-wins overwrite rules,
where a later empty smell never clears an earlier one; mirrors the I9 WP branch):

```python
elif site["framework"].startswith("drupal"):
    gather = gather_drupal(site, live_site, site_context)
    drupal_version = gather.drupal_version
    mods = gather.modules
    add_on_updates = gather.add_on_updates
    if gather.drush_smell != "":
        drush_smell = gather.drush_smell
    if gather.composer_smell != "":
        composer_smell = gather.composer_smell
    site_results[site["name"]] = gather.results_entry
```

The D7-vs-D8+ branch (`drupal_version.startswith("7.")`) stays INSIDE `gather_drupal`
(it selects between two gather strategies, not between checks). `DrupalGather` is a
supporting return type not in §6's table — the I7 `PlanRecommendation` / I9
`WordPressGather` precedent (ledger note, no amendment). Imports added to
`psh/gather.py`: `re`, `from psh.gateway import drush, drush_error, run_terminus,
terminus` (widening the existing gateway import; `drush_php_script` is NOT among them
— nothing moving into this file calls it, only the hooks via `sc.drush_php_script`,
and an unused import is F401 in a born-gated file). Column-0
literal interiors (the `composer-update` notice's are indented — they are byte-locked
all the same) move verbatim except the two named fixes (D-i10-7/D-i10-8).

### D-i10-3: the multisite probe — first hook-produced contract keys

`check/drupal/multisite.py`, `site_post_dns`, `consumes ['custom_domains',
'primary_domain']`, `produces ['drupal_multisite', 'drupal_multisite_smell']`:

```python
def check_multisite(site_context):
    site = site_context["site"]
    if (
        len(site_context["custom_domains"]) <= 1
        or len(site_context["primary_domain"]) != 0
        or not site["framework"].startswith("drupal")
    ):
        return                      # keys deliberately absent when not probed
    live_site = site["id"] + ".live"
    ...probe verbatim (:1396–1421): drush_php_script sites.php check;
       fatal/None -> sc.drush_error multisite-check notice; smell captured;
       is_multisite from isinstance/result-is-True; unconditional console print...
    site_context["drupal_multisite"] = is_multisite
    site_context["drupal_multisite_smell"] = smell
```

`main()`, immediately after `invoke_hooks("site_post_dns")` (`:1456`), with the
emission gate extracted as a pure helper (finding of the spec review — the seam is
named here, not at plan time):

```python
probe_smell = site_context.get("drupal_multisite_smell", "")
if probe_smell != "":
    drush_smell = probe_smell
notice = no_primary_domain_notice(
    site, custom_domains, primary_domain, site_context.get("drupal_multisite", False)
)
if notice is not None:
    site_context.add_notice(notice)
```

`no_primary_domain_notice(site, custom_domains, primary_domain, is_multisite) ->
dict | None` is a NEW pure helper (module-level def in `psh/_legacy.py`, beside the I1
builders — the Spine's named-extraction rule: the emission has no seam above the
golden, and the goldens only exercise its gate-FALSE path). It owns the whole gate
(`len(custom_domains) > 1 and len(primary_domain) == 0 and site["framework"] !=
"wordpress_network" and not is_multisite`) and returns the notice dict (interior bytes
verbatim) or `None`. Its final module home is I13's call (it is core-and-staying-core;
ledger-noted like the I1 builders). The two seeding lines above have no seam and are
not golden-exercised (golden sites have ≤1 custom domain, so the probe never runs) —
they rest on inspection, accepted and ledger-noted (the I4 `HookDagError`-glue
precedent).

Hook-produced keys are amendment 2's machinery: DAG-declared, `.get()`-read, absent
when the gate fails or `[Check.drupal]` is disabled. Why this shape (exhaustive
alternatives considered): (a) moving the no-primary-domain
notice into the hook fails — the notice is generic (it fires for WordPress and unknown
frameworks too; CLAUDE.md: `no-primary-domain` remains in core); (b) an early in-place
rebind of `drush_smell` at `site_post_dns` fails — `stuff_gather_contract` would
overwrite it at `site_post_gather`, silently dropping a probe-only smell (a
`drush_php_script` PHP warning is plausibly probe-only, so this is a real row-loss, not
a D-i9-4-style theoretical); making the stuffer merge-aware bends "keys are stuffed just
before their phase" for no gain over (c) two explicitly produced keys read once by
`main()` — no engine change, no stuffer change, DAG-visible, byte-exact precedence
(probe → core-status → pm:list → UA, unchanged). These are the campaign's first
hook-produced keys, which the ledger records; CLAUDE.md's contract table gains a note
beneath the `site_post_dns` row.

**Documented consequence** (default-true keeps today's behavior): with
`[Check.drupal].enabled = false`, the probe never runs, so a Drupal *multisite* with >1
custom domains and no primary domain now gets the (info-severity) `no-primary-domain`
notice — the operator opted out of the probe that suppressed it. Ledgered, not guarded.

### D-i10-4: smell precedence — the D-i9-4 analysis; NO §8 amendment needed

`drush_smell` write order today: multisite probe (`:1412`) → core-status (`:1506`) →
pm:list (`:1530`) → UA (`:1765`); `composer_smell` has a single writer (`:1649`);
`wp_smell` is untouched by I10. Post-I10 order: probe (seeded by `main()` right after
`site_post_dns`) → core-status → pm:list (inside `gather_drupal`, threaded last-wins) →
UA (hook rebind during `site_post_gather`, after stuffing). **Identical in every
co-occurrence** — unlike I9's theme/OCP swap, no pair of writers changes relative
order, so no notice-csv value can diverge and §8 needs no amendment. `drush_smell`
joins `wp_smell` as a sanctioned mutate-during-phase key (mutator:
`check.umich.drupal_ua`; the hook does NOT declare `produces: ['drush_smell']` — the
D-i9-3 rule); B48's emission already reads `site_context["drush_smell"]` (I9 repoint),
so the rebind reaches it. CLAUDE.md's contract row and BOTH `psh/modules.py`
occurrences of "the one sanctioned mutate-during-phase key" (docstring `:275–279` and
inline comment `:289–292`) are updated to "two sanctioned (wp_smell, drush_smell)".

### D-i10-5: `check/drupal/` and `check/addon_updates/` package shapes

One module per check (D-i8-1); `check/drupal/__init__.py` registers in this order
(preserves today's intra-set notice order — probe, then PAPC before D7-EOL/tag1):

| Phase | Name | consumes | produces |
|---|---|---|---|
| `site_post_dns` | `check.drupal.multisite.check_multisite` | `['custom_domains', 'primary_domain']` | `['drupal_multisite', 'drupal_multisite_smell']` |
| `site_post_gather` | `check.drupal.papc.check_papc` | `['framework', 'drupal_modules']` | `[]` |
| `site_post_gather` | `check.drupal.d7_eol.check_d7_eol` | `['framework', 'drupal_version', 'drupal_modules']` | `[]` |

`check/addon_updates/__init__.py` registers one hook:

| Phase | Name | consumes | produces |
|---|---|---|---|
| `site_post_gather` | `check.addon_updates.table.check_add_on_updates` | `['add_on_updates']` | `[]` |

`papc`/`d7_eol` early-return unless `site_context["framework"].startswith("drupal")`
(the branch condition the code sat inside); `papc` and the tag1 check call
`sc.check_drupal_module(site["name"], site_context["drupal_modules"], …)` — the
contract's None/non-dict is handled by the builder's existing non-dict early return.
`d7_eol` fires only when `drupal_version.startswith("7.")` (contract: str, `"unknown"`
on failed fetch — which correctly does not match, same as today). `table.py` reads
`site_context["add_on_updates"]` (the same list object `main()` accumulated — stuffer
publishes it un-copied, pinned by `test_contract_registry.py`) plus `site["name"]`/
`site["id"]`; no-op when empty. The stray doubled quote in the Name column header
(`rt-data-header rt-plan""`, `:1849`) is **golden-rendered — moves byte-verbatim, do
not fix**. Config gates (§5, D-i8-6 shape, default true, skip message on disabled) and
sample-toml blocks:

```toml
[Check.drupal]
enabled = true          # PAPC-module, Drupal-7-EOL/tag1_d7es, multisite-probe checks

[Check.addon_updates]
enabled = true          # pending add-on (plugin/theme/package) updates table notice
```

Documented consequence: `[Check.addon_updates].enabled = false` removes the
`updates-addons` notice from reports and `--only-warn` output (operator opt-out;
default true preserves today's unconditional behavior — §5's relocation rule).

### D-i10-6: the Drupal UA check → `check/umich/` — a deliberate gating change

`drupal_ua.py` (`check_drupal_ua`), `site_post_gather`, `consumes ['framework',
'drupal_version']`, registered after `hummingbird` under the existing
`[UMich].enabled` gate. Gate mirror of today's placement (inside the D8+ `else`):
early-return unless `framework.startswith("drupal")` and
`not drupal_version.startswith("7.")` (a failed version fetch is `"unknown"` → the
check RUNS, exactly as today's `else` branch). Probes via `sc.drush_php_script`
(the column-0 PHP heredoc `:1739–1750` moves byte-verbatim), failure notices via
`sc.drush_error`, rebinds `site_context["drush_smell"]` on non-fatal stderr (D-i10-4),
emits the `drupal-ua` info notice on a non-U-M/template UA string.

**Behavior change (deliberate, ledgered — the D-i9-6 precedent):** today the UA check
runs **un-gated** — a non-U-M Drupal 8+ site is told to configure a
`…; UMich; https://…` user agent, which is factually wrong off-campus (CLAUDE.md lists
it under still-hardcoded U-M). After I10 it runs only when `[UMich].enabled`.
Consequences: for a non-U-M run the `drupal-ua`/`drupal-ua-check` notices and csv rows
no longer occur — NOT a §8 csv-*value* change (rows appear/disappear with config, the
cachecheck/D-i9-6 precedent); zero golden impact — but note the Drupal golden DOES run
the un-gated UA check today with a compliant fixture result and zero notice; post-I10
that fetch disappears from its run (§6). Invariant 3 moves in its
intended direction; CLAUDE.md's still-hardcoded-U-M list drops the entry.

### D-i10-7: named fix — the updatestatus `type in u` builtin bug

`:1614`: `"type": u["type"] if type in u else "package"` tests whether the **`type`
builtin** is a dict key — always False — so every D7 pm:updatestatus row renders
`package` even when Drupal reports a real type. Discovered during scope verification;
§12 "fits scope, <30 min → fix now, note in ledger". Fix in the moved `gather_drupal`:
`u["type"] if "type" in u else "package"`. Notice-*body* value only (the csv carries
`updates-addons,{num_updates}`); zero golden impact (the Drupal golden's fixture is
D8+, its add-on rows come from composer audit — §6). Test-first: RED on the old
expression with a `{"type": "module", …}` fixture entry asserting the table row says
`module`, not `package`.

### D-i10-8: named fix — composer-smell baked-in indentation (LEDGER I1 Obs. 4)

`build_smell_notices`' composer `message`/`text` literals (`:931–945`) carry 8 spaces
of accidental leading indentation on every interior line — the wp/drush siblings are
column-0 — so the rendered email/plaintext shows stray indentation (and the plaintext
START/END markers are indented). Discharge the I1 deferral as the builder moves:
de-indent the composer literal interiors to column-0, matching the siblings' byte
shape. NOT an Invariant-8 violation (that invariant locks deliberate column-0
literals; this one is the ledgered bug), NOT a csv change (csv embeds the smell text,
unchanged), zero golden impact (no golden renders any smell — CAMPAIGN §10's grep +
§6). Test-first: syrupy snapshots of all three smell-notice bodies pin the new bytes
(RED = snapshot mismatch against the indented form is impossible pre-creation, so the
RED is the unit assertion `not composer["message"].startswith("\n        ")` /
line-anchored equality with the sibling shape, shown failing on the old builder before
the move+fix commit).

### D-i10-9: ratchet — all new files born gated; no exclude-list edits

`check/drupal/`, `check/addon_updates/`, `check/umich/drupal_ua.py` are new files never
in `ruff-broad.toml`'s `extend-exclude` (the `check/umich/` entry was narrowed to the
two legacy siblings at I9), and `psh/gather.py` is already gated — so I10 deletes
NOTHING from the exclude list and adds nothing to it (I2–I7 precedent). **Pyright scope
stays `psh/` minus `_legacy.py`** (D-i8-7/D-i9-8 inherited: the hooks call
runtime-assigned `sc` attributes — now including `sc.drush_php_script`/
`sc.drush_error`). I11+ inherit.

### D-i10-10: `sc.drush_php_script` + `sc.drush_error` façade additions

The relocated multisite/UA checks need the drush-script wrapper and the drush
notice-builder; checks import only `sc` (Invariant 9). Two lines in the exposure block
(`:396–404`, block comment style), CLAUDE.md's runtime-exposed list, pinned by
`test_documented_sc_facade_names_exist`. `sc.drush` is NOT added — no relocated check
calls `drush()` (core-status/pm:list stay in the gather core); dead façade surface
otherwise (§17 Q4, the I9 `sc.wp` reasoning).

### D-i10-11: `stuff_gather_contract` docstring correction (LEDGER I9 obligation)

The docstring still claims the `*_version` values are `"unknown"` on a failed fetch —
true for Drupal only; WordPress yields `""` through the gateway (LEDGER I9 Deviations
4). Corrected while this increment touches nothing else in `psh/modules.py` beyond the
D-i10-4 comment updates (the CLAUDE.md table — the authoritative prose — was already
fixed at I9). Doc-only.

### D-i10-13: `Notice`-class adoption stays deferred

LEDGER I9 carried "Notice-adoption for extra-csv notices remains I10/I12". I10
passes, deliberately: every notice this increment touches carries extra csv fields
(`not-installed,{name}`, `turned-off,{name}`, `updates-addons,{num_updates}`,
`drupal-ua,{ua}`, the three smell csvs), which `Notice` cannot hold without the
reserved §6 field-set amendment, and taking that amendment here would widen the
campaign's second-largest increment for zero behavioral gain. Deferred to **I12/I14**
(PD#9: written here and re-ledgered at close — I12's spec author inherits it with the
annual-bill candidates).

### D-i10-12: ordering + gate analysis (the D-i8-3 way)

`find_modules` sorts: post-I10 `site_post_dns` registration order is
`check.cloudflare.cache`, `check.dns.*`, **`check.drupal.multisite`**,
`check.pantheon_cdn_change.*`; `site_post_gather` is **`check.addon_updates.table`**,
**`check.drupal.papc`**, **`check.drupal.d7_eol`**, `check.pantheon.updates`,
`check.pantheon.php_eol`, `check.umich.cloudflare_cms`, `check.umich.oidc_login`,
`check.umich.hummingbird`, **`check.umich.drupal_ua`**, `check.wordpress.papc`,
`.sessions`, `.ocp`, `.favicon`. The multisite hook's produced keys have no hook
consumer, so the DAG stays edgeless and registration order holds (§4).

Notice-insertion shifts (all within-tier only; §8 structure bar holds; B50's severity
sort is stable so cross-tier placement is unaffected; **zero golden impact — §6**):

- `multisite-check` (probe-failure alert): pre-phase today → mid-`site_post_dns` (after
  cloudflare/dns hook notices, before cdn_change's).
- `no-primary-domain` (info): pre-phase today → post-phase (after all `site_post_dns`
  hook notices).
- `updates-addons` (warning): post-phase today (after every `site_post_gather` hook
  notice) → FIRST in the phase (`addon_updates` sorts first).
- Drupal `papc`/`drupal7-eol`/`tag1` notices: pre-phase today (inline gather) →
  in-phase, but still before `pantheon.*`/`umich.*` output (`drupal` < `pantheon` —
  order among them preserved); they now land after `updates-addons` where they
  previously preceded it.
- `drupal-ua` (info): inline pre-phase today → late in the phase (after `hummingbird`,
  before `wordpress.*` — which never co-fires, framework-disjoint).
- `composer-update`/`core-status`/`pm-list`/`pm-updatestatus` failure notices
  (exhaustive): unchanged relative order (they move with the fetches and are emitted
  at the same point in the flow).

Subject-line consequence (informational, ledgered to make it deliberate — I9 shipped
the same class without comment): the subject takes the FIRST sorted notice's `short`
(`:2426–2428`), so for a production site with no alert whose first warning changes
under these shifts (e.g. a Drupal PAPC warning previously preceding `updates-addons`,
which now runs first), the email subject changes. Content of every notice is
unchanged; no golden is affected (each golden's leading notice is unmoved — §6).

Gate parity (canonical table — `--only-warn` reaches `site_post_gather`, so every
relocated check fires on only-warn exactly as its inline form did; `--update`/
`--import-older-metrics`/`--create-tables` never reach site phases; a per-site fatal
error skips remaining phases as today):

| Region | Today | Post-I10 | Only-warn output |
|---|---|---|---|
| B30 probe + B35 checks + UA | inline, before the `:2004` gate | phase hooks, before the gate | unchanged |
| B39 table | inline `:1825`, before the gate | `site_post_gather` hook | unchanged (present) |
| B48 smells | inline `:2374`, after the gate | **unchanged** (amendment 1) | unchanged (absent) |

## 3. Module shapes (imports; no cycles)

- `psh/gather.py`: gains `re` and widens the gateway import to `drush`, `drush_error`,
  `run_terminus`, `terminus` (alongside the existing `wp`, `wp_error`, `wp_eval`;
  NOT `drush_php_script` — D-i10-2); `json` + `html` for `build_smell_notices` (`html` already
  imported); call-time `escape_url` bridges inside `check_drupal_module` and
  `gather_drupal` (§1 non-scope). `_legacy.py` re-imports `check_drupal_module`,
  `gather_drupal`, `DrupalGather`, `build_smell_notices` (no cycle: `_legacy` →
  `psh.gather` → `psh.gateway`). Module docstring updated (the "moves here at I10"
  note becomes present tense; B48-builder note added).
- `check/drupal/*`: `import script_context as sc` only (multisite additionally uses
  nothing else; papc/d7_eol call `sc.check_drupal_module`, d7_eol's notice needs no
  `html`). No module-level mutable state (§3.4).
- `check/addon_updates/table.py`: `sc` + stdlib `html` (+ `rich.pretty.pprint` for the
  verbose preamble — the I9 `psh/gather.py` precedent; NOT stdlib pprint, the
  `d5c4bf8` lesson).
- `check/umich/drupal_ua.py`: `sc` only.
- `psh/modules.py`: comment/docstring edits only — the D-i10-11 `*_version` fix plus
  the two "one sanctioned mutate-during-phase key" occurrences (D-i10-4).
- `psh/_legacy.py`: region deletions, re-imports, D-i10-2/D-i10-3 threading, two
  façade lines. `check_drupal_module`'s and `build_smell_notices`' defs leave;
  `smtp_login` (`:322`) and the annual-bill builders (`:951+`) are untouched neighbors.

## 4. Deliverables

- **A** — `psh/gather.py` additions (`check_drupal_module`, `gather_drupal` incl.
  D-i10-7, `build_smell_notices` incl. D-i10-8) + `_legacy.py` deletions/re-imports/
  threading + façade lines (D-i10-10).
- **B** — `check/drupal/` package (D-i10-3/D-i10-5) + `main()`'s post-dns seeding and
  no-primary-domain move + sample-toml block.
- **C** — `check/addon_updates/` package (D-i10-5) + sample-toml block.
- **D** — `check/umich/drupal_ua.py` (D-i10-6) + `__init__.py` registration.
- **E** — `stuff_gather_contract` docstring (D-i10-11).
- **F** — tests per §7.
- **G** — docs: CLAUDE.md, CAMPAIGN.md amendments (header), README TODO (`mutates`),
  ledger entry, auto-memory.

## 5. Ratchet (§13) — expected findings, MUST be confirmed against real tool output

Predictions (PD#14 — run the tools; correct in the task report where reality differs):

- `C901`/`PLR0912`/`PLR0915` on `gather_drupal` (~200-line verbatim body) → noqa, no
  algorithmic redesign (§3.1 whole-file-coverage rule).
- `E712` on `sites_file["result"] == True` (moves to `multisite.py`) → rewrite
  `is True` with an equivalence note (the value is a JSON-decoded boolean — the PHP
  side emits literal `true`/`false`; `1 == True` vs `1 is True` divergence is
  unreachable).
- `F541` on `f"Migrate off Drupal 7 ASAP"` (`:1549`, → `d7_eol.py`) and
  `f"fix composer error"` (`:1631`, → `gather_drupal`) → drop the f-prefix (I6/I8/I9
  precedent).
- `PLC0206` on the two key-iterating dict loops (`for package in updates:` `:1596`,
  `for package in package_list:` `:1672`) → `.items()` rewrite (I6 precedent) unless
  the body's rebinding pattern makes noqa honester — implementer decides against real
  output, equivalence-argued either way.
- `PLW2901` on the `advisory = package_list[package][advisory]` loop-var rebind
  (`:1677`) → noqa, verbatim move.
- `PLR2004` on `len(t) == 4` (`:1687`) → noqa, verbatim move.
- `ERA001` on the commented-out `drush_smell` line (`:1591–1592`) → converted to the
  prose comment shown in D-i10-2 (the reason survives, the dead code does not — I5/I6
  deletion precedent, but here the comment carries load-bearing intent).
- `PLC0415` on the two new `escape_url` bridges → two-line noqa form (I9 lesson —
  the single-line form trips `I001`).
- `PLR0913` WILL fire on `check_drupal_module` (7 params vs ruff's default max-args 5;
  the 6-param sibling `check_wordpress_plugin` fired at I9 and carries the noqa,
  `psh/gather.py:38`) → noqa with the I9 reason (signature unchanged is a
  requirement).
- Orphan check in `_legacy.py`: expectation NONE (`html`, `re`, `json`, `pprint`,
  `semver`-already-gone — all retain users; `drush_php_script`/`drush_error` stay
  imported for the façade lines and `psh.*` test references).

## 6. Behavior bar (§8) application — golden-impact evidence

Verified 2026-07-22 against `tests/e2e/__snapshots__/*.ambr` and the fixture data:

- Body-string greps across all four goldens: `primary domain` 0, `Extended Support` 0,
  `user agent` 0, `reporting PHP code problems` 0, `is a Drupal multisite` 0,
  `needs to be installed`/`needs to be enabled` 0 — **none of the moved checks'
  notices render in any golden**, and the smell notices render in none (CAMPAIGN §10
  grep still 0).
- `pending add-on update` renders in **all four** goldens (2–3 hits each) — the B39
  notice is golden-load-bearing: its content (table rows, the stray `""` quote, the
  its.umich.edu link, plugin-then-theme row order) MUST be byte-preserved by the hook
  move. Its within-tier position is safe: it is the **only warning-tier notice in all
  four goldens** (`grep -c "26A0" *.ambr` → exactly 1 per golden; the
  `pantheon_cdn_change` notice is info-tier — `check/pantheon_cdn_change/notices.py:196`
  — and the cdn golden's `Action Recommended` subject comes from `updates-addons`
  itself; `Action Required` subjects in the other three come from the `no-domains`
  alert), so the stable three-bucket sort (`:2404–2408`) renders it identically
  wherever inside the flow it was inserted.
- The Drupal golden (`its-wws-test2`, D8+ fixtures) renders `updates-addons` from the
  composer-audit path — its `add_on_updates` entries carry list-valued `name`s and
  `new_version_url`s, so the audit collection in `gather_drupal` and the table
  rendering in `table.py` are both byte-pinned by that golden. The D-i10-7 fix cannot
  touch it (the `type in u` expression is on the D7 pm:updatestatus path only).
- Subprocess traffic: the WP/non-U-M/cdn goldens keep an identical fixture argv set
  (the gather fetches move, they do not change; the multisite probe fires only when
  `custom_domains` > 1, and every golden has ≤ 1 — the three plain goldens' fixtures
  are reduced to the platform domain, the cdn golden adds exactly one synthetic custom
  domain WITH primary set). The **Drupal golden loses one call**: today its D8+ path
  runs the un-gated UA check (`tests/fixtures/terminus-drupal/c17e10215ba09beb.json`,
  a compliant `…; UMich; …` UA → no notice); post-I10 `drupal_ua` is not registered
  (umich disabled), so that `drush php:script` call and its `=== Checking for Drupal
  user agent` banner disappear from the run — stdout-only (§8-free), the replay shim
  is keyed by argv so the now-unused fixture is harmless (NOT deleted — Invariant 10
  posture; noted in the ledger), and the rendered `.eml` is unaffected.
- `--only-warn` output unchanged (D-i10-12 gate table);
  `tests/e2e/test_only_warn_e2e.py` and `test_unknown_framework_e2e.py` stay green
  unmodified.

Therefore the four goldens MUST stay byte-identical (Invariant 1). stdout ordering
changes (banners/prints now firing at hook time) are §8-free. `-notices.csv` per-site
row order may shift per D-i10-12; structure may not; values change only via the two
named fixes (D-i10-7 notice-body-only; D-i10-8 body-only) and the D-i10-6 gating
change (rows appear/disappear with config, not a value change).

## 7. Tests (test-first at these seams)

**Seams (named per the Spine's spec bar):** the `gateway` conftest fixture
(`psh.gateway.run_terminus` — reaches `drush`/`drush_php_script`/`run_terminus`/
`terminus` inside `psh/gather.py` AND `sc.drush_php_script` inside hooks),
`sc.SiteContext` construction + direct hook invocation (the I8/I9 pattern), standalone
module loading via `tests/helpers/checkload.py`, `recording_console` (production
width where prints are asserted), syrupy snapshots for notice bodies, the pure
`build_smell_notices` builder, and the four e2e goldens as the end-to-end pin. No new
mock surface.

Integration tier (new files; patterns: `test_gather_wordpress.py`,
`test_check_wordpress*.py`, `test_check_umich_wp.py`):

- `test_gather_drupal.py` — `psh.gather.gather_drupal` via the `gateway` fixture +
  `sc.SiteContext`: D8+ happy path (version from core-status; `modules` passed
  through; composer dry-run parse → `package_updates` merge; audit advisories →
  add-on entries incl. severity-from-title split (`len(t) == 4`), `new_version_url`
  variants (`cve` path is dead — `package_updates` entries never carry `cve`; assert
  current behavior: advisory-link fallback), abandoned print); D7 happy path
  (pm:updatestatus mapping incl. `candidate_version`/`recommended`/`latest_version`
  fallbacks and `none: {project_status}`, **the D-i10-7 pin**: an entry with
  `"type": "module"` renders `module` — RED first on the old expression); fatal
  core-status → `core-status` notice + `"unknown"` version + results entry still
  written; fatal pm:list → `pm-list` notice; fatal pm:updatestatus →
  `pm-updatestatus` notice + no D7 add-on rows; composer dry-run fatal →
  `composer-update` alert; smells: core-status-then-pm:list last-wins,
  pm:updatestatus stderr NOT captured, composer stderr lands in `composer_smell`
  separately.
- `test_check_drupal_init.py` — gating: section absent → 3 hooks with the D-i10-5
  declarations in order; `enabled = false` → nothing + skip message; default-true
  proof.
- `test_check_drupal.py` — hook seams: multisite (gate variants → key absence; probe
  true/false → key values; fatal → `multisite-check` notice + keys still produced
  (False/""); stderr → `drupal_multisite_smell`; the unconditional print via
  `recording_console`); papc (delegation to `sc.check_drupal_module`; non-drupal → no
  call; None modules → builder early-return); d7_eol (7.x → `drupal7-eol` alert +
  tag1 delegation; 8.x/`"unknown"` → nothing).
- `test_check_addon_updates_init.py` / `test_check_addon_updates.py` — gating +
  declarations; empty list → no notice; plugin+theme rows → `updates-addons` warning
  with `{num_updates}` csv, singular/plural `short`, alternating row colors,
  list-valued `name` join + `new_version_url` anchor (the audit shapes), the same-
  object read (mutating the stuffed list before invoking shows in the table).
- `test_check_umich_drupal_ua.py` — seams: non-drupal / 7.x → no probe; compliant UA →
  none; template/`your-site` UA → `drupal-ua` info notice (csv carries the UA string);
  fatal probe → `drupal-ua-check` notice; non-dict result → the "Unexpected result"
  notice; stderr → `site_context["drush_smell"]` rebound (**the D-i10-4 pin**);
  registration: umich-enabled registers it after `hummingbird`, umich-disabled
  registers nothing (**the D-i10-6 gating-change proof**).
- `tests/unit/test_no_primary_domain_notice.py` — the D-i10-3 pure helper (the named
  extraction; no existing test at any tier covers this notice — verified,
  `grep -rln "no-primary-domain" tests/` is empty): gate-true + `is_multisite=False`
  → the notice dict (csv/short/message/text pinned, snapshot in
  `test_drupal_notice_render.py`); `is_multisite=True` → None; ≤1 custom domains →
  None; primary set → None; `framework == "wordpress_network"` → None. The two
  probe-smell seeding lines in `main()` have no seam and are not golden-exercised
  (golden sites have ≤1 custom domain, so the probe never runs) — they rest on
  inspection, accepted and ledger-noted (the I4 `HookDagError`-glue precedent); the
  halves they join are pinned separately (`test_check_drupal.py`'s produced-key pins;
  D-i10-4's smell pins).
- `test_drupal_notice_render.py` + `test_addon_updates_notice_render.py` +
  `test_umich_drupal_ua_notice_render.py` — syrupy snapshots of every relocated
  notice body (`check_drupal_module` not-installed/turned-off via `psh.gather`,
  drupal7-eol, composer-update, multisite-check, drupal-ua, updates-addons with
  representative D7-shaped and audit-shaped rows): the Invariant-8 forward byte pins.
- `test_smell_notice_render.py` — syrupy snapshots of all three smell bodies pinning
  the D-i10-8 de-indent (plus the unit RED described there).

Unit tier:

- `tests/unit/test_smell_notices.py` — existing file keeps passing via the `psh`
  re-import (substring assertions are indentation-safe); ADD the D-i10-8 shape
  assertions (composer interiors start at column 0, matching the drush sibling).
- `test_house_rules.py` — `drush_php_script`/`drush_error` join the documented-façade
  pin.
- `tests/unit/test_contract_registry.py` — unchanged (no CONTRACT edits); implementer
  verifies it stays green after the docstring edit.

**`test_hook_dag.py` MUST be extended, not assumed** (spec-review finding — PD#14):
its `ALL_PACKAGES` list is hardcoded and was last touched at I4 — it is **already
missing `check/pantheon` (I8) and `check/wordpress` (I9)**, so CLAUDE.md's "loads
every real check/plugin package" has been false for two increments (a discovered
task, ledgered: I8/I9 shipped this drift silently). I10 adds all four missing
packages (`pantheon`, `wordpress`, `drupal`, `addon_updates`) to `ALL_PACKAGES` — the
per-phase `got == names` assertion still holds (the DAG stays edgeless; nothing
consumes the probe keys) — and corrects the CLAUDE.md sentence or restores its truth.
This is the test that proves the campaign's first hook `produces` declarations
validate.

Existing suites, no weakening (implementer verifies): the four goldens +
`test_only_warn_e2e.py` + `test_unknown_framework_e2e.py` + `test_recommendation_e2e.py`
+ `test_abort_e2e.py` unchanged and green.

## 8. Acceptance (pasted at close, §16)

1. Full `./run-tests` (live tier if credentials present; else `--fast` + ledger note),
   all three gates, goldens byte-identical (`git diff <start-sha> --
   tests/e2e/__snapshots__/` empty; start = the commit before Deliverable A lands).
2. `uvx ruff check --config ruff-broad.toml psh/gather.py psh/modules.py check/drupal/
   check/addon_updates/ check/umich/__init__.py check/umich/drupal_ua.py` → clean;
   pyright gate 0 errors; no `ruff-broad.toml` edits in the increment diff.
3. Extracted-block byte-diff evidence for every moved literal region, pasted in the
   task reports; every difference is a named, sanctioned substitution (exhaustive
   classes: D-i10-7, D-i10-8, the two F541 f-drops, the E712 rewrite, and the
   relocation renames — `escape_url`/`check_drupal_module`/`drush_php_script`/
   `drush_error` to their `sc.` forms inside hook files, `site[...]` to
   `site_context["site"][...]`, locals to `site_context[...]` contract reads — the I9
   evidence convention; PLUS, added at Task 4's review (PD#14 — real tool output over
   the prediction): E713 ×2 in `check_drupal_module` (`not X in Y` → `X not in Y`),
   the D-i10-7 fix expressed as `u.get("type", "package")` (SIM401; behavior-identical
   to the conditional form), and the `advisory = None` init + scoped pyright ignore in
   the composer-audit loop (unreachable input; `None["link"]` would still raise
   loudly, PD#1-preserving)).
4. CAMPAIGN.md amendments applied (§3.1/§3.2/§3.3/§11 per the header); README TODO
   added; ledger entry appended (§12 template); CLAUDE.md/memory updated; both
   sample-toml blocks present.
5. Named pins green: D-i10-7 (`module` not `package`), D-i10-8 (composer de-indent),
   D-i10-4 (UA stderr reaches `site_context["drush_smell"]`), D-i10-6 (umich-disabled
   registers no `drupal_ua`), D-i10-3 (probe keys produced/absent per gate;
   `no_primary_domain_notice` gate cases); `test_hook_dag.py` runs with all four
   added packages in `ALL_PACKAGES`.

## 9. Acceptance results

Run at increment close (2026-07-22, closing docs commit; base = `eff1b40`). Per the Spine:
"Acceptance criteria = exact commands + expected output, run and pasted, never summarized."

### §8 item 1 — full `./run-tests --llm` (live tier present), all three gates, goldens byte-identical

A Terminus token is present (`ls ~/.terminus/cache/tokens/` → `markmont@umich.edu`) AND
the sandbox has a working network path to Pantheon this session (unlike I10 Task 4's
environment — `terminus site:info its-wws-test1` returned live JSON), so **the live tier
ran** (the 2 `tests/live/test_live_smoke.py` cases are included in the count below — no
`deselected` line appears, and `pytest tests/live/ -q` → `2 passed in 2.29s` confirms).

```
$ ./run-tests --llm
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
[... progress dots ...]
LLM_SUMMARY passed=991 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
--------------------------- snapshot report summary ----------------------------
107 snapshots passed.
991 passed, 1 skipped, 4 warnings in 46.92s
Linting (ruff, narrow PD set) ...
Linting (ruff-broad.toml, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
```

(The 1 skip is `test_db_credentials.py`'s `importorskip("MySQLdb")` on a sqlite-only
install. The two warnings beyond the docs ones are the pre-existing
`semver.compare` PendingDeprecationWarning — LEDGER I9, post-campaign cleanup — and the
`load_module` DeprecationWarning from the standalone check loader.)

Goldens byte-identical vs the increment base:

```
$ git diff eff1b40 -- tests/e2e/__snapshots__/ | wc -l
0
```

### §8 item 2 — ruff-broad spot-check clean; pyright 0; no `ruff-broad.toml` edits

```
$ uvx ruff check --config ruff-broad.toml psh/gather.py psh/modules.py check/drupal/ check/addon_updates/ check/umich/__init__.py check/umich/drupal_ua.py
All checks passed!

$ .venv/bin/pyright
0 errors, 0 warnings, 0 informations

$ git diff eff1b40 --stat -- ruff-broad.toml
(no output — untouched)
```

### §8 item 3 — extracted-block byte-diff evidence

Pasted per moved region in the four task reports (`.superpowers/sdd/task-{1,2,3,4}-report.md`),
each difference a named, sanctioned substitution class (SPEC §8.3, amended in place at Task
4's review to add: E713 ×2, the D-i10-7 fix as `u.get("type","package")` per SIM401, and the
`advisory = None` init + scoped pyright-ignore). Not re-pasted here (the task reports are the
canonical byte-diff record; the empty golden diff above is the end-to-end confirmation).

### §8 item 4 — docs/amendments applied

CAMPAIGN.md amendments 1 (§3.1/§3.2/§3.3/§11 row I10) and 2 (§4 hook-produced-key paragraph)
applied to the document this closing commit; README `mutates` TODO added; LEDGER I10 entry
appended (§12 template, I9 density); CLAUDE.md updated (module map, package lists, contract
table, sc-façade list, Testing block, still-hardcoded-U-M list, § Two mock seams); both
`sample-pantheon-sitehealth-emails.toml` blocks (`[Check.drupal]`, `[Check.addon_updates]`)
present since Tasks 2/3. **Memory: NOT updated at this commit** — §8 item 4's "memory" clause
was silently dropped from the original paste here (the whole-branch review's one Important
finding — the PD#14 checklist shape). Discharged post-final-review: `modularization-campaign`
(I10 status, hook-produced keys, the ALL_PACKAGES drift lesson) and `gateway-extraction`
(the two-binding `psh.gather.run_terminus` seam trap) both updated, LEDGER wording corrected
in the same follow-up commit.

### §8 item 5 — named pins green (all part of the 991 above)

- **D-i10-7** (`module` not `package`): `test_gather_drupal.py::test_d7_type_field_uses_dict_value_not_builtin`.
- **D-i10-8** (composer de-indent): `test_smell_notices.py::test_composer_literals_are_column_zero_like_siblings` + `test_smell_notice_render.py`.
- **D-i10-4** (UA stderr → `site_context["drush_smell"]`): `test_check_umich_drupal_ua.py`.
- **D-i10-6** (umich-disabled registers no `drupal_ua`): `test_check_umich_drupal_ua.py`.
- **D-i10-3** (probe keys produced/absent per gate; `no_primary_domain_notice` gate cases):
  `test_check_drupal.py` + `tests/unit/test_no_primary_domain_notice.py`.
- `test_hook_dag.py` runs with all four added packages in `ALL_PACKAGES` (I8/I9 drift repaired).
