# SPEC — Increment I6: `psh/traffic.py` (traffic helpers + gather/load flow + aggregation)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I6. Module map: §3.1 (`psh/traffic.py` row). What stays in `main()`:
§3.3 (B25 is named there — see D-i6-1). Parallel-ready constraint: §3.4. Per-increment
obligations: §7. Behavior bar: §8. Invariants: §9. Ratchet: §13.

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I5 — its I6 open-question
note on `build_traffic_table_rows`' `db_retry` coupling is binding here), `CLAUDE.md`
(§ Database, § Per-site report pipeline, § Testing), `BLOCKMAP.md` rows B22–B26, B43
(and B44/B46 for the boundary), `prompts/directives.md`,
`prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's)

- **Move set** — the four module-level items Deliverable A enumerates
  (`traffic_table_columns`, `get_old_metrics`, `estimate_month_visits`,
  `build_traffic_table_rows`); "verbatim" means byte-identical bodies except the edits
  Deliverable A names per item.
- **Flow functions** — the four NEW functions Deliverable B extracts from `main()`'s
  loop body (`update_site_traffic`, `import_older_site_metrics`, `load_site_traffic`,
  `aggregate_visits_by_month`).
- **Loop control** — the `continue` statements that advance `main()`'s per-site loop;
  these NEVER move into a flow function (D-i6-1).

## 1. Scope (exhaustive) and non-scope

In scope (§11 row I6 — its "598–671, 977–1127" are a47418c line ranges, drifted per
BLOCKMAP preamble; current-line equivalents below, verified 2026-07-20):

1. **Move** into a new `psh/traffic.py` (gated from birth): `traffic_table_columns`
   (`psh/_legacy.py:53–68`), `get_old_metrics` (265–336), `estimate_month_visits`
   (485–507), `build_traffic_table_rows` (510–633). This is exactly §3.1's
   `psh/traffic.py` def/global list.
2. **Extract** the B22–B24 + B26 loop-body flow (`_legacy.py:1904–1936`, `1942–1957`)
   and the B43 aggregation (`3036–3048`) into the four flow functions in
   `psh/traffic.py`, leaving loop control, option gating, and the B25 `--update`
   continue (`1938–1940`) in `main()` (D-i6-1).
3. **Re-import** every moved/new name into `psh/_legacy.py` (I2/I3/I5 pattern) so the
   `main()` call sites and the tests' `psh.<name>` references (`psh.get_old_metrics`,
   `psh.estimate_month_visits`, `psh.build_traffic_table_rows`) resolve unchanged.
4. **New tests** at the new seams (test-first, `mattpocock-skills:tdd`): the flow
   functions and the aggregation function (§4 Deliverable D). Existing suites are
   untouched — zero repoints needed (all references go through `psh.<name>`).
5. **Ratchet** (§13): `psh/traffic.py` clean under broad ruff + pyright standard from
   birth; measured findings + dispositions in §5.
6. Docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8), including the LEDGER I5
   obligation: `db_retry`'s unit-list prose in CLAUDE.md § Database notes
   `build_traffic_table_rows`' new home.

NOT in scope:

- **B25** (`--update` continue, 1938–1940): §3.3 names it part of the site-loop
  skeleton that stays in `main()`. It stays verbatim (D-i6-1).
- **`build_plan_over_time`** (def at 717, call at 3073): §3.1 assigns the def to
  `psh/plans.py` (I7). The call, the `last_day`/`plot_right_date` prep (3054–3056),
  the empty-`plan_on_day` synthetic-plan-day guard (3057–3069), and the
  `days`/`dates`/`visits` conversions (3071–3078+) stay in `main()` — they are the
  B43/B44 boundary and move with plans/charts (I7/I11). §3.1's "visits-by-month
  aggregation (B43)" is read as the aggregation loop only (D-i6-4; **ledger note**).
- **B46** (`db_retry(build_traffic_table_rows)` call site, 3458): stays in `main()`;
  it resolves via the re-import. (§11 assigns B46's call site to no increment; it
  leaves with `main()`'s final form.)
- **`overage_blocks`** (def in `_legacy.py`): §3.1 assigns it to `psh/plans.py` (I7).
  I6 bridges with a call-time import (D-i6-2), moving nothing.
- The verbose `pprint` block (3049–3052): stays in `main()` (D-i6-4).
- `live_site = site["id"] + ".live"` (1906): stays in `main()` — nine later blocks
  (domain:list, wp/drush gathers, upstream:updates) use it; it is passed to the flow
  functions as a parameter.
- No `_legacy.py` import removals: grep-verified 2026-07-20, the move orphans
  **nothing** (`calendar` → 3055; `TerminusError` → 1710; `terminus_data` → 1709;
  `escape`, `datetime`, `pprint`, `db_retry` → 3458 — all keep other users; the
  `psh.db` re-imports `update_traffic_rows`/`insert_traffic_rows`/`load_traffic_rows`/
  `PantheonOverageProtection` stay as the tests' `psh.<name>` façade, 22 references
  across `tests/conftest.py`, `test_traffic_table_rows.py`, `test_db_resilience.py` —
  D-i6-3).
- No test-file un-grandfathering; no golden/fixture changes (Invariants 1, 10); no
  config keys; no contract keys; no new `sc` façade names (nothing in the move set is
  on `sc`; grep-verified).

## 2. Architecture decisions (each with why; deviations flagged for the ledger)

### D-i6-1: loop control stays in `main()`; flow functions signal, never `continue`

B22's fatal-metrics path, B24, and B25 all `continue` the per-site loop. A `continue`
cannot cross a function boundary, and §3.3 keeps the site-loop skeleton (including B25
explicitly) in `main()`. Resolution — the §11/§3.3 tension is read as: the flow
*bodies* move, loop control does not (**ledger note**):

- `update_site_traffic(db_session, site, live_site, start_date, end_date) -> bool`
  (B22 fetch + failure report + B23 update): returns `False` on a fatal/undecodable
  `env:metrics` response (after printing the existing error), `True` on success.
  `main()`: `if not update_site_traffic(...): continue`.
- `import_older_site_metrics(db_session, site, live_site, end_date) -> None` (B24 body
  incl. its banner print; the week→month fetch/insert order and the
  fetch-outside-the-retried-unit comment move verbatim). `main()` keeps the gate:
  `if sc.options.import_older_metrics: import_older_site_metrics(...); continue`
  (Invariant 11 — option gating never moves out of `main()`).
- B25 stays verbatim between the two call sites, exactly where it is today.
- `load_site_traffic(db_session, site, start_date, end_date) -> list[TrafficRow]`
  (B26: the `db_retry(load_traffic_rows)` call, its connection-release comment, and
  the records-found debug print).
- `main()`'s replacement region (1904–1957) therefore reads: comment + `live_site` +
  `if not update_site_traffic(...): continue` + the B24 gate + B25 verbatim +
  `results = load_site_traffic(...)`.

The B22 error print interpolates `site["name"]` where the old code used the loop
variable `site_name` (identical value — `site` is selected by that name from the org
list; §8 sanctions stdout changes anyway).

### D-i6-2: `overage_blocks` bridges via a call-time import

`build_traffic_table_rows` calls `overage_blocks`, which §3.1 assigns to
`psh/plans.py` (I7) and which must stay in `_legacy.py` this increment (`plan_costs`
and the `psh.overage_blocks` test references still live there). A module-level
`from psh._legacy import overage_blocks` in `psh/traffic.py` is a cycle (`_legacy`
imports `psh.traffic` for the re-exports). Resolution: a call-time import at the top
of `build_traffic_table_rows`' body — the I4 `psh/modules.py` precedent
(`# noqa: PLC0415` with the cycle reason). **Temporary until I7**, which moves
`overage_blocks` into `psh/plans.py` and MUST replace this with a module-level
`from psh.plans import overage_blocks` (ledger this obligation against I7). Measured:
pyright standard accepts the call-time import at 0 errors (2026-07-20).

