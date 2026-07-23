# SPEC — Increment I11: `psh/charts.py` (cap geometry + chart data prep + matplotlib build)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I11 ("B13 (caps), B44–B45 → `psh/charts.py`"). Module map: §3.1
(`psh/charts.py` row: "Cap geometry (B13 part), chart data prep + matplotlib build
(B44–B45) — returns PNG bytes"). What stays in `main()`: §3.3 (the date window is named
there — see D-i11-3). Parallel-ready constraint: §3.4. Per-increment obligations: §7.
Behavior bar: §8. Invariants: §9. Ratchet: §13.

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I10 — its I11 open-question
note is binding: the B43 `pprint` diagnostics, the empty-`plan_on_day` guard, and the
`build_plan_over_time` call + date/chart prep stay in `main()`; I11 threads shaped data
rather than re-deriving it), `CLAUDE.md` (§ Per-site report pipeline, § Testing),
`BLOCKMAP.md` rows B13, B44, B45 (and B43/B46 for the boundary),
`prompts/directives.md`, `prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's)

- **Chart region** — `psh/_legacy.py:1490–1851` (current lines, verified 2026-07-23):
  everything from `visits_covered_by_month = {}` through `plt.close(fig)`, plus the
  `# TODO: Create SVG chart` marker at 1853. This is B44's post-`--only-warn` remainder
  + all of B45.
- **Cap geometry** — `psh/_legacy.py:1093–1101`: the numpy cap-shape block (comment +
  `cap_size`/`x`/`y`/`cap_points`/`cap_points_inv`), B13's chart-specific part.
- **Shaped locals** — the `main()` locals the chart region consumes that earlier
  increments already shaped (I6 traffic, I7 plans) and that `build_chart` receives as
  parameters; enumerated in D-i11-1. "Verbatim" for the moved bodies means
  byte-identical except the edits §3's table names per site.

## 1. Scope (exhaustive) and non-scope

In scope:

1. **Move** into a new `psh/charts.py` (gated from birth) a single function
   `build_chart(...) -> bytes` containing: the cap geometry (as the function prologue —
   D-i11-2), the chart region, and the two one-line derivations D-i11-3 relocates
   (`end_date_yyyy_mm`, `visits`). Returns `chart_image` (PNG bytes) — exactly §3.1's
   "returns PNG bytes".
2. **Re-import** `build_chart` into `psh/_legacy.py` (I2–I10 pattern); `main()`'s chart
   region collapses to `chart_image = build_chart(...)`.
3. **Delete from `psh/_legacy.py`**: the cap geometry (1093–1101), the
   `end_date_yyyy_mm` derivation (1086), the `visits` derivation (1417), the chart
   region (1490–1851 + the 1853 TODO line), and the eight imports the move orphans
   (verified 2026-07-23 — each name's only remaining uses are inside the move set):
   `io` (line 17), `matplotlib` (33), `matplotlib.dates as mdates` (34),
   `matplotlib.patheffects as path_effects` (35), `matplotlib.pyplot as plt` (36),
   `numpy as np` (37), `GridSpec` (40), `Polygon` (41).
4. **New tests** at the new seam (test-first, `mattpocock-skills:tdd`):
   `tests/integration/test_charts.py` (§4 Deliverable C).
5. **Increment-scoped behavior evidence** (§6): the goldens do NOT pin chart bytes —
   the chart PNG lives only in the `.eml`, which has no byte golden (CLAUDE.md
   § Testing: only the HTML/txt are snapshotted; `test_eml_headers.py` asserts headers).
   Task 2's acceptance therefore includes a before/after chart-payload hash comparison
   (§6 procedure), pasted in §9. No committed image golden (D-i11-6 says why not).
6. **Ratchet** (§13): `psh/charts.py` clean under broad ruff + pyright standard from
   birth; measured findings + dispositions in §5 (assembly archived:
   `development/2026-07-23-mod-I11-charts/charts-scratch-measured.py`).
7. Docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8), §8 of this spec.

NOT in scope:

