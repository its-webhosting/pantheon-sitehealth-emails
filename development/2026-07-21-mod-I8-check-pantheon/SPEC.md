# SPEC — Increment I8: `check/pantheon/` (frozen, live-env, upstream-updates, PHP-EOL checks)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I8 (B19, B21, B38, B41). Tier-2 assignment: §3.2 row `check/pantheon/`
(frozen + no-live-env at `site_pre`; updates + PHP EOL at `site_post_gather`). Config:
§5 (the `[Check.pantheon]` example is "exhaustive for `check/pantheon/`"; default
**true**). Contract key: §4 ("`envs` (I8, at `site_pre`)"). What stays in `main()`: §3.3.
Data-fetch rule: §3.2 tail ("a check MAY fetch its own data through `sc` gateway wrappers
when the data is check-specific (e.g. `upstream:updates:list`); data used by core *and*
checks is published through the contract instead (e.g. `envs`)"). Obligations: §7.
Behavior bar: §8. Invariants: §9 (esp. 1, 3, 8, 9, 11). Ratchet: §13.

**Carried obligation this spec discharges** (LEDGER I7 "Open questions for I8" =
LEDGER I1 Obs. 2): the `php_version < "8.2"` string comparison and the KeyError when
`envs["live"]` has no `php_version` key — B41 moves this increment, so both are fixed in
its new home, test-first (D-i8-4). The I1-extracted `build_php_eol_notice`
(`psh/_legacy.py:1011–1066`) travels to `check/pantheon/` per LEDGER I1's schedule
("php-eol → I8").

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I7), `CLAUDE.md`
(§ Plugin / check module system, § Per-site report pipeline, § Testing), `BLOCKMAP.md`
rows B19–B21, B38–B42, `prompts/directives.md`, `prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's)

- **Move set** — the four notice-emitting regions leaving `main()` (B19 frozen, B21's
  initialized-False branch, B38 upstream updates, B41 PHP EOL) plus the
  `build_php_eol_notice` def.
- **The guards** — B21's three control-flow outcomes that stay in `main()`: the
  fatal/undecodable `continue`, the missing-live `sys.exit`, and (unchanged, B20) the
  unknown-plan `sys.exit`.
- **The package** — the new `check/pantheon/` check package (Tier 2, §3.2).

## 1. Scope (exhaustive) and non-scope

In scope (current `psh/_legacy.py` lines, verified 2026-07-21):

1. **New package** `check/pantheon/` (D-i8-1): `__init__.py` (config-gated hook
   registration) + `frozen.py`, `live_env.py`, `updates.py`, `php_eol.py`. Four hooks:
   `site_pre` frozen + live-env, `site_post_gather` updates + PHP EOL — registered in
   that statement order (D-i8-3).
2. **Move** out of `main()`, bodies verbatim except the named fixes (D-i8-4/D-i8-5) and
   ratchet dispositions (§5): B19 (`:1403–1430`, frozen console print + `frozen` notice),
   B21's initialized-False branch (`:1461–1485`, console ERROR + `no-live-env-but-paid-plan`
   notice), B38 (`:2320–2487`, banner print + `terminus("upstream:updates:list")` +
   `updates-info`/`updates-warning`/`updates-alert` notices + non-list error print),
   B41 (`:2566–2570`, the `build_php_eol_notice` call + comment). Column-0 `f"""`
   interiors move byte-for-byte (Invariant 8; extracted-block diff pasted empty in the
   task report, I2 precedent).
3. **Move** `build_php_eol_notice` (`:1011–1066`) → `check/pantheon/php_eol.py`, with
   the two D-i8-4 fixes. Deleted from `psh/_legacy.py`; **no re-import** (unlike
   I2–I7's moves, nothing in `_legacy.py` calls it after the move — the hook does; the
   one test file repoints, §7-Tests).
4. **Contract key `envs`** at `site_pre` (§4): `CONTRACT["site_pre"] = ("envs",)`,
   a `stuff_envs_contract()` stuffer in `psh/modules.py` (sibling of
   `stuff_traffic_contract`/`stuff_gather_contract` — core-produced key, D-i8-2),
   called in `main()` immediately before `sc.invoke_hooks("site_pre", …)` (`:1503`),
   the `PHASES` tuple's `site_pre` comment updated, CLAUDE.md table row, and the
   `test_contract_registry.py` pin.
5. **Config**: `[Check.pantheon]` with `enabled` defaulting **true** (§5); registration
   guard in `__init__.py` (D-i8-6); documented block added to
   `sample-pantheon-sitehealth-emails.toml`.
6. **Ratchet** (§13): `ruff-broad.toml`'s wholesale `"check/"` exclude is replaced by
   the four grandfathered packages (`check/cloudflare/`, `check/dns/`,
   `check/pantheon_cdn_change/`, `check/umich/`), so the package is born gated
   (D-i8-7; pyright scope unchanged — see D-i8-7 for why).
7. **New tests** (test-first, `mattpocock-skills:tdd`) per §7-Tests; the existing
   `tests/unit/test_php_eol_notice.py` repoints to the builder's new home.
8. **Docs**: CLAUDE.md (contract table `site_pre` row; `find_modules` package list;
   check-package descriptions; key-flags `--only-warn` note unchanged), ledger entry,
   auto-memory. README only if a discovered task demands it.

NOT in scope:

- **The guards stay in `main()`** (§3.3 site-loop skeleton; I6 D-i6-1 / I7 D-i7-1
  reading): the `terminus("env:list", …)` call itself (`:1443–1448` — core fetches
  `envs` because core gates on it, §3.2 tail), the fatal `continue` (`:1449–1454`),
  the missing-live `sys.exit` (`:1455–1460`), B20's unknown-plan `sys.exit`, and the
  `# Metrics for an uninitialized live environment…` comment (`:1487`).
- **B39 add-on updates** (`:2489–2564`): I10 (`check/addon_updates/`). It re-initializes
  its own `num_updates`/`update_table_rows`/`update_bullet_list`, so B38's departure
  leaves it whole (implementer grep-verifies no B38 local is read after `:2487`).
- **B40** is already deleted (I1). The `# TODO: Warn if no Autopilot` marker (`:2572`)
  stays in `main()` (BLOCKMAP §9 in-code TODO, not I8's).
- **`Notice`-class adoption** for any of the four notices: all stay legacy dicts
  (LEDGER I3 candidates remain I10/I12; `updates-*` csv rows carry extra fields, which
  `Notice` cannot hold without the reserved §6 amendment).
- **U-M copy split**: the frozen/no-live-env/updates bodies embed its.umich.edu /
  procurement links today, un-gated (BLOCKMAP classifies B19 "generic (U-M link in
  body)"). They move **verbatim** — not NEW un-gated U-M content (Invariant 3 bars
  additions; §3.2 assigns these to `check/pantheon/`, not `check/umich/`). De-U-M-ifying
  them is post-campaign/I14 work; CLAUDE.md's still-hardcoded-U-M list gains them
  (docs task) so the debt is visible.
- No golden/fixture refreshes (Invariants 1, 10); no new `sc` façade names (hooks use
  the existing `sc.console`/`sc.terminus`); no `-results.json`/`-notices.csv`/
  `-run.json` structure change (§8).
- No `_legacy.py` import removals beyond what this change orphans (I3 rule; expectation:
  `datetime`/`pprint`/`escape` all have other users — implementer verifies with grep,
  removes only true orphans).

## 2. Architecture decisions

### D-i8-1: package shape — one module per check

`check/pantheon/__init__.py` registers hooks and imports siblings (the
`check/cloudflare/`/`check/umich/` convention); logic lives in `frozen.py`,
`live_env.py`, `updates.py`, `php_eol.py` so each is standalone-loadable by the tests
(SourceFileLoader / `tests/helpers/checkload.py`, the existing per-module pattern).
Hook functions take the `SiteContext` and read `site_context["site"]` /
`site_context["envs"]`; they import **only** `sc` (Invariant 9). `updates.py` fetches
its own data via `sc.terminus("upstream:updates:list", f"{site['id']}.live")` — §3.2
names exactly this command as the check-specific-fetch example. Hook names/declarations:

| Phase | Name | consumes | produces |
|---|---|---|---|
| `site_pre` | `check.pantheon.frozen.check_frozen_site` | `[]` | `[]` |
| `site_pre` | `check.pantheon.live_env.check_live_env` | `['envs']` | `[]` |
| `site_post_gather` | `check.pantheon.updates.check_upstream_updates` | `[]` | `[]` |
| `site_post_gather` | `check.pantheon.php_eol.check_php_eol` | `['envs']` | `[]` |

`check_php_eol` consuming `envs` (first produced at `site_pre`) from `site_post_gather`
is the §4-condition-4 legal direction (earlier phase is fine).

### D-i8-2: core stuffs `envs`; the stuffer lives in `psh/modules.py`

`envs` is used by core (the guards) *and* checks (live-env, PHP EOL), so per §3.2 it is
published through the contract, fetched once by `main()` where it is today. The stuffer
sits beside `stuff_traffic_contract`/`stuff_gather_contract` (core-stuffed keys live in
`psh/modules.py`; producer-module stuffers like `stuff_dns_contract`/
`stuff_plans_contract` are for keys a moved module computes — `envs` has no such module
until I9's `psh/gather.py`, and §3.1 assigns it nowhere else):

```python
def stuff_envs_contract(site_context, envs) -> None:
    site_context["envs"] = envs
```

Contract semantics (CLAUDE.md table row): `envs` — dict, the `terminus env:list` JSON
keyed by environment id (`dev`/`test`/`live`/multidevs) with fields
`id, created, domain, connection_mode, locked, initialized, php_version,
php_runtime_generation`; `main()`'s guards ensure `envs["live"]` exists with an
`initialized` key before any site phase fires; **`php_version` is NOT guaranteed
present** (the D-i8-4 defect class). Never `None`/empty when a phase fires (a failed
fetch skips the site).

Flow (PD#8) — where each moved emission lands relative to today:

```
main() per site:  resolve plan → Sandbox skip → SiteContext
   [B19 frozen notice ──────────────┐ moves]
   B20 unknown-plan sys.exit (stays) │
   B21 env:list fetch (stays) ─ guards (stay) ─ [initialized-False notice ─┐ moves]
   traffic gather / --update / --import continues (stay)                   │
   stuff_envs_contract(site_context, envs)   ◄── NEW                       │
   invoke_hooks("site_pre") ──► pantheon.frozen ◄─┘  pantheon.live_env ◄───┘
                                then umich.sitelens (unchanged order, D-i8-3)
   … site_post_traffic … site_post_dns … gather …
   stuff_gather_contract → invoke_hooks("site_post_gather")
        ──► pantheon.updates ◄─[B38 moves]  pantheon.php_eol ◄─[B41 moves]
            then umich.cloudflare_cms
   B39 add-on updates (stays, I10) → B42 --only-warn gate → …
```

### D-i8-3: notice ordering — preserved at `site_pre`, shifted at `site_post_gather` (ledger note)

`find_modules` sorts (`check.pantheon` imports before `check.umich`), and same-phase
edgeless hooks keep registration order (§4).

- **`site_pre`: order preserved exactly.** Today frozen/no-live-env notices are added
  before the phase fires; after the move the package's two hooks run before
  `check.umich.sitelens`'s (alphabetical import), and frozen registers before live_env.
  First-notice position is unchanged on every path.
- **`site_post_gather`: three pairs flip.** Today's add order is umich.cloudflare_cms
  (hook) → B38 updates → B39 addons → B41 php-eol. After: pantheon.updates →
  pantheon.php_eol → umich.cloudflare_cms → B39 addons. So updates and php-eol now
  precede cloudflare_cms notices, and php-eol precedes addons; (updates, php-eol) and
  (updates, addons) keep today's order. Consequence: for a production site where such
  notices co-occur at equal severity, the rendered within-tier order and that site's
  `-notices.csv` row order shift (row *content*, keys, and shape unchanged — §8's
  structure bar holds). **Zero golden impact, proven**: no moved notice code renders in
  any golden (fixture `upstream:updates:list` returns `[]`; fixture PHP is 8.2; sites
  unfrozen, live initialized — grep evidence in §6). This is the §3.2-approved phase
  assignment's inherent consequence; the interim asymmetry vs B39 dissolves at I10 when
  addons becomes a hook too. Recorded in the ledger.

### D-i8-4: the PHP-EOL fixes (carried LEDGER I1 Obs. 2; test-first, RED on old behavior)

Two defects, one home (`check/pantheon/php_eol.py`):

1. **Lexicographic version compare.** `php_version < "8.2"` is a string compare:
   `"8.10" < "8.2"` is `True`, so a hypothetical PHP 8.10 site gets a false
   September-30 alert. Fix: parse to an int tuple and compare `(major, minor…) < (8, 2)`.
   Unparseable input returns `None` (today's `"banana" < "8.2"` → `False` → `None`
   behavior preserved; `"8"` → `(8,) < (8, 2)` → alert, same as today's
   `"8" < "8.2"`). RED: `build_php_eol_notice("s", "8.10")` returns an alert dict on
   the old code, `None` on the new.
2. **Missing/None `php_version`.** The old call site indexed
   `envs["live"]["php_version"]` — a KeyError aborting the whole run (as "fatal", not a
   site skip) if Pantheon ever omits the field; the guards check `live`/`initialized`
   but never `php_version`. Fix: the hook reads
   `site_context["envs"]["live"].get("php_version")` and the builder returns `None` for
   `None`/unparseable input (one mechanism covers both). RED: `build_php_eol_notice("s",
   None)` raises `TypeError` on the old code (`None < "8.2"`); the hook-seam test shows
   a `php_version`-less `envs` adds no notice and raises nothing.

Sketch (the exact-match warning branch is untouched):

```python
if php_version in ("7.4", "8.1"): …warning dict…
try:
    parsed = tuple(int(part) for part in php_version.split("."))
except (AttributeError, ValueError):
    return None
if parsed < (8, 2): …alert dict…
return None
```

Notice bodies, csv codes (`php-eol-warning`/`php-eol-alert`), and severities are
untouched — this changes *when* a notice fires, only for inputs (8.x≥10, missing key)
no current U-M site emits (and no golden contains, §10 of CAMPAIGN.md).

### D-i8-5: the updates-alert singular `short` f-prefix (discovered task, fixed here per §12)

`_legacy.py:2440`: the alert branch's singular arm reads
`else "needs maintenance: 1 Pantheon update, {oldest_update_days} days old"` — **no
f-prefix**, so an owner with exactly one >30-day-old update gets the literal braces in
the notice `short`. Discovered during scope verification; §12 disposition "fits current
increment's scope and <~30 min → fix now, note in ledger". Fix: add the `f`. Not a csv
value (§8's csv row untouched); no golden renders any `updates-*` notice (§6 evidence),
so Invariant 1 holds. RED: hook-seam test with one 45-day-old update pins
`short == "needs maintenance: 1 Pantheon update, 45 days old"` — fails on the old
literal. (The info/warning singular arms have no placeholder and are correct as-is.)

### D-i8-6: config gating — `[Check.pantheon].enabled`, default true

Registration guard in `__init__.py` (the `check/umich/` shape, inverted default):

```python
if sc.config.get("Check", {}).get("pantheon", {}).get("enabled", True) is not False:
    …imports + 4 add_hook calls…
else:
    sc.console.print("[bold yellow] Skipping check.pantheon because it is disabled in the config")
```

§5: relocating MUST NOT silently disable a check that runs unconditionally today —
hence default true when `[Check]`/`[Check.pantheon]`/`enabled` are absent, and the
sample config documents the section with `enabled = true`. `gate_disabled_sections`
already handles `enabled = false` at any depth (§5: its semantics apply to `[Check.*]`
unchanged). A parent-level `[Check].enabled` key is **not consulted** — §5 defines no
such key, and inventing semantics for it is out of scope (noted so the choice is
deliberate: a disabled `[Check]` parent would drop the subsection and the default-true
guard would still register — an operator disables the check via `[Check.pantheon]`).
`envs` is stuffed unconditionally (core contract key, not gated by the check).

### D-i8-7: ratchet — born gated for ruff; pyright scope unchanged

`ruff-broad.toml` `extend-exclude` drops `"check/"` and gains
`"check/cloudflare/"`, `"check/dns/"`, `"check/pantheon_cdn_change/"`,
`"check/umich/"` (each still grandfathered until I9/I10/I14; the empty top-level
`check/__init__.py` gates trivially). `check/pantheon/` is thereby born under the broad
set (I2–I7 precedent). **Pyright's gate stays `psh/` minus `_legacy.py`** (§13 defines
that scope; the checks call runtime-assigned `sc` attributes — `sc.terminus`,
`sc.console` — which pyright cannot see on `script_context`, and declaring typed façade
stubs is not I8 scope). Ledger-notes the pyright decision so I9/I10 inherit it
consciously.

## 3. `check/pantheon/` module shape (imports; no cycles)

`__init__.py`: `import script_context as sc`; conditional `from . import frozen,
live_env, updates, php_eol` + registrations. Siblings: `import script_context as sc`
only (plus stdlib `datetime`, `pprint` in `updates.py`). Nothing imports `psh._legacy`
or any `psh/` module (checks import only `sc`, Invariant 9 — `sc.terminus` reaches the
gateway through the façade). No module-level mutable state (§3.4).

## 4. Deliverables

- **A** — `check/pantheon/` package: four hooks emitting today's console lines and
  notices verbatim (modulo D-i8-4/D-i8-5), config-gated per D-i8-6.
- **B** — `main()` edits in `psh/_legacy.py`: B19/B21-notice/B38/B41 regions deleted;
  `stuff_envs_contract(site_context, envs)` inserted before the `site_pre` invoke;
  `build_php_eol_notice` def deleted; guards untouched.
- **C** — `psh/modules.py`: `CONTRACT["site_pre"] = ("envs",)`, `stuff_envs_contract`,
  `PHASES` comment update.
- **D** — config: sample-toml `[Check.pantheon]` block.
- **E** — ratchet: the D-i8-7 `ruff-broad.toml` edit.
- **F** — tests per §7; `test_php_eol_notice.py` repointed.
- **G** — docs: CLAUDE.md (contract table, package lists, still-hardcoded-U-M list),
  ledger entry, auto-memory.

## 5. Ratchet (§13) — expected findings, MUST be confirmed against real tool output

Predictions (PD#14: run the tools, correct this table in the task report if reality
differs — the I3/I5/I7 precedent):

- `F541` on `f"no live environment"` (live_env) and the two `f"Upgrade PHP"` shorts
  (php_eol) → drop the `f` (I6 precedent, behavior-identical).
- `PLR2004` on the `<= 7` / `<= 30` age thresholds in `updates.py` → `noqa` with
  reason (verbatim move).
- Possible `C901`/`PLR0915` on `check_upstream_updates` (the ~90-line B38 body moves
  whole) → `noqa`, no algorithmic redesign (§3.1 whole-file-coverage rule).
- `DTZ` clean: B38 already uses `datetime.datetime.now(datetime.UTC)` and
  tz-attached `fromisoformat`.
- `T203` on the `pprint(updates)` error path → keep behavior; disposition per real
  ruff output (likely `noqa` with reason — it is the existing operator diagnostic).

## 6. Behavior bar (§8) application — golden-impact evidence

Verified 2026-07-21: no moved notice renders in any golden.
`grep -c 'frozen\|no-live-env-but-paid-plan\|updates-info\|updates-warning\|updates-alert\|php-eol'`
over `tests/e2e/__snapshots__/*.ambr` → 0 hits for every code (the only "updates" text
is B39's add-on notice, which stays). Fixture evidence: `upstream:updates:list` returns
`[]` in `terminus/`, `terminus-drupal/`, `terminus-unknownfw/`, `terminus-cdnchange/`;
fixture PHP is 8.2 (CAMPAIGN §10); fixture sites are unfrozen with initialized live
envs. Therefore the four goldens MUST stay byte-identical (Invariant 1) — an increment
run that moves them is a defect in the increment. stdout changes (banner/skip-message
timing under hooks) are §8-free. `-notices.csv` per-site row order may shift per
D-i8-3; structure may not.

## 7. Tests (test-first at these seams; RED shown where behavior changes)

Unit tier:

- `tests/unit/test_php_eol_notice.py` — repointed to the standalone-loaded
  `check/pantheon/php_eol.py` (SourceFileLoader per-module pattern;
  `tests/helpers/checkload.py` if relative imports demand it). All existing cases kept
  byte-identical in expectation; NEW red-first: `"8.10"` → `None` (D-i8-4.1),
  `None` → `None` (D-i8-4.2), plus `"9.0"` → `None` and `"8"` → alert (pin the
  boundary semantics).

Integration tier (patterns: `test_check_cloudflare_init.py`, `test_check_dns.py`,
`test_check_sitelens.py`, `test_hooks_phases.py`):

- `test_check_pantheon_init.py` — gating: section absent → 4 hooks registered at the
  right phases with the D-i8-1 declarations; `enabled = false` → nothing registered +
  skip message; `[Check]` absent entirely → registered (default-true proof).
- `test_check_pantheon.py` — hook seams with `sc.SiteContext({...})`:
  frozen (`frozen: True` → alert `{name},frozen`; `frozen: False` → no notice);
  live_env (`initialized: False` → alert `{name},no-live-env-but-paid-plan`;
  `True` → none); updates via the `gateway` fixture (empty list → no notice;
  ages ≤7/≤30/>30 → info/warning/alert with correct csv `,{num},{days}` fields;
  non-list → error print, no notice; **RED D-i8-5**: one 45-day-old update pins the
  interpolated singular `short`); php_eol (`"8.1"` → warning added; `"8.2"` → none;
  **RED D-i8-4.2**: `envs["live"]` without `php_version` → no notice, no exception).
- `test_pantheon_notice_render.py` — syrupy snapshots of all seven notice variants'
  HTML/text (frozen, no-live-env, updates-info/warning/alert, php-eol-warning/alert):
  the byte-identity pin for the verbatim move going forward (Invariant 8 evidence at
  move time is the extracted-block diff in the task report, I2 precedent — snapshots
  are new files, not golden refreshes).
- `tests/unit/test_contract_registry.py` — `site_pre` row + `stuff_envs_contract` pin.
- `tests/integration/test_hook_dag.py` — loads every real package; now proves the
  `check.pantheon` declarations validate (no edit expected unless it pins counts —
  implementer verifies).

e2e tier: the four goldens + `test_unknown_framework_e2e.py` +
`test_only_warn_e2e.py` unchanged and green — the golden proof that hooks fire on the
real `main()` (conftest `_CWD_ASSETS` already symlinks `check/`, so the new package
loads in e2e workdirs automatically).

## 8. Acceptance (pasted at close, §16)

1. Full `./run-tests` (live tier if credentials present; else `--fast` + ledger note),
   all three gates, goldens byte-identical (`git diff <start> --
   tests/e2e/__snapshots__/` empty).
2. `uvx ruff check --config ruff-broad.toml check/pantheon/` → clean;
   `psh/modules.py` stays clean; pyright gate 0 errors.
3. RED evidence pasted for D-i8-4.1, D-i8-4.2, D-i8-5 (each shown failing against the
   old behavior before the fix).
4. Extracted-block byte-diff evidence for the four moved literal regions.
5. Ledger entry appended (§12 template); CLAUDE.md/memory updated.

## 9. Acceptance results

Pasted at close (2026-07-21), against the §8 checklist:

1. **Full `./run-tests --llm`** (no `--fast`, so the live tier is selected — `run-tests`
   only filters `-m "not live and not slow"` under `--fast`), all three gates green:
   ```
   All checks passed!          (ruff, narrow PD set)
   All checks passed!          (ruff-broad.toml, campaign ratchet)
   0 errors, 0 warnings, 0 informations   (pyright, standard mode)
   LLM_SUMMARY passed=846 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
   48 snapshots passed.
   846 passed, 1 skipped, 1 warning in 45.33s
   ```
   The single skip is `tests/integration/test_db_credentials.py`'s
   `importorskip("MySQLdb")` (sqlite-only install). **Live tier ran:** 0 deselected in
   the full run, and `python -m pytest -m live -q` → `2 passed, 845 deselected` confirms
   the 2 live-marked Terminus tests execute and pass (credentials present).

2. **Goldens byte-identical.** `git diff 6ce3416 -- tests/e2e/__snapshots__/` → empty
   output (exit 0, no diff) — the four e2e goldens are unchanged across the whole
   increment (base commit `6ce3416`).

3. **Born-gated ratchet.** `uvx ruff check --config ruff-broad.toml check/pantheon/
   psh/modules.py` → `All checks passed!`; pyright gate (`psh/` minus `_legacy.py`) → 0
   errors. Package noqa inventory: PLR2004 ×2 (`updates.py` `<=7`/`<=30` age tiers),
   T203 ×1 (`updates.py` `pprint` diagnostic); F541 ×3 resolved by f-prefix drops (no
   noqa).

4. **RED evidence** for D-i8-4.1 (`"8.10"` alert→None), D-i8-4.2 (`None` TypeError→None
   + hook no-exception), and D-i8-5 (singular `short` literal-braces→interpolated) is in
   `.superpowers/sdd/task-3-report.md`, each shown failing on the old behavior before the
   fix. Extracted-block byte-diff evidence for the four moved literal regions is in the
   Task 2/3 reports (pasted empty, I2 precedent).

5. Ledger entry appended (`development/2026-07-17-modularization-campaign/LEDGER.md`, §12
   template); CLAUDE.md contract-table/package-lists/still-hardcoded-U-M/Testing updated;
   auto-memory updated.