### D-i6-3: the `psh.db` re-imports in `_legacy.py` stay, even though `main()` no longer calls them

After Deliverable B, `_legacy.py`'s only *calls* to `update_traffic_rows`/
`insert_traffic_rows`/`load_traffic_rows` move into `psh/traffic.py`. The I5
re-imports stay anyway: 22 test references resolve `psh.update_traffic_rows`,
`psh.insert_traffic_rows`, `psh.load_traffic_rows`, `psh.PantheonOverageProtection`
through the `psh` fixture (grep-verified 2026-07-20). Removing them is exactly the
"remove only what this change orphans" rule's negative case — they are not orphaned,
the test façade uses them.

### D-i6-4: B43 moves as a pure function; its consumers stay

`aggregate_visits_by_month(rows, start_date, end_date) -> tuple[dict, dict]` returns
`(visits_by_month, plan_on_day)`: seeds every month in the window to 0, sums
`row.visits` per `"%Y-%m"` key, and maps `row.traffic_date -> row.site_plan`
(last-row-wins, preserving iteration order semantics). Pure — no `sc`, no I/O — per
§3.4. The verbose `pprint` block stays in `main()` immediately after the call (it is
operator diagnostics wired to `sc.options.verbose`, not aggregation), as do the
empty-`plan_on_day` guard and everything from 3054 on (see non-scope). A row whose
month is outside the seeded window would `KeyError`, exactly as today —
`load_traffic_rows` only returns in-window rows; the function documents (not handles)
that precondition.