- **The date window** (`_legacy.py:1085, 1087–1091`: `end_date`, `start_date`,
  `end_of_contract_year`, the debug line): §3.3 keeps "overage constants + date window
  (B9, B13 part)" in `main()`. Only the chart-specific cap geometry and the chart-only
  `end_date_yyyy_mm` alias leave (D-i11-3).
- **The B43 tail** (`_legacy.py:1385–1424`: `aggregate_visits_by_month` call, `pprint`
  diagnostics, empty-`plan_on_day` guard, `days`, `build_plan_over_time` call, `dates`,
  `estimate` call, `first_plan_day`/`last_plan_day`/`site_plan_start`): stays in
  `main()` per LEDGER I10's I11 note and D-i6-4/I7 — except the `visits` line (1417),
  which is chart-only (D-i11-3).
- **B46/B47** (traffic table, recommendation, the `--only-warn` gate at 1485–1488):
  untouched; the gate remains the line above the new `build_chart` call site.
- **B55's `chart_image` consumer** (`_legacy.py:2057`, the MIME `add_related`): I12
  scope; it keeps reading the `chart_image` local, now assigned from `build_chart`.
- **`wordmark_image`** (B12): not chart data; stays for I12.
- No `[Check.*]`/config keys; no contract keys; no new `sc` façade names (nothing in
  the move set is on `sc`; the region's only `sc` uses are `sc.debug` — grep-verified).
- No test-file un-grandfathering; no golden/fixture changes (Invariants 1, 10).
- No `matplotlib`-version or style changes; no chart redesign of any kind (§3.1
  whole-file coverage: moves are behavior-preserving).

## 2. Architecture decisions (each with why; ledger notes flagged)

### D-i11-1: one function, threading the shaped locals

`psh/charts.py` exposes a single public function (plus nothing else — no module
globals, D-i11-2):

```python
def build_chart(
    site: dict,
    site_url: str,
    visits_by_month: dict[str, int],
    plan_on_day: dict[datetime.date, str],
    plan_info: dict,
    plan_over_time: list[dict],
    dates: list[datetime.date],
    estimate: int,
    first_plan_day: datetime.date,
    last_plan_day: datetime.date,
    start_date: datetime.date,
    end_date: datetime.date,
    plot_right_date: datetime.date,
) -> bytes:
```

The 13 parameters are exactly the `main()` locals the chart region reads (LEDGER I10:
"threads shaped data rather than re-deriving") — no grouping type is introduced
(that would be redesign; the `PLR0913` noqa records the pinned arg set, the I6
`build_traffic_table_rows` 12-arg precedent). Satisfies §3.4: a function of
`(site, …)` with no module-level mutable state. Real annotations replace nothing —
the moved code carried none (§6 house-style rule is moot here); the signature's
annotations are new and honest (`plan_info` stays a plain `dict` — it is the raw
normalized `[Pantheon.plan_info]` sub-dict, the same object `PlanCatalog.from_config`
mutates; typing it tighter is I14's business if ever).

Boundary diagram (PD#8 — the flow is non-local, `main()` → `psh/charts.py` → I12's
MIME assembly):

```
main() per-site loop (post --only-warn gate)
  visits_by_month, plan_on_day   (I6: aggregate_visits_by_month)
  plan_info                      (I7: PlanCatalog.from_config's normalized dict)
  plan_over_time, dates, estimate, first/last_plan_day   (B43 tail, stays)
  start_date, end_date, plot_right_date, site, site_url
        │
        ▼
  chart_image = build_chart(...)          # psh/charts.py — the whole move
        │        (cap geometry + data prep + matplotlib build + savefig/close)
        ▼
  B55 MIME add_related(chart_image, ...)  # _legacy.py:2057, I12 scope
```

### D-i11-2: cap geometry becomes the function prologue (ledger note)

Today the cap shape (`cap_points`/`cap_points_inv`) is computed once per run,
pre-loop (B13, 1093–1101). It is pure constant math — no inputs, identical values
every run. It moves **inside** `build_chart` as the prologue, recomputed per call,
because the alternatives are worse: module-level numpy arrays are new module-level
mutable state (§3.4 bars it; the `traffic_table_columns` list precedent predates that
rule and is not license to add more), and the interim `x`/`y` temporaries would leak
as module names. Cost: ~microseconds of numpy on 31-point arrays per site, vs. a
~1 s matplotlib build — not observable. Behavior: values identical (pure function of
constants). The `zip(x, y)` gains `strict=True` (§5 B905): both operands are
`np.linspace(0, cap_size, 31)`-shaped, so `strict=True` provably never raises —
recorded as the honest disposition, not a behavior change.

### D-i11-3: `end_date_yyyy_mm` and `visits` derive inside; `dates` is passed (ledger note)

Grep-verified 2026-07-23: `end_date_yyyy_mm` (def 1086) and `visits` (def 1417) have
**no consumer outside the chart region** — after the move they would be dead stores in
`main()`. Both one-line derivations move into `build_chart`
(`end_date.strftime("%Y-%m")`; `list(visits_by_month.values())`) and the `main()`
lines are deleted (the orphan-removal rule). Value-identity of the relocated `visits`
derivation: nothing mutates `visits_by_month` between line 1417 and the chart —
grep-verified, the only writer anywhere is `aggregate_visits_by_month`'s seeding loop
(`psh/traffic.py:350`), which runs before 1417. `dates` (def 1416) **is** passed as a
parameter: it has a pre-gate consumer (the `estimate_month_visits` call at 1420).
`end_date_yyyy_mm` is read as chart-only formatting, not part of §3.3's "date window"
(which is `end_date`/`start_date`/`end_of_contract_year`).

### D-i11-4: `estimates = []` prologue init (pyright; I7 precedent)

`estimates` is bound under `if estimate != -1:` and read under `if estimate >= 0:` —
safe by invariant (`>= 0` implies `!= -1`), invisible to pyright. Resolution: an
`estimates = []` init immediately before the `if` (the I7 `costs_best = {}` prologue
precedent) — never read while empty, so behavior-identical. The other
conditionally-bound names (`ax_surge`, `est_bars`, `bars`) get scoped
`# pyright: ignore[reportPossiblyUnboundVariable]` instead (§5): an `= None` init
would trade unbound-errors for optional-member-access errors at every use site, and a
fabricated default (`ax_surge = ax_plan`) would silently draw on the wrong axes if the
`surge` invariant ever broke — a PD#1 violation; the loud `NameError`/`UnboundLocal`
is the correct failure mode.

### D-i11-5: `psh/charts.py` imports

Module level: `datetime`, `io`, `typing.Any`; `matplotlib as mpl` (ICN001 — the one
alias rename, §5), `matplotlib.dates as mdates`, `matplotlib.patheffects as
path_effects`, `matplotlib.pyplot as plt`, `numpy as np`,
`matplotlib.gridspec.GridSpec`, `matplotlib.patches.Polygon`;
`import script_context as sc` (for `sc.debug` only — no cycle, the D-i5-2/D-i6-5
reasoning applies verbatim). **No gateway imports** — the region makes no
Terminus/WP/Drush calls, so the I10 two-binding seam trap does not apply. The one
in-body `matplotlib.rcParams` read becomes `mpl.rcParams` (the alias rename's only
other touch point). `_legacy.py` keeps importing matplotlib **transitively** (via
`from psh.charts import build_chart`), so conftest's MPLBACKEND-before-import rule
still holds — its CLAUDE.md wording updates to name `psh/charts.py` (§8).

### D-i11-6: behavior evidence — before/after payload hash, no committed image golden

The chart PNG is not golden-pinned (§1 item 5). A **committed** byte-golden of the
PNG would freeze matplotlib's exact rendering across environment upgrades — a
matplotlib/font bump would red a golden that Invariant 1 forbids refreshing, trapping
post-campaign maintenance. Instead: (a) permanent seam tests (§4) pin the properties
that matter (valid PNG, surge-vs-plain figure geometry, estimate visibility,
determinism, no figure leaks); (b) this increment proves the move byte-preserving
with a before/after hash of the chart payload extracted from the offline golden
pipeline's `.eml`, run in the same environment minutes apart (§6 procedure, pasted in
§9). The e2e goldens remain the proof that `main()` still drives the chart path.

### D-i11-7: the `plan_on_day` precondition is documented, not handled

`visits_covered_by_month` indexes `plan_on_day[ymd]` with each month's midpoint
clamped to `[first_plan_day, last_plan_day]`; a `plan_on_day` lacking a clamped
midpoint would `KeyError` — exactly as today. In production `plan_on_day` maps every
traffic-row date and `first_plan_day`/`last_plan_day` are its min/max, so the clamp
lands on existing keys. `build_chart`'s docstring records the precondition; no
handling is added (the D-i6-4 documents-not-handles posture; a move may not change
behavior).

## 3. Deliverable A — the move, with named edits (exhaustive — else verbatim)

Module docstring: names the module's role (the per-site traffic chart: cap geometry,
data prep, matplotlib build, returning PNG bytes for the MIME assembly), cites
CAMPAIGN.md §3.1 I11 as the move, and carries the two suppression-family notes (§5:
matplotlib-stub `reportArgumentType`; surge-conditional `reportPossiblyUnboundVariable`).

