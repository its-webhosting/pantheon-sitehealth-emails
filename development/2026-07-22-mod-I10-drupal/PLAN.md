# I10 — gather (Drupal half) + `check/drupal/` + `check/addon_updates/` + UA check → `check/umich/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move B30/B35/B39 out of `main()` — Drupal gather core to `psh/gather.py`,
the Drupal checks to the new `check/drupal/`, the add-on table to the new
`check/addon_updates/`, the U-M UA check to `check/umich/` — with the B48 smell-notice
*builder* joining `psh/gather.py` while its emission stays in `main()` (SPEC
amendment 1), and the campaign's first hook-produced keys
(`drupal_multisite`/`drupal_multisite_smell`, SPEC amendment 2).

**Architecture:** SPEC.md in this directory (D-i10-1…13); CAMPAIGN.md §3.1/§3.2/§4/§5.
Task order is load-bearing: the UA check leaves B35 first (it is inside the region
Task 4 guts — moving it first avoids an inline orphan), then `check/drupal/` +
`main()`'s post-dns rewiring, then `check/addon_updates/`, then the remaining gather
core + builder move. Every task's commit leaves the suite green and the goldens
byte-identical.

**Tech Stack:** Python 3.12, pytest (+syrupy), ruff two-config ratchet, pyright.

## Global Constraints

- Four e2e goldens byte-identical at every commit; NO golden/fixture refreshes
  (Invariants 1, 10). All four goldens render the `updates-addons` notice — its
  content (table rows, the stray `""` quote at the Name header, the its.umich.edu
  link, row order) is golden-load-bearing. The Drupal golden's add-on rows come from
  the composer-audit path (list-valued `name`s, `new_version_url`s). The now-unused
  UA fixture `tests/fixtures/terminus-drupal/c17e10215ba09beb.json` is NOT deleted.
- Moved notice-literal interiors move **byte-for-byte** (Invariant 8; `git diff -w` is
  not acceptable evidence). **This plan deliberately does not retype the literal
  bodies** — copy them from the quoted anchors in `psh/_legacy.py`; retyping is how
  bytes drift. Statement-level code may re-indent; lines *inside* triple-quoted
  literals may not. Exhaustive sanctioned differences (SPEC §8.3): D-i10-7
  (`"type" in u`), D-i10-8 (composer de-indent), F541 f-drops
  (`"Migrate off Drupal 7 ASAP"`, `"fix composer error"`), the E712 → `is True`
  rewrite, and the relocation renames (`escape_url`/`check_drupal_module`/
  `drush_php_script`/`drush_error` → `sc.` forms in hook files; `site[...]` →
  `site_context["site"][...]`; locals → `site_context[...]` contract reads).
- Checks import ONLY `script_context as sc` (Invariant 9; exception: `table.py` also
  imports stdlib `html` and `rich.pretty.pprint` — NOT stdlib pprint, the `d5c4bf8`
  lesson); no module-level mutable state (§3.4).
- Born-gated: `uvx ruff check --config ruff-broad.toml <new/touched gated files>`
  clean at every commit; NO `ruff-broad.toml` edits (SPEC D-i10-9); pyright scope
  unchanged (`psh/` minus `_legacy.py`).
- Test-first (`mattpocock-skills:tdd` — NOT superpowers:test-driven-development).
  For pure moves, RED = the module/hook does not exist yet (I8 precedent); the two
  named fixes (D-i10-7/D-i10-8) need REAL red on old behavior.
- Notice csv codes unchanged (exhaustive for this increment): `no-primary-domain`,
  `multisite-check`, `core-status`, `pm-list`, `pm-updatestatus`, `composer-update`,
  `not-installed,{name}`, `turned-off,{name}`, `drupal7-eol`, `drupal-ua,{ua}`,
  `drupal-ua-check`, `updates-addons,{num}`, `wp-smell`, `drush-smell`,
  `composer-smell`.
- Commit per task, each green (`./run-tests --fast` minimum; full suite at close).
  Baseline: 908 passed / 1 skipped / 2 deselected.
- Line numbers below were verified 2026-07-22 against the Task-1 starting state
  (HEAD `eff1b40`); later tasks shift them. **Locate every edit by the quoted anchor
  text, never by a stale number.**