### D-i6-5: `psh/traffic.py` imports

Module level: `calendar`, `datetime`; `rich.markup.escape`;
`import script_context as sc` (no cycle — the D-i5-2 reasoning applies verbatim);
`from psh.db import PantheonOverageProtection, db_retry, insert_traffic_rows,
load_traffic_rows, update_traffic_rows` (+ `TrafficRow` if used in annotations);
`from psh.gateway import TerminusError, terminus, terminus_data`. Call-time:
`overage_blocks` (D-i6-2). Test-seam note: the gateway wrappers are imported
*bindings*, but the documented mock seam is `psh.gateway.run_terminus`, which every
wrapper resolves in the gateway's own namespace — patching it intercepts calls made
from `psh/traffic.py` with no repoint (CLAUDE.md § mock seams; the `gateway` fixture
works unchanged, proven by `test_terminus_contract.py` staying green).

## 3. Deliverable A — the move set (verbatim, with named edits)

Module docstring: names the module's role (traffic metrics gather, DB update/load
flow, and per-month aggregation feeding the report pipeline), cites CAMPAIGN.md §3.1
I6 as the move, and carries the D-i6-2 bridge note (the flow is non-local).

| Item | From (`_legacy.py`) | Edits allowed (exhaustive — else verbatim) |
|---|---|---|
| `traffic_table_columns` | 53–68 | — (the duplicated month/visitors head entries are template-consumed and golden-frozen; see Observations) |
| `get_old_metrics` | 265–336 | `-> list` → `-> list[dict]` (honest annotation, §6/I5 precedent); `# noqa: DTZ007` + reason on the `strptime` (§5) |
| `estimate_month_visits` | 485–507 | two `# noqa: PLR2004` + reason (§5) |
| `build_traffic_table_rows` | 510–633 | def line gains `# noqa: C901, PLR0912, PLR0915, PLR0913` + reason (§5); call-time `overage_blocks` import (D-i6-2); `.keys()` dropped in favor of `.items()` with `month_visits` replacing the two `visits_by_month[month]` reads (§5 SIM118/PLC0206); three `if`-guards → `max`/`min` + `d = max(ymd, first_plan_day)` (§5 PLR1730/FURB136); two `f`-prefixes dropped (§5 F541); `# noqa: DTZ007` + reason on the month-label `strptime` (§5) |

Docstrings move verbatim; `build_traffic_table_rows`' docstring keeps its SPEC 3.3.1
citation (verified still-resolving) and its idempotency contract — it remains one of
`db_retry`'s five named units (LEDGER I5 open-question obligation; CLAUDE.md sync in
§8 of this spec).

## 4. Deliverables B–D — the flow extraction, the remnant, the tests

**B — `psh/traffic.py` flow functions** (new code, born clean — shapes in D-i6-1/
D-i6-4). Bodies are the existing loop-body lines moved verbatim except: the function
headers/returns D-i6-1 defines, the B22 print's `site["name"]`, and de-indentation to
function level (none of these lines are column-0 `f"""` notice literals — Invariant 8
does not bite; the implementer confirms by grep before de-indenting).

**C — `psh/_legacy.py`:** delete the move set and the extracted loop-body lines; add
`from psh.traffic import (aggregate_visits_by_month, build_traffic_table_rows,
estimate_month_visits, get_old_metrics, import_older_site_metrics, load_site_traffic,
traffic_table_columns, update_site_traffic)` to the import block; rewrite the
1904–1957 region per D-i6-1 and replace 3036–3048 with
`visits_by_month, plan_on_day = aggregate_visits_by_month(results, start_date,
end_date)`. No import removals (§1 non-scope). The narrow PD set must stay green on
`_legacy.py`.