| Site | From (`_legacy.py`) | Edit |
|---|---|---|
| def line | new | quadruple `# noqa: C901, PLR0912, PLR0913, PLR0915` + reason (verbatim ~360-line move; pinned arg set) |
| cap geometry | 1093–1101 | de-indent to function level; `zip(..., strict=True)` (D-i11-2) |
| `end_date_yyyy_mm`, `visits` | 1086, 1417 | relocated one-line derivations at prologue (D-i11-3) |
| `visits_covered_by_month` loop | 1491–1500 | `for month, month_visits in visits_by_month.items():` + `month_visits` at the `min()` read (SIM118/PLC0206); the two `ymd` clamps → `ymd = max(...)` / `ymd = min(...)` (PLR1730 ×2) — the I6 `build_traffic_table_rows` exact precedents |
| `xbins` comprehension | 1503–1506 | `.keys()` dropped (SIM118); `# noqa: DTZ007` + reason comment on the `strptime` line (naive month-label bin edges; tzinfo could shift a bin edge by a day — I5/I6 precedent) |
| `estimates` block | 1520–1525 | `estimates = []` prologue init (D-i11-4); `.keys()` dropped in the zeroing loop (SIM118 — values mutated, key set untouched, safe) |
| `upgrade_at_max` clamp | 1531–1532 | `upgrade_at_max = max(upgrade_at_max, upgrade_at)` (PLR1730) |
| `surge` | 1535 | `surge = visits_max > surge_threshold` (SIM210 — identical truth value; note the old form produced `bool` too) |
| `kwargs` axes-caps dict | 1702–1710 | `dict(...)` → literal (C408) **annotated `kwargs: dict[str, Any]`** — the `Any` is what lets pyright accept the `**kwargs` splat into `Axes.plot` (dissolves 6 `reportArgumentType` findings; §5) |
| upgrade-label concat | 1730–1733 | explicit `+` → implicit concat (ISC003; the single-line downgrade concat at 1768 did NOT fire and stays verbatim) |
| `matplotlib.rcParams` | 1787 | `mpl.rcParams` (ICN001 alias, D-i11-5) |
| scoped pyright ignores | 14 lines | per §5's pyright table — `# pyright: ignore[...]` with the narrowest rule set per line |
| tail | 1846–1851, 1853 | `return chart_image` appended after `plt.close(fig)`; the `# TODO: Create SVG chart` marker moves beside it (chart work belongs to the chart module) |