- Purge stale `.superpowers/sdd/task-*-report.md` files before the first dispatch
  (LEDGER I1 process note).

---

### Task 1: Drupal UA check → `check/umich/drupal_ua.py` (+ drush façade names)

**Files:**
- Create: `check/umich/drupal_ua.py`
- Modify: `check/umich/__init__.py` (one registration, after `hummingbird`'s)
- Modify: `psh/_legacy.py` (delete the inline UA region; add 2 façade lines)
- Modify: `psh/modules.py` (the two "one sanctioned mutate-during-phase key"
  comments → two keys)
- Test: `tests/integration/test_check_umich_drupal_ua.py` (new),
  `tests/integration/test_umich_drupal_ua_notice_render.py` (new, snapshot),
  `tests/unit/test_house_rules.py` (façade names)

**Interfaces:**
- Consumes: contract keys `framework`, `drupal_version` (exist since I9);
  `sc.drush_php_script`, `sc.drush_error` (added HERE).
- Produces: hook `check.umich.drupal_ua.check_drupal_ua(site_context)` registered at
  `site_post_gather` with `consumes ['framework', 'drupal_version']`, `produces []`;
  rebinds `site_context["drush_smell"]` on non-fatal stderr. Task 4's gather-move
  relies on the UA region being GONE from the B35 `else:` block.

- [ ] **Step 1: Write the failing tests** — `tests/integration/test_check_umich_drupal_ua.py`,
  following `tests/integration/test_check_umich_wp.py`'s loading pattern
  (`tests/helpers/checkload.py` for the module, `reset_sc` + `gateway` fixtures,
  `sc.SiteContext`). Cases (SPEC §7): non-drupal framework → no `drush_php_script`
  call; `drupal_version` `"7.4"` → no call; compliant UA
  (`{"result": "Drupal (+https://drupal.org/); UMich; https://x.example.edu/"}`) →
  no notice; template UA (`…UMich; https://your-site…`) → `drupal-ua` info notice,
  csv `f"{site},drupal-ua,{ua}"`; fatal probe → `drupal-ua-check` notice; non-dict
  result → the `"Unexpected result from drush php-script."` notice; non-fatal stderr
  → `site_context["drush_smell"]` rebound (**D-i10-4 pin**); registration:
  umich-enabled config → hook present after `check.umich.hummingbird.…` in
  `sc.hooks["site_post_gather"]`, umich-disabled → absent (**D-i10-6 pin**,
  pattern: `test_umich_disabled_registers_neither_wp_check`). Snapshot test: the
  `drupal-ua` notice `message`/`text` via syrupy in a NEW
  `tests/integration/test_umich_drupal_ua_notice_render.py` (one render file per
  relocation set — the I9 `test_umich_wp_notice_render.py` precedent).

- [ ] **Step 2: Run to verify RED**

Run: `./run-tests --fast tests/integration/test_check_umich_drupal_ua.py -x -q`
Expected: FAIL/ERROR — `check/umich/drupal_ua.py` does not exist.

- [ ] **Step 3: Create `check/umich/drupal_ua.py`** — module docstring (campaign I10,
  from B35; U-M-gated since I10 — D-i10-6), `import script_context as sc` only:

```python
def check_drupal_ua(site_context):
    if not site_context["framework"].startswith("drupal"):
        return
    drupal_version = site_context["drupal_version"]
    if drupal_version is None or drupal_version.startswith("7."):
        return
    site = site_context["site"]
    live_site = site["id"] + ".live"
    sc.console.print(
        f"[bold magenta]=== Checking for Drupal user agent on {site['name']}:"
    )
    ua_check_script = """ ...COPY the column-0 heredoc verbatim from the anchor
`$result = 'unknown';` through `echo( json_encode( array( 'result' => "{$result}" ) ) );`
(psh/_legacy.py:1739–1750)... """
    ua, errors, fatal = sc.drush_php_script(
        live_site,
        ua_check_script,
    )
    ...remainder verbatim from the anchor `if fatal or ua is None:` (:1755) through
    the end of the drupal-ua add_notice (:1807), with EXACTLY these renames:
    drush_error( -> sc.drush_error(;  site_context.add_notices(...) unchanged;
    the smell line `drush_smell = errors` -> site_context["drush_smell"] = errors ...
```

  The notice dict interiors (`:1786–1806`) move byte-for-byte.

- [ ] **Step 4: Register + delete inline region + façade lines.**
  `check/umich/__init__.py`: add `from .drupal_ua import check_drupal_ua` to the
  import block (isort order) and, AFTER the `hummingbird` add_hook call:

```python
    sc.add_hook('site_post_gather', {'name': 'check.umich.drupal_ua.check_drupal_ua',
                                     'func': check_drupal_ua,
                                     'consumes': ['framework', 'drupal_version'],
                                     'produces': []})
```

  `psh/_legacy.py`: delete the inline region from the anchor
  `sc.console.print(\n                        f"[bold magenta]=== Checking for Drupal user agent on {site['name']}:"`
  (`:1736`) through the end of the `drupal-ua` `add_notice` call (`:1807`) — the last
  statements of the D8+ `else:` block; collapse leftover blank runs to the file's
  2-line standard (I5 precedent). Add to the exposure block (after the
  `sc.wp_error` line, `:403`, matching its comment style):

```python
sc.drush_php_script = drush_php_script  # check packages: drush php probes (check/drupal multisite, check/umich drupal_ua)
sc.drush_error = drush_error            # check packages: drush command-failure notices
```

  `psh/modules.py`: update BOTH "the one sanctioned mutate-during-phase key"
  occurrences (docstring `:275–279`, inline comment `:289–292`) to say two sanctioned
  keys (`wp_smell` — ocp/favicon; `drush_smell` — umich drupal_ua).
  `tests/unit/test_house_rules.py`: add `drush_php_script`, `drush_error` to the
  documented-façade-names pin.

- [ ] **Step 5: Run to verify GREEN**

Run: `./run-tests --fast`
Expected: baseline count + new tests, 0 failures; goldens byte-identical
(`git diff -- tests/e2e/__snapshots__/` empty — note the Drupal golden simply stops
making the UA call; its `.eml` is unaffected, SPEC §6).

- [ ] **Step 6: Ratchet gates**

Run: `uvx ruff check --config ruff-broad.toml check/umich/__init__.py check/umich/drupal_ua.py psh/modules.py && .venv/bin/pyright`
Expected: `All checks passed!` / `0 errors`.

- [ ] **Step 7: Commit** — `feat(campaign-I10): relocate the Drupal UA check to check/umich (U-M-gated)`

---

### Task 2: `check/drupal/` package + `main()` post-dns rewiring + hook-DAG test repair

**Files:**
- Create: `check/drupal/__init__.py`, `check/drupal/multisite.py`,
  `check/drupal/papc.py`, `check/drupal/d7_eol.py`
- Modify: `psh/_legacy.py` (delete B30 probe + no-primary emission + inline
  papc/d7eol/tag1; add `no_primary_domain_notice` helper + post-dns wiring)
- Modify: `sample-pantheon-sitehealth-emails.toml` (`[Check.drupal]` after
  `[Check.wordpress]`, `:111`)
- Modify: `tests/integration/test_hook_dag.py` (`ALL_PACKAGES` + drift repair)
- Test: `tests/integration/test_check_drupal_init.py`,
  `tests/integration/test_check_drupal.py`,
  `tests/unit/test_no_primary_domain_notice.py`,
  `tests/integration/test_drupal_notice_render.py` (all new)

**Interfaces:**
- Consumes: contract keys `custom_domains`, `primary_domain`, `framework`,
  `drupal_version`, `drupal_modules`; `sc.check_drupal_module` (existing façade,
  def still in `_legacy.py` until Task 4 — resolves either way),
  `sc.drush_php_script`/`sc.drush_error` (Task 1).
- Produces: hooks per SPEC D-i10-5's tables (names/consumes/produces EXACT);
  `site_context["drupal_multisite"]` (bool) + `site_context["drupal_multisite_smell"]`
  (str), ABSENT when the gate fails; `psh/_legacy.py` module-level
  `no_primary_domain_notice(site, custom_domains, primary_domain, is_multisite) ->
  dict | None` (importable as `psh.no_primary_domain_notice`).

- [ ] **Step 1: Write the failing tests.**
  `test_check_drupal_init.py` (pattern: `test_check_wordpress_init.py`): section
  absent → 1 hook at `site_post_dns` + 2 at `site_post_gather` with the exact
  D-i10-5 declarations in registration order; `enabled = false` → nothing + the skip
  message; `[Check]` absent entirely → registered (default-true proof).
  `test_check_drupal.py` (pattern: `test_check_wordpress.py`): multisite — ≤1
  custom domains / primary set / non-drupal → NO probe call and both keys ABSENT;
  probed `{"result": true}` → `drupal_multisite is True`; `{"result": false}` and
  junk results → `False`; fatal → `multisite-check` notice + keys produced
  (`False`, `""`); non-fatal stderr → `drupal_multisite_smell == errors`; the
  unconditional `is a Drupal multisite:` print via `recording_console`. papc —
  delegation to `sc.check_drupal_module` with
  `(site["name"], site_context["drupal_modules"], "pantheon_advanced_page_cache",
  "Pantheon Advanced Page Cache", "https://www.drupal.org/project/pantheon_advanced_page_cache", …)`;
  non-drupal → no call; None modules → builder early-return (no notice). d7_eol —
  `"7.1"` → `drupal7-eol` alert + tag1_d7es delegation; `"10.2"`/`"unknown"` →
  nothing.
  `test_no_primary_domain_notice.py` (unit; via the `psh` fixture): gate-true +
  `is_multisite=False` → dict with csv `f"{site['name']},no-primary-domain,"`;
  `is_multisite=True` → None; ≤1 custom domains → None; primary set → None;
  `framework == "wordpress_network"` → None.
  `test_drupal_notice_render.py`: syrupy snapshots — `psh.check_drupal_module`
  not-installed + turned-off variants, `drupal7-eol` body, `multisite-check` body
  (via the hook seam), the no-primary-domain body (via `psh.no_primary_domain_notice`).
  `test_hook_dag.py`: extend `ALL_PACKAGES`, keeping the tuple alphabetical within
  each base — insert `("check", "drupal", "hookdag_check_drupal"),` after the `dns`
  entry, `("check", "pantheon", "hookdag_check_pantheon"),` BEFORE the
  `pantheon_cdn_change` entry, and
  `("check", "wordpress", "hookdag_check_wordpress"),` after the `umich` entry
  (`addon_updates` joins in Task 3, first position). The pantheon/wordpress
  entries repair the I8/I9 drift (SPEC §7 — ledgered discovered task).

- [ ] **Step 2: Run to verify RED**

Run: `./run-tests --fast tests/integration/test_check_drupal_init.py tests/unit/test_no_primary_domain_notice.py -x -q`
Expected: FAIL/ERROR — package and helper do not exist.

- [ ] **Step 3: Create the package.** `check/drupal/__init__.py` (docstring: campaign
  I10, CAMPAIGN.md §3.2; gated `[Check.drupal].enabled` default TRUE):

```python
import script_context as sc

if sc.config.get('Check', {}).get('drupal', {}).get('enabled', True) is not False:
    from . import d7_eol, multisite, papc
    sc.add_hook('site_post_dns', {'name': 'check.drupal.multisite.check_multisite',
                                  'func': multisite.check_multisite,
                                  'consumes': ['custom_domains', 'primary_domain'],
                                  'produces': ['drupal_multisite', 'drupal_multisite_smell']})
    sc.add_hook('site_post_gather', {'name': 'check.drupal.papc.check_papc',
                                     'func': papc.check_papc,
                                     'consumes': ['framework', 'drupal_modules'],
                                     'produces': []})
    sc.add_hook('site_post_gather', {'name': 'check.drupal.d7_eol.check_d7_eol',
                                     'func': d7_eol.check_d7_eol,
                                     'consumes': ['framework', 'drupal_version', 'drupal_modules'],
                                     'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.drupal because it is disabled in the config')
```

  `multisite.py` per SPEC D-i10-3's sketch: the gate, then the probe verbatim from
  the anchor `sites_file, errors, fatal = drush_php_script(` (`:1398`) through the
  unconditional print (`:1421`), renames `drush_php_script(` → `sc.drush_php_script(`,
  `drush_error(` → `sc.drush_error(`, `drush_smell = errors` → a local
  `smell = errors` (init `smell = ""` above), `== True` → `is True` (sanctioned E712
  rewrite — the value is a JSON-decoded boolean), ending:

```python
    site_context["drupal_multisite"] = is_multisite
    site_context["drupal_multisite_smell"] = smell
```

  `papc.py`: framework gate + the `check_drupal_module` call verbatim from the anchor
  `site_context.add_notices(\n                    check_drupal_module(` (`:1533–1542`)
  with `check_drupal_module(` → `sc.check_drupal_module(`, `site["name"]` →
  `site_context["site"]["name"]`, `mods` → `site_context["drupal_modules"]`.
  `d7_eol.py`: framework gate + `if not site_context["drupal_version"].startswith("7."): return`
  guard (None unreachable for drupal frameworks — contract guarantees str), then the
  `drupal7-eol` add_notice verbatim (`:1544–1566`, interiors byte-locked, drop the
  `short` f-prefix — sanctioned F541) and the tag1 delegation (`:1567–1576`, same
  renames as papc).

- [ ] **Step 4: Rewire `main()` + helper + toml.** In `psh/_legacy.py`:
  (a) add module-level helper below `build_smell_notices` — the gate lifted verbatim
  from `:1391–1395` + `:1422`, the dict copied byte-for-byte from `:1423–1450`:

```python
def no_primary_domain_notice(site, custom_domains, primary_domain, is_multisite):
    """Return the no-primary-domain info notice dict, or None when it does not apply
    (BLOCKMAP B30; extracted at campaign I10 -- SPEC D-i10-3)."""
    if (
        len(custom_domains) > 1
        and len(primary_domain) == 0
        and site["framework"] != "wordpress_network"
        and not is_multisite
    ):
        return { ...the dict from the add_notice call, interiors verbatim... }
    return None
```

  (b) delete the whole inline block `:1391–1450` (`if (` gate, probe, `if not
  is_multisite:` emission); (c) immediately after
  `sc.invoke_hooks("site_post_dns", site_context)` insert the SPEC D-i10-3 wiring
  (seeding + helper call, code verbatim from the SPEC); (d) delete the inline papc
  call (`:1533–1542`), the d7-eol notice + tag1 block (`:1543–1576`), and the
  relocated-checks comment `:1577–1579` gains a sibling line for I10 (or is replaced
  by one noting papc/d7-eol/tag1 moved to `check/drupal/` — match the I9 comment
  style at `psh/gather.py:195–198`). `sample-pantheon-sitehealth-emails.toml`: add
  after the `[Check.wordpress]` block:

```toml
[Check.drupal]
enabled = true          # PAPC-module, Drupal-7-EOL/tag1_d7es, multisite-probe checks
```

- [ ] **Step 5: Run to verify GREEN**

Run: `./run-tests --fast`
Expected: all green; goldens byte-identical (`git diff -- tests/e2e/__snapshots__/`
empty — golden sites have ≤1 custom domain, so probe and emission both no-op).

- [ ] **Step 6: Ratchet gates**

Run: `uvx ruff check --config ruff-broad.toml check/drupal/ && uvx ruff check . && .venv/bin/pyright`
Expected: clean / clean (narrow set over the tree) / `0 errors`.

- [ ] **Step 7: Commit** — `feat(campaign-I10): check/drupal package, hook-produced multisite keys, no-primary-domain helper`

---

### Task 3: `check/addon_updates/` package (B39 → hook)

**Files:**
- Create: `check/addon_updates/__init__.py`, `check/addon_updates/table.py`
- Modify: `psh/_legacy.py` (delete the B39 region incl. verbose preamble)
- Modify: `sample-pantheon-sitehealth-emails.toml` (`[Check.addon_updates]` after
  `[Check.drupal]`)
- Modify: `tests/integration/test_hook_dag.py` (`ALL_PACKAGES` += addon_updates)
- Test: `tests/integration/test_check_addon_updates_init.py`,
  `tests/integration/test_check_addon_updates.py`,
  `tests/integration/test_addon_updates_notice_render.py` (all new)

**Interfaces:**
- Consumes: contract key `add_on_updates` (same-object publish, I9);
  `sc.escape_url` (existing façade).
- Produces: hook `check.addon_updates.table.check_add_on_updates(site_context)` at
  `site_post_gather`, `consumes ['add_on_updates']`, `produces []`. Emits the
  golden-rendered `updates-addons` notice — byte-parity is the whole game.

- [ ] **Step 1: Write the failing tests.** `test_check_addon_updates_init.py`:
  gating trio (absent/false/`[Check]`-absent), declaration pin, registration at
  `site_post_gather`. `test_check_addon_updates.py`: empty list → no notice, no
  print; plugin+theme dict rows → `updates-addons` warning, csv
  `f"{site},updates-addons,{num}"`, plural/singular `short`; alternating
  `#fff`/`#CCCFCA` row backgrounds; audit-shaped rows (list-valued `name` joined
  with severity upper-cased, `new_version_url` rendered as anchor via
  `sc.escape_url`); same-object pin (mutate the stuffed list, then invoke — the
  table reflects the mutation). `test_addon_updates_notice_render.py`: syrupy
  snapshots of the notice body for a plugin/theme pair AND an audit-shaped row
  (D7-shaped `type` row included).

- [ ] **Step 2: Run to verify RED**

Run: `./run-tests --fast tests/integration/test_check_addon_updates_init.py -x -q`
Expected: FAIL/ERROR — package does not exist.

- [ ] **Step 3: Create the package.** `__init__.py` — same shape as Task 2's, one
  registration (`check.addon_updates.table.check_add_on_updates`,
  `consumes ['add_on_updates']`, `produces []`), skip message
  `Skipping check.addon_updates because it is disabled in the config`. `table.py` —
  docstring (campaign I10, B39), imports `html`, `rich.pretty.pprint`, `sc`:

```python
def check_add_on_updates(site_context):
    site = site_context["site"]
    add_on_updates = site_context["add_on_updates"]
    if sc.options.verbose:
        sc.console.print(f"[bold yellow]=== Add-on updates for {site['name']}:")
        pprint(add_on_updates)
    num_updates = len(add_on_updates)
    if num_updates > 0:
        ...body verbatim from the anchor `update_table_rows = ""` (:1830) through the
        end of the add_notice call (:1900): renames escape_url( -> sc.escape_url(,
        site["name"]/site["id"] -> site["name"]/site["id"] via the local `site` above
        (no textual change inside literals); table-row/bullet f-string interiors and
        the notice dict interiors byte-locked (incl. the stray `rt-plan""` quote)...
```

  Then delete the B39 region from `psh/_legacy.py` — anchor `if sc.options.verbose:\n
  sc.console.print(f"[bold yellow]=== Add-on updates for` (`:1825`) through the
  add_notice close (`:1900`) — leaving the `# TODO: Warn if no Autopilot` line
  (`:1902`) in place. Extend `ALL_PACKAGES` with
  `("check", "addon_updates", "hookdag_check_addon_updates"),` (sorted position:
  first).  `sample-pantheon-sitehealth-emails.toml`: add after `[Check.drupal]`:

```toml
[Check.addon_updates]
enabled = true          # pending add-on (plugin/theme/package) updates table notice
```

- [ ] **Step 4: Run to verify GREEN — the goldens are the real gate here**

Run: `./run-tests --fast`
Expected: all green; `git diff -- tests/e2e/__snapshots__/` EMPTY. All four goldens
render this notice; any byte drift in the moved literals shows up here first
(Global Constraints: it is the only warning-tier notice in every golden, so its
within-phase insertion shift cannot reorder anything).

- [ ] **Step 5: Ratchet gates**

Run: `uvx ruff check --config ruff-broad.toml check/addon_updates/ && .venv/bin/pyright`
Expected: clean / `0 errors`.

- [ ] **Step 6: Commit** — `feat(campaign-I10): check/addon_updates package (B39 add-on table as a hook)`

---

### Task 4: `psh/gather.py` Drupal half + smell builder + the two named fixes

**Files:**
- Modify: `psh/gather.py` (`DrupalGather`, `gather_drupal`, `check_drupal_module`,
  `build_smell_notices`; docstring; imports)
- Modify: `psh/_legacy.py` (delete the moved defs + B35 gather region; re-imports;
  threading)
- Modify: `psh/modules.py` (`stuff_gather_contract` docstring — D-i10-11)
- Test: `tests/integration/test_gather_drupal.py`,
  `tests/integration/test_smell_notice_render.py` (new);
  `tests/unit/test_smell_notices.py` (D-i10-8 shape assertions added)

**Interfaces:**
- Consumes: `psh.gateway.drush/drush_error/run_terminus/terminus` (NOT
  `drush_php_script` — D-i10-2/F401); Task 1's UA deletion and Task 2's check
  deletions (the B35 region is now gather-only).
- Produces: `DrupalGather(drupal_version: str, modules, add_on_updates: list,
  drush_smell: str, composer_smell: str, results_entry: dict)` NamedTuple;
  `gather_drupal(site, live_site, site_context) -> DrupalGather`;
  `check_drupal_module` + `build_smell_notices` importable as `psh.gather.*` AND
  (re-import) `psh.*`; `main()`'s Drupal branch = the SPEC D-i10-2 threading.

- [ ] **Step 1: Write the failing tests.**
  `test_gather_drupal.py` (pattern: `test_gather_wordpress.py`; `gateway` fixture +
  `sc.SiteContext`): D8+ happy path (version passthrough, `modules` passthrough,
  dry-run parse → audit advisory rows incl. severity-from-title `len(t) == 4` split
  and advisory-link fallback for unknown new_version, abandoned print); D7 happy
  path (`candidate_version`/`recommended`/`latest_version` fallbacks,
  `none: {project_status}`, **D-i10-7 pin**: entry with `"type": "module"` yields a
  row with `"type": "module"` — RED procedure fixed here, not implementer's choice:
  in Step 3, land the move with the OLD `type in u` expression first, run this test
  to capture the RED on the moved function, then apply the one-token fix and rerun
  GREEN — both runs quoted in the task report, all inside Task 4's single commit);
  fatal core-status → `core-status` notice + `"unknown"` + results entry; fatal
  pm:list → `pm-list` notice; fatal pm:updatestatus → `pm-updatestatus` notice + no
  D7 rows; fatal dry-run → `composer-update` alert; smells (core-status/pm:list
  last-wins; updatestatus stderr NOT captured; composer stderr separate).
  `test_smell_notice_render.py`: syrupy snapshots of all three smell bodies.
  `test_smell_notices.py` additions (**D-i10-8 RED**, must fail on the CURRENT
  builder before the move):

```python
def test_composer_literals_are_column_zero_like_siblings(psh):
    notices = psh.build_smell_notices("s", "", "d", "c")
    drush, composer = notices
    assert not composer["message"].startswith("\n        ")
    assert composer["message"].splitlines()[1].startswith("<p>The <code>composer</code>")
    assert composer["text"].splitlines()[1].startswith('The "composer" command')
```

- [ ] **Step 2: Run to verify RED**

Run: `./run-tests --fast tests/unit/test_smell_notices.py -q` (D-i10-8 assertion
FAILS on the indented literals) and
`./run-tests --fast tests/integration/test_gather_drupal.py -x -q`
(ERROR — `psh.gather.gather_drupal` does not exist).

- [ ] **Step 3: The move.** In `psh/gather.py`: widen the gateway import
  (`from psh.gateway import drush, drush_error, run_terminus, terminus, wp, wp_error,
  wp_eval`), add `import re`, `import json`; add `DrupalGather` (fields + comments
  per SPEC D-i10-2) beside `WordPressGather`; move `check_drupal_module` verbatim
  below `check_wordpress_plugin` (call-time `escape_url` bridge — copy the 2-line
  form from `check_wordpress_plugin:46–48`); build `gather_drupal` from the B35
  anchors: banner (`=== Checking Drupal modules for`), core-status block, version
  derivation, `results_entry`, pm:list block, D7 `pm:updatestatus` block (with the
  D-i10-7 fix `"type" in u` and the ERA001 comment → prose:
  `# pm:updatestatus stderr is deliberately not captured as a smell -- it always`
  `# contains verbose progress output.`), D8+ composer dry-run + parse + audit
  blocks (drop the `f` on `"fix composer error"`), returning the NamedTuple; move
  `build_smell_notices` verbatim EXCEPT the composer literals de-indented to
  column-0 (D-i10-8 — match the drush block's shape exactly). In `psh/_legacy.py`:
  delete the moved defs (`check_drupal_module` `:270–319`, `build_smell_notices`
  `:871–948`) and the B35 gather region; extend the existing `from psh.gather
  import …` re-import line with `DrupalGather, build_smell_notices,
  check_drupal_module, gather_drupal`; replace the branch body with the SPEC
  D-i10-2 threading (verbatim from the SPEC). Update `psh/gather.py`'s module
  docstring (Drupal half now here; B48 builder note; drop "moves here at I10").
  Fix `stuff_gather_contract`'s docstring in `psh/modules.py` (WP `""` vs Drupal
  `"unknown"` — D-i10-11).

- [ ] **Step 4: Run to verify GREEN**

Run: `./run-tests --fast`
Expected: all green (existing `test_smell_notices.py` substring tests unaffected;
`test_wrappers.py`'s `psh.drush_php_script`/`psh.drush_error` still resolve);
`git diff -- tests/e2e/__snapshots__/` EMPTY (the Drupal golden's composer-audit
add-on rows byte-identical through the move).

- [ ] **Step 5: Ratchet gates + orphan check**

Run: `uvx ruff check --config ruff-broad.toml psh/gather.py psh/modules.py && uvx ruff check . && .venv/bin/pyright`
Expected: clean ×2 / `0 errors`. Confirm SPEC §5's predictions against real output in
the task report (C901/PLR0912/PLR0915 on `gather_drupal`; PLR0913 on
`check_drupal_module`; PLC0206/PLW2901/PLR2004 in the audit region; no F401 —
`drush_php_script` not imported). Grep-verify `_legacy.py` orphans: expectation NONE.

- [ ] **Step 6: Commit** — `feat(campaign-I10): move the Drupal gather core and smell builder into psh/gather.py`

---

### Task 5: closing — docs, amendments, ledger, acceptance

**Files:**
- Modify: `CLAUDE.md`, `development/2026-07-17-modularization-campaign/CAMPAIGN.md`,
  `README.md`, `development/2026-07-17-modularization-campaign/LEDGER.md`,
  `development/2026-07-22-mod-I10-drupal/SPEC.md` (§9 acceptance paste), auto-memory.

- [ ] **Step 1: CAMPAIGN.md amendments** (SPEC header, both user-approved):
  §3.2 `check/addon_updates/` row → B39 only + B48-emission note; §11 row I10
  likewise; §3.1 `psh/gather.py` row gains `build_smell_notices` +
  `check_drupal_module`… (Drupal half); §3.3 gains the B48 emission call; §4 gains
  the hook-produced-key paragraph (amendment 2, text per SPEC).
- [ ] **Step 2: README TODO** — the `mutates` DAG extension (one sentence of context:
  orders smell-notice consumers after in-place mutators; declined in-campaign,
  user decision at I10).
- [ ] **Step 3: CLAUDE.md** — module map (psh/gather Drupal half + builder), package
  lists (`check/drupal`, `check/addon_updates`, `check/umich` drupal_ua), contract
  table (drush_smell mutable; hook-produced-keys note under `site_post_dns`), façade
  list (+`sc.drush_php_script`, `sc.drush_error`), Testing section (new suites;
  `test_hook_dag.py` ALL_PACKAGES truth restored), still-hardcoded-U-M list
  (UA check leaves; `updates-addons` its.umich.edu link joins the generic-package
  half).
- [ ] **Step 4: Ledger entry** (§12 template) — moved blocks; the two amendments;
  D-i10-6 gating change; hook-produced keys; the I8/I9 `test_hook_dag.py` drift
  discovered+fixed; the unused UA fixture note; D-i10-13 Notice deferral to I12/I14;
  the seeding-lines-rest-on-inspection note; open questions for I11.
- [ ] **Step 5: Full acceptance run** — `./run-tests --llm` (live tier if
  `ls ~/.terminus/cache/tokens/` shows a token, else `--fast` + ledger note); paste
  outputs into SPEC §9 per SPEC §8's five items; `git diff <increment-base> --
  tests/e2e/__snapshots__/` empty.
- [ ] **Step 6: Update auto-memory** (modularization-campaign note: I10 done; new
  facts: hook-produced keys exist; test_hook_dag drift lesson).
- [ ] **Step 7: Commit** — `docs(campaign-I10): close the drupal/addon_updates increment` (includes this dev folder).