**D — tests (test-first at the new seams; written RED before Deliverable B lands):**

- `tests/unit/test_traffic_aggregation.py` — `aggregate_visits_by_month`: seeds all
  window months to 0 (including traffic-free months); sums multiple rows in one
  month; `plan_on_day` maps date→plan with last-row-wins; a window spanning a year
  boundary (Nov→Feb) seeds the right keys. Pure-function tier, no fixtures
  (`psh.traffic` imported directly).
- `tests/integration/test_traffic_flow.py` — via the `gateway` fixture + `temp_db` +
  `recording_console`: `update_site_traffic` returns `False` and writes no rows on a
  fatal `env:metrics` (error printed, escaped); returns `True` and persists rows on
  success. `import_older_site_metrics` fetches week then month and inserts both
  (order asserted on the fake's call log). `load_site_traffic` returns the seeded
  window's `TrafficRow`s.
- Existing suites: untouched and green — `test_plan_math.py`,
  `test_traffic_table_rows.py`, `test_terminus_contract.py`, the db suites, all four
  goldens (which drive the extracted flow end-to-end through the real `main()`).

## 5. Ratchet (§13) — measured findings and dispositions

Broad ruff + pyright (standard, project venv) were run 2026-07-20 on a scratch
assembly of the exact move set with final imports (archived:
`scratchpad/traffic-scratch-measured.py`); after the dispositions below, both report
clean (`All checks passed!` / `0 errors, 0 warnings, 0 informations`). Anything new at
implementation time is disposed inline and ledger-recorded (I3 precedent).

| Finding | Where | Disposition |
|---|---|---|
| DTZ007 ×2 | `get_old_metrics` strptime (288); `build_traffic_table_rows` month-label strptime (559) | `# noqa: DTZ007` + inline reason — naive date markers / label re-formatting; attaching tzinfo risks an off-by-one-day shift, a behavior change a move may not make (I5's exact precedent) |
| PLR2004 ×2 | `estimate_month_visits` `>= 25`, `>= 15` | `# noqa: PLR2004` + reason (extrapolation-weighting day thresholds; I3 precedent — no redesign in a move) |
| C901/PLR0912/PLR0915/PLR0913 | `build_traffic_table_rows` def | quadruple `# noqa` + reason: moved verbatim (§3.1 whole-file coverage: no algorithmic redesign); 12-arg signature pinned by `test_traffic_table_rows.py` and the B46 call site (I3 `config_substitution` / I4 `stuff_gather_contract` precedents) |
| I001 | call-time import formatting | reason comment on its own line above the import, `# noqa: PLC0415` on the import line (the `psh/modules.py` style) — measured clean |
| SIM118 + PLC0206 | `for month in visits_by_month.keys():` + two value reads | `for month, month_visits in visits_by_month.items():`, `month_visits` at both reads — behavior-identical (loop never mutates the dict), measured clean |
| PLR1730 ×3 + FURB136 | the four `ymd`/`ymd1`/`d` clamp sites | `max()`/`min()` rewrites — equivalent on totally-ordered dates (`if x < a: x = a` ≡ `x = max(x, a)`) |
| F541 ×2 | `f"used 1 month, "`, `f"1 month remaining"` | drop the `f` prefix — byte-identical output |
| ERA001 (would fire on move) | the commented-out `# for row in results:` / `#    sc.debug(row, level=2)` pair (1956–1957) in the B26 region | **delete** — dead commented debug code; ratchet D2 ("cleaned exactly once, as it moves"), I5's `# id:` precedent |

The four flow functions (Deliverable B) were included in the measured assembly and
introduce **zero** additional findings (both gates clean, 2026-07-20; assembly archived
as `scratchpad/traffic-scratch-measured.py`).

No `ruff-broad.toml` `ignore` additions (would be a §13 amendment). No
`extend-exclude` deletion (fresh gated file — I2/I3/I5 precedent; `_legacy.py` stays
grandfathered).

## 6. Behavior bar & invariants applied (§8/§9)

- Four goldens byte-identical (Invariant 1): the goldens execute the full extracted
  flow (B22→B26→B43) through the real `main()` — they are the primary tripwire for
  the extraction, exactly as §14 intends.
- Invariant 5: `db_retry` keeps wrapping the same whole units at the same
  granularity; the fetch-outside-the-retried-unit comment (B24) and the
  connection-release comment (B26) move with their code; `build_traffic_table_rows`'
  idempotency docstring moves verbatim.
- Invariant 8: no column-0 `f"""` literal is in scope (implementer confirms by grep
  over the moved regions before de-indenting).
- Invariant 11: `--update`/`--import-older-metrics` gating stays in `main()`
  (D-i6-1); `--create-tables` exits before the loop — untouched.
- Invariant 9: no `sc` name removed; nothing new documented on the façade.
- Invariants 4, 6, 7: untouched paths; the one moved console print keeps its
  `escape()`; no interlock change.
- §8 rows: emails/artifacts/config/exit codes untouched; stdout changes limited to
  the `site["name"]` spelling (sanctioned).

## 7. Task shape (for the plan)

Task 1 — tests RED: Deliverable D's two new files written against the specced
signatures, shown failing (import error / missing names) — the `mattpocock-skills:tdd`
red step. Task 2 — the move + extraction (Deliverables A–C) turning Task 1 green
atomically (partial application cannot be green). Gates per commit: full `--fast`
suite green with collected count = baseline + new tests (780 passed / 1 skipped / 2
deselected at I5 close, `--fast` tier), goldens diff empty, broad ruff clean on
`psh/traffic.py`, narrow ruff whole-tree clean, pyright 0 errors. Task 3 —
docs/memory/ledger (§8 below) + acceptance pasted into §9.

## 8. Documentation & memory obligations (same change, §7)

- CLAUDE.md: § Single-module core gains the `psh/traffic.py` sentence (what lives
  there, re-imported by `_legacy`, same import-back pattern); § Database's five-unit
  list notes `build_traffic_table_rows` now lives in `psh/traffic.py` (LEDGER I5
  obligation); § Testing's pure-helper list notes `estimate_month_visits`/
  `build_traffic_table_rows` home (references stay `psh.<fn>`-resolvable).
- Memory: update `modularization-campaign.md` progress line.
- `LEDGER.md`: I6 entry — D-i6-1 (loop control stays; B25 §3.3), D-i6-2 (+ the I7
  obligation to replace the call-time import), D-i6-3, D-i6-4 (B43 partial move),
  ratchet dispositions, the `traffic_table_columns` duplicate-head observation
  (template-consumed, golden-frozen; disposition: leave, revisit post-campaign),
  discovered tasks.

## 9. Acceptance (commands run and output pasted at close — never summarized)

Filled 2026-07-20 at increment close. `terminus auth:whoami` succeeded (see below), so the
**full** `./run-tests --llm` ran, live tier included — no live-tier-skipped ledger note is
needed.

### `terminus auth:whoami`

```
$ terminus auth:whoami
markmont@umich.edu
EXIT: 0
```

### `./run-tests --llm` (full, live tier included)

```
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
................................s....................................... [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
........................................................................ [ 45%]
........................................................................ [ 54%]
........................................................................ [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
........................................................................ [ 91%]
.......................................................................  [100%]
LLM_SUMMARY passed=790 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
--------------------------- snapshot report summary ----------------------------
27 snapshots passed.
790 passed, 1 skipped in 31.15s
Linting (ruff, narrow PD set) ...
Linting (ruff-broad.toml, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
```

790 = the 788 figure from `.superpowers/sdd/task-1-report.md`'s `--fast`-tier GREEN run
(780 baseline + 8 new tests) plus 2 live-tier-only tests — consistent with the I4/I5
780-`--fast`-baseline / +2-live-tier pattern.

### `git diff 5de11a4 -- tests/e2e/__snapshots__/ | wc -l`

```
$ git diff 5de11a4 -- tests/e2e/__snapshots__/ | wc -l
0
```

Four goldens byte-identical across the increment, confirmed.

### `uvx ruff check --config ruff-broad.toml psh/traffic.py`

```
$ uvx ruff check --config ruff-broad.toml psh/traffic.py
All checks passed!
```

### `uvx ruff check .`

```
$ uvx ruff check .
All checks passed!
```

## Observations (recorded for the ledger, no action this increment)

- `traffic_table_columns` opens with `month`/`visitors` listed twice (53–57). The
  templates iterate the full list (`email_template.html:359`) and `[1:]`
  (`:374`, `email_template.txt:105`), so the duplication is rendered and
  golden-frozen. Whether it is a deliberate responsive-layout device or a latent bug
  is a post-campaign question; any change would violate Invariant 1 now.