No column-0 `f"""` literal exists anywhere in the move set (grep-verified 2026-07-23:
zero `"""` occurrences in 1490–1851 and 1093–1101) — Invariant 8 cannot bite, but the
implementer re-confirms by grep before de-indenting.

## 4. Deliverables B–C — the remnant, the tests

**B — `psh/_legacy.py`:** add `from psh.charts import build_chart` to the import
block; delete per §1 item 3; replace the chart region with:

```python
            chart_image = build_chart(
                site, site_url, visits_by_month, plan_on_day, plan_info,
                plan_over_time, dates, estimate, first_plan_day, last_plan_day,
                start_date, end_date, plot_right_date,
            )
```

Blank-line runs left by the non-contiguous deletions collapse to the file's standard
(the disclosed I5 precedent). The narrow PD ruff set must stay green on `_legacy.py`.

**C — tests (test-first at the seam `psh.charts.build_chart`; written RED before
Deliverable A lands — RED = `ImportError`/`AttributeError` on the missing module):**

`tests/integration/test_charts.py` (integration tier: real matplotlib/Agg, real `sc`;
the `reset_sc` autouse fixture provides `sc.options`). Fixture inputs are synthetic
shaped locals (12 months, `plan_on_day` keyed by every month midpoint — the D-i11-7
precondition; one plan spanning the window). Tests, each with its purpose:

1. **Returns a PNG** — magic bytes `\x89PNG\r\n\x1a\n`, non-trivial length. The
   baseline contract of §3.1's "returns PNG bytes".
2. **Surge branch renders the two-axes figure** — parse the PNG IHDR (width/height at
   fixed offsets 16–24): the non-surge figure is 12×9 in, the surge figure 12×12 in,
   so at equal dpi the surge PNG is strictly taller. Proves the branch actually ran —
   not just that some PNG came back.
3. **Estimate affects the render** — same inputs with `estimate = 4200` vs
   `estimate = -1` produce different bytes (the estimate bars/labels exist). Guards
   the `estimates` prologue-init edit (D-i11-4) against a regression that skips the
   estimate histogram entirely.
4. **Deterministic** — two identical calls return identical bytes. This is the
   property the `.eml` reproducibility (and §6's hash procedure) rests on; PD#14 says
   prove it rather than assume it.
5. **No leaked figures** — after the calls above, `plt.get_fignums() == []`. Guards
   the moved `plt.close(fig)` (the I1-deleted duplicate close's surviving sibling);
   a leak here is invisible until a 300-site run exhausts memory.

The four e2e goldens stay untouched and green — they drive `build_chart` end-to-end
through the real `main()` (crash tripwire), while §6 covers byte-preservation.

## 5. Ratchet (§13) — measured findings and dispositions

Broad ruff + pyright (standard, project venv, file placed at `psh/charts.py`) were run
2026-07-23 on the exact assembly (archived:
`development/2026-07-23-mod-I11-charts/charts-scratch-measured.py`); after the
dispositions below, both gates report clean (`All checks passed!` / `0 errors, 0
warnings, 0 informations`), and the assembly was smoke-run (both chart paths render
PNG bytes, deterministic, zero leaked figures). Anything new at implementation time is
disposed inline and ledger-recorded (I3 precedent).

Ruff (17 findings; INP001 from the scratch location did not fire at `psh/charts.py`):

| Finding | Disposition |
|---|---|
| ICN001 (`matplotlib` → `mpl`) | rename per D-i11-5 (import + the one `rcParams` site) |
| B905 (`zip` without `strict=`) | `strict=True` (provably equal-length; D-i11-2) |
| C901/PLR0912/PLR0913/PLR0915 | quadruple noqa + reason on the def (verbatim move; pinned args — I6 precedent) |
| SIM118 ×3, PLC0206, PLR1730 ×3, SIM210, C408, ISC003, DTZ007 | per §3's table (rewrites behavior-identical; DTZ007 noqa'd with reason) |
| I001 | canonical import order (ruff-fix applied in the assembly) |

pyright (25 errors → 0). Two families, both inherent to a verbatim matplotlib move:

| Family | Sites | Disposition |
|---|---|---|
| `reportArgumentType` — matplotlib stubs reject runtime-valid dynamic API use (`hist(bins=list[datetime])` ×4 — mpl converts via date units; `bar_label(container=BarContainer\|Polygon…)` ×2; `gap_bars.extend` unions ×2; `set_xlim(NDArray)` ×1 line; `transform_point(tuple)` ×1) | scoped `# pyright: ignore[reportArgumentType]` per line (10 sites; the I10 scoped-ignore precedent); family reason stated once in the module docstring |
| `reportPossiblyUnboundVariable` — `estimates`, `est_bars`, `bars`, `ax_surge` bound under `surge`/loop conditions pyright cannot correlate | `estimates = []` prologue init (D-i11-4); scoped ignores on the other 6 lines (2 lines carry both rules); why-not-`None`-inits in D-i11-4 |
| 6 `reportArgumentType` on `Axes.plot(**kwargs)` | dissolved by the `kwargs: dict[str, Any]` annotation (§3) — no ignores needed |

No `ruff-broad.toml` `ignore` additions (would be a §13 amendment). No
`extend-exclude` deletion (fresh gated file — I2–I10 precedent; `_legacy.py` stays
grandfathered). Pyright scope UNCHANGED (`psh/` minus `_legacy.py`) — D-i8-7/D-i9-8/
D-i10-9 inherited (`psh/charts.py` is inside the gate and clean).

## 6. Behavior bar & invariants applied (§8/§9)

- Four goldens byte-identical (Invariant 1): the goldens run the chart path through
  the real `main()` (its-wws-test1/test2/nonumich/cdnchange all render a chart), so a
  crash or HTML/txt-visible change trips them. **They do not pin chart bytes** — the
  increment-scoped evidence is:

  **Chart-payload hash procedure** (run on the pre-move tree, then on the post-move
  tree, same environment; both outputs pasted in §9): from repo root,

  ```bash
  python - <<'EOF'
  import email, hashlib, pathlib, sys
  sys.path.insert(0, "tests"); sys.path.insert(0, ".")
  from conftest import make_workdir, build_rendered_report, E2E_SITE
  import tempfile
  work = make_workdir(pathlib.Path(tempfile.mkdtemp()))
  build_rendered_report(work)
  msg = email.message_from_bytes((work / "build" / f"{E2E_SITE}.eml").read_bytes())
  pngs = [p.get_payload(decode=True) for p in msg.walk()
          if p.get_content_type() == "image/png"]
  for i, b in enumerate(pngs):
      print(i, len(b), hashlib.sha256(b).hexdigest())
  EOF
  ```

  The chart is the PNG whose filename part starts `pantheon-traffic_` (the other is
  the wordmark banner). Equal hashes before/after = the move is byte-preserving.
- Invariant 8: no column-0 `f"""` literal in scope (§3; implementer re-confirms).
- Invariant 9: no `sc` name removed; nothing new documented on the façade.
- Invariant 11: the `--only-warn` gate stays exactly where it is (chart code was
  always after it; `--update`/`--import-older-metrics` never reach the chart).
- Invariants 4–7, 10: untouched paths; no console prints move except the region's own
  `sc.debug` banner (moves verbatim; §8 sanctions stdout changes anyway); no interlock
  or fixture change.
- §8 rows: emails byte-identical (goldens + §6 hashes); artifacts/config/exit codes
  untouched; no csv values change (the region emits no notices).

## 7. Task shape (for the plan)

Task 1 — tests RED: `tests/integration/test_charts.py` written against the D-i11-1
signature, shown failing for the right reason (`ModuleNotFoundError: psh.charts`) —
the `mattpocock-skills:tdd` red step. Also run §6's hash procedure on the pre-move
tree and record the baseline hashes.

Task 2 — the move (Deliverables A–B) turning Task 1 green atomically (a partial move
cannot be green — I5/I6 single-commit precedent). Gates: full `--fast` suite green
with collected count = baseline + new tests (I10 close full-tier was 991 passed / 1
skipped, i.e. `--fast` ≈ 989 passed / 1 skipped / 2 deselected — re-verify before
Task 1 and pin the measured figure), goldens diff empty, §6 hashes equal, broad ruff
clean on `psh/charts.py`, narrow ruff whole-tree clean, pyright 0 errors.

Task 3 — docs/memory/ledger (§8) + acceptance pasted into §9.

## 8. Documentation & memory obligations (same change, §7)

- CLAUDE.md: § Single-module core gains the `psh/charts.py` sentence (what lives
  there, the 13-param threading, re-imported by `_legacy.py`, same import-back
  pattern); § Testing's conftest note reworded — MPLBACKEND must precede the load
  because **`psh/charts.py`** imports `matplotlib.pyplot` (reached transitively via
  `_legacy`'s re-import); LEDGER I10's "chart region consumes shaped locals" prose in
  § Single-module core / the campaign section updated to name the module.
- Memory: update `modularization-campaign.md` progress line.
- `LEDGER.md`: I11 entry — D-i11-2 (cap geometry into the prologue), D-i11-3 (the two
  chart-only derivations relocated; `dates` passed), D-i11-4 (prologue init vs scoped
  ignores), D-i11-6 (no committed image golden, why; the hash evidence), D-i11-7
  (precondition documented), ratchet dispositions, discovered tasks, open questions
  for I12 (which inherits: the `escape_url` bridges in `psh/gather.py`, the
  `Notice`-adoption candidates, the B55 `chart_image` consumer, the annual-billing
  relocation with its untested-call-site obligation from LEDGER I1).

## 9. Acceptance (commands run and output pasted at close — never summarized)

Filled 2026-07-23 at increment close. Live tier ran (credentials present via the
cached machine token; `terminus auth:login` succeeded), so no live-tier-skipped
ledger note is needed. Increment start SHA: `2c79b05`.

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
LLM_SUMMARY passed=996 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
107 snapshots passed.
996 passed, 1 skipped, 4 warnings in 45.01s
EXIT: 0
```

996 = the Task 1 measured `--fast` baseline 989 + 5 new `test_charts.py` tests + 2
live-tier tests (the I4–I10 +2-live-tier pattern). The 1 skip is
`test_db_credentials.py`'s `importorskip("MySQLdb")` on a sqlite-only install.

### `git diff 2c79b05 -- tests/e2e/__snapshots__/ | wc -l`

```
$ git diff 2c79b05 -- tests/e2e/__snapshots__/ | wc -l
0
```

Four goldens byte-identical across the increment, confirmed.

### `uvx ruff check --config ruff-broad.toml psh/charts.py`

```
$ uvx ruff check --config ruff-broad.toml psh/charts.py
All checks passed!
```

### `uvx ruff check .` (narrow PD set, whole tree)

```
$ uvx ruff check .
All checks passed!
```

### §6 chart-payload hashes (before = pre-move tree, after = post-move tree)

```
$ cat development/2026-07-23-mod-I11-charts/chart-hashes-before.txt
pantheon-traffic-email-banner.png 20638 8fbf823669bd56051f9978629424ed4cccd2f16d72537ac2ad72c86f54ac3fce
pantheon-traffic_its-wws-test1_20260331.png 59810 2bca16a2f8a842df1a31fec7ecbf7d23cdd0eb0e6883f8150cd59b60f3c9afcb

$ cat development/2026-07-23-mod-I11-charts/chart-hashes-after.txt
pantheon-traffic-email-banner.png 20638 8fbf823669bd56051f9978629424ed4cccd2f16d72537ac2ad72c86f54ac3fce
pantheon-traffic_its-wws-test1_20260331.png 59810 2bca16a2f8a842df1a31fec7ecbf7d23cdd0eb0e6883f8150cd59b60f3c9afcb
```

Chart payload byte-identical (`2bca16a2…9afcb` both sides); the task reviewer also
reproduced the pre-move hash independently from a `2c79b05` worktree.

## Observations (recorded for the ledger, no action this increment)

- The `estimates` def/use guards differ (`!= -1` at the def, `>= 0` at the use) —
  equivalent today because `estimate_month_visits` returns either `-1` or a
  non-negative int; moved verbatim, not unified (a move may not change behavior).
- `est_bars`/`bars` rely on for-loop variable leakage past the `for ax in axs:` loop
  (last iteration's containers are the ones capped). Deliberate in the original;
  moved verbatim; the scoped ignores record pyright's inability to see `axs` is
  never empty.
- The surge cap block draws `vlines` at `x + w - 0.00001` — a hand-tuned epsilon;
  moved verbatim, left alone.
