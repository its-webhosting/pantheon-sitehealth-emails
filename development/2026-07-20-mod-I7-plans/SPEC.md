# SPEC — Increment I7: `psh/plans.py` (plan catalog + cost model + recommendation flow + D7)

**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
authority: §11 row I7 (B9, B12 plans part, B17, B47; a47418c lines 967–976, 1128–1208,
1254–1280 — drifted, current equivalents below, verified 2026-07-20). Module map: §3.1
(`psh/plans.py` row). What stays in `main()`: §3.3. Types: §6 (`PlanInfo`/`PlanCatalog`
row). Decision D7 (`--only-warn` runs the recommendation): §2 row D7, §11 row I7.
Contract keys: §4 ("plan/cost keys `current_plan`, `recommended_plan`, `plan_costs`,
`savings` (I7, at `site_pre_render`)"). Parallel-ready: §3.4. Obligations: §7. Behavior
bar: §8 (one amendment, D-i7-5). Invariants: §9. Ratchet: §13.

**Carried obligations this spec discharges** (LEDGER I6 "Open questions for I7" +
LEDGER I1 items carried to I7):

1. **D-i6-2 discharge** — replace `psh/traffic.py`'s call-time
   `from psh._legacy import overage_blocks` with a module-level
   `from psh.plans import overage_blocks` (MUST, per LEDGER I6).
2. **B47 downgrade-path behavior decision** (LEDGER I1 Obs. 3) — decided in D-i7-4.
3. **`its-recommends-plan` comma-in-csv** (LEDGER I1 Obs. 5, LEDGER I3 candidates
   list) — decided in D-i7-5.

**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I6), `CLAUDE.md`
(§ Per-site report pipeline, § Database, § Testing), `BLOCKMAP.md` rows B9, B12, B17,
B42–B47 (B42–B46 for the D7 boundary), `prompts/directives.md`,
`prompts/implementation-standards.md`.

## Glossary (delta over CAMPAIGN.md's)

- **Move set** — the six module-level items Deliverable A moves verbatim
  (`cost_table_columns`, `overage_blocks`, `contract_year_end`, `plan_costs`,
  `build_plan_over_time`, `build_plan_recommendation_notice`).
- **Catalog** — the new `PlanCatalog` (§6's `PlanInfo`/`PlanCatalog`), the typed view
  over `[Pantheon].plan_info` + the two overage constants.
- **Recommendation flow** — the B47 core extracted as `recommend_plan(...)`
  (Deliverable C): op-window load → `plan_costs` → selection → downgrade guardrails →
  notice/savings → cost-table rows.
- **The gate** — `main()`'s `--only-warn` dump-and-`continue` (B42), which D7 moves
  *after* the recommendation flow.

## 1. Scope (exhaustive) and non-scope

In scope (current `psh/_legacy.py` lines, verified 2026-07-20):

1. **Move** into a new `psh/plans.py` (gated from birth): `cost_table_columns`
   (`:54–59`), `overage_blocks` (`:395–397`), `contract_year_end` (`:400–402`),
   `plan_costs` (`:405–483`), `build_plan_over_time` (`:486–510`),
   `build_plan_recommendation_notice` (`:1278–1325`). Bodies verbatim except the
   Deliverable-A-named edits (annotations per §6/§7-obligation-3; the D-i7-5 csv edit;
   ratchet dispositions per §5).
2. **New type** (Deliverable B): `PlanCatalog` / `PlanInfo` in `psh/plans.py`
   absorbing B12's plan-info normalization (`:1445–1457`) and carrying B9's overage
   constants as fields (the two reads `:1411–1412` stay verbatim in `main()` per §3.3
   "overage constants … stay" and feed `from_config` — D-i7-1/D-i7-2; this also
   preserves the failure timing of a missing-constant config on the
   `--create-tables` path, which exits before the catalog is built).
3. **Extract** B17's Elite-SKU body (`:1552–1574`) as `resolve_plan_name(site)`
   (D-i7-3) and B47's recommendation core (`:3200–3337`) as `recommend_plan(...)`
   (D-i7-7), loop control staying in `main()` (D-i7-1).
4. **D7**: reorder `main()`'s per-site tail so the recommendation flow runs before the
   `--only-warn` gate (`:2760–2764`), which then includes `its-recommends-plan` rows
   in its csv dump (D-i7-6 flow diagram).
5. **Contract keys** `current_plan`, `recommended_plan`, `plan_costs`, `savings` at
   `site_pre_render` (§4): `CONTRACT` registry entries, a `stuff_plans_contract()`
   stuffer in `psh/plans.py` (the `dns_classify.stuff_dns_contract` producer-module
   precedent), the call in `main()` immediately before
   `sc.invoke_hooks("site_pre_render", ...)` (`:3410`), CLAUDE.md table row, and the
   `test_contract_registry.py` pin — D-i7-8.
6. **D-i6-2 discharge** in `psh/traffic.py` (module-level import; delete the bridge
   comment at `psh/traffic.py:10–13` and the call-time import at `:169–170`).
7. **Re-import** every moved/new name into `psh/_legacy.py` (I2/I3/I5/I6 pattern) so
   `main()`'s call sites and the tests' `psh.<name>` references (`psh.overage_blocks`,
   `psh.contract_year_end`, `psh.plan_costs`, `psh.build_plan_over_time`,
   `psh.build_plan_recommendation_notice`, `psh.cost_table_columns` — 7 test files,
   grep-verified) resolve unchanged.
8. **New tests** (test-first, `mattpocock-skills:tdd`) per §7-Tests below; sanctioned
   updates to the two `its-recommends-plan` csv pins (D-i7-5).
9. **CAMPAIGN.md §8 amendment** (D-i7-5) + README TODO addition (D-i7-4) +
   docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8).

NOT in scope:

- **Chart-region code** (B44/B45, `:2799–2830`, `:2833–3164` post-reorder): I11. The
  D7 reorder hoists only what §D-i7-6 names (`last_day`, `plot_right_date`, the
  empty-`plan_on_day` guard, `days`, `plan_over_time`, `dates`, `estimate`) — all
  value-identical, none chart-rendering.
- **B46** (`db_retry(build_traffic_table_rows)` call site, `:3178–3196`): stays in
  `main()`. (Originally specced to stay after the gate as "render-only"; final review
  proved it is NOT render-only — it persists the overage-protection rows the
  recommendation reads — so the shipped fix hoists it above `recommend_plan` on both
  paths. See the corrected D-i7-6 first Consequences bullet.)
- **B12's non-plans half** (wordmark read `:1437–1438`, `load_news_items()`
  `:1440–1443`): stays; §3.1 assigns `load_news_items` to `psh/configuration.py`
  (moved at I3) and the wordmark to render/mail (I12).
- **B13 date window + cap geometry** (`:1459–1475`): §3.3 keeps the date window in
  `main()`; cap geometry is I11. `contract_year_end`'s *def* moves (it is in §3.1's
  plans row); its call site (`:1464`) stays.
- **B50/B51 annual billing** (`plan_info[...]["cost"]` reads `:3380`, `:3400`): I12.
  They read the raw dict via `main()`'s `plan_info` alias, which survives (D-i7-2).
- **Smell notices** (`:3339–3341`): I10. `--only-warn` continues to exclude them
  (today's behavior; only the recommendation moves ahead of the gate — D7's TODO
  names only "plan recommendations").
- **`Notice` adoption** for `its-recommends-plan`: deferred (D-i7-9) — its csv keeps
  extra fields, which `Notice` cannot carry without the §6 amendment LEDGER I3
  reserved for the first adopting increment. It stays a dict.
- No owner-facing downgrade notice (D-i7-4 → README TODO); no golden/fixture
  refreshes (Invariants 1, 10 — syrupy snapshot updates outside the four e2e goldens
  are NOT golden refreshes, per CLAUDE.md § Testing); no config keys; no new `sc`
  façade names (nothing in the move set is on `sc`; the two globals
  `cost_table_columns`/`fqdn_re` — only `fqdn_re` is exposed, and it stays put).
- No `_legacy.py` import removals beyond what the move orphans (implementer verifies;
  expectation: `copy` may orphan if `recommend_plan` takes its only use — confirm
  with grep, the I3 rule "remove only what this change orphans").

## 2. Architecture decisions

### D-i7-1: bodies move; bootstrap ordering and loop control stay in `main()`

Same §11-vs-§3.3 tension I6 resolved (D-i6-1), same reading (**ledger note**): §3.3
keeps "overage constants + date window (B9...)" and the site-loop skeleton in `main()`
as *ordering*; §11 row I7 moves the *bodies*. Concretely:

- B9+B12 → `catalog = PlanCatalog.from_config(sc.config["Pantheon"])` in `main()` at
  the current B12 position; `main()` keeps aliases
  `plan_info = catalog.plan_info` / `plan_names = catalog.plan_names` (raw-dict views)
  so the chart (I11) and annual-billing (I12) regions are untouched.
- B17 → `main()` keeps the `continue` and the B17-tail inits (`:1575–1578`); the
  whole body — including the Elite check, which becomes the function's early
  return (see D-i7-3, which is authoritative for the seam) — becomes
  `resolve_plan_name(site) -> str | None` in `psh/plans.py` (`None` = transient
  failure → `main()` prints nothing extra and `continue`s; the two fatal branches
  keep their `sys.exit` inside the function — exit codes/messages preserved, §8).
- B47 → `recommend_plan(...)` (D-i7-7); `main()` unpacks the result into the same
  locals the template reads (`:3415–3444` untouched).

### D-i7-2: `PlanCatalog` normalizes in place; `plan_costs` keeps its dict signature

`PlanCatalog.from_config(pantheon_config)` performs B12's `"-"` → `None` normalization
**mutating the config sub-dict exactly as today** (`sc.config["Pantheon"]["plan_info"]`
is read again by I11/I12 regions via the alias; a non-mutating copy would fork two
views of the same data — PD#1). It exposes: `plan_info` (the raw normalized dict —
alias source), `plan_names` (`list(plan_info.keys())`, order-preserving),
`plans: dict[str, PlanInfo]` (frozen-dataclass typed view: `cost: float`,
`traffic_limit: int`, `upgrade_at: int`, `upgrade_to: str | None`,
`downgrade_to: str | None`), `overage_block_size: int`, `overage_block_cost: float`
(B9's two reads; today's `KeyError`-on-missing behavior preserved — CLAUDE.md
§ Database precedent: no code defaults). `plan_costs` moves **verbatim** with its
10-param dict-based signature — pinned by `test_plan_costs.py`/`test_property_plan.py`
and by its (post-extraction) `recommend_plan` call site; new code (`recommend_plan`)
reads typed fields via `catalog.plans` where it touches plan attributes, and passes
the raw pieces into `plan_costs` unchanged.
`PlanCatalog` is the one §6 type introduction; nothing else is retyped.

### D-i7-3: `resolve_plan_name` seam

`resolve_plan_name(site: dict) -> str | None`: non-Elite → returns
`site["plan_name"]` unchanged; Elite → `terminus("plan:info", ...)` body verbatim
(transient/undecodable → existing error print + `None`; missing/unknown SKU →
existing print + `sys.exit("Bailing out.")`). `main()`:
`plan_name = resolve_plan_name(site)` / `if plan_name is None: continue` /
`site["plan_name"] = plan_name`. (Uses the `terminus` gateway wrapper — `psh/plans.py`
imports it from `psh.gateway`, testable via the `gateway` fixture.)

### D-i7-4: downgrade path — no new owner notice; `site_savings` gap fixed

LEDGER I1 Obs. 3 asked I7 to decide intended behavior. Decision:

- **No owner-facing downgrade notice.** A new notice is new report content — §1
  non-goals bar exactly that (D9 reasoning: golden churn mid-campaign). Disposition:
  **README TODO** ("notify owners of downgrade recommendations; the dead
  `extra_message` deleted in I1 was presumably meant for this").
- **The non-Basic downgrade `site_savings` omission is fixed.** Today a downgrade
  recommendation to a non-Basic plan appends nothing — invisible to the operator's
  end-of-run savings summary, whose whole purpose is finding savings. `site_savings`
  is **stdout-only** (verified: `finish_run` pprints it + totals, `:736–741`; it is
  in no artifact), so §8 sanctions the change freely. `recommend_plan` returns a
  `savings_entry` for **every** changed-plan recommendation surviving the guardrails
  (upgrade, downgrade-to-Basic as today, and now non-Basic downgrade); entry shape
  unchanged (`site`/`savings`/`current_plan`/`recommended_plan`). RED test first on
  the old omission.

### D-i7-5: `its-recommends-plan` csv comma fix (§8 amendment)

The csv field embeds `{savings:,.2f}` — a thousands **comma inside a comma-separated
row**, so any savings ≥ $1,000 splits the field and the row's column count varies
(LEDGER I1 Obs. 5). D7 is about to grow this row's reach (`--only-warn` runs feed
`-notices.csv`), so it is fixed **now, before D7 widens the blast radius**: the csv
field becomes `{savings:.2f}` (fixed 5-column row). The HTML/text bodies keep
`{savings:,.2f}` (owner-facing copy unchanged; not rendered by any golden — §10's
grep shows zero occurrences). §8 restricts notice-csv *value* changes to I1/I12, so
this is a **CAMPAIGN.md §8 amendment** (add I7 + this code to the sanctioned list),
applied in the closing commit with its ledger entry, per the CAMPAIGN.md preamble.
The two existing pins (`test_plan_recommendation_notice.py` asserts, the
`test_plan_recommendation_notice_render.ambr` snapshot) are updated in the same
change — sanctioned, not a weakening.

### D-i7-6: the D7 reorder (flow diagram, PD#8)

```
today:  …gather → php-eol → [GATE --only-warn: dump csv, continue]
        → B43 aggregation → plan_over_time prep → chart prep (estimate inside)
        → chart build → traffic table (B46) → B47 cost model/recommendation
        → smells → recipients/subject → site_pre_render → render/send

after:  …gather → php-eol
        → B43 aggregation (+pprint)                          (:2766–2772, unmoved code, new position n/a — gate moves, not B43)
        → last_day/plot_right_date/empty-guard/days/plan_over_time  (:2775–2794)
        → dates (:2797) → estimate (:2831–2832)              [hoisted from chart prep]
        → first/last_plan_day → site_plan_start
        → traffic table (B46: persists+commits the OP rows)   [hoisted in the final-review
                                                              fix — see the first
                                                              Consequences bullet]
        → RECOMMENDATION FLOW: rec = recommend_plan(...)     [B47 core, now in psh/plans.py]
          main() unpacks rec; appends rec.savings_entry
        → [GATE --only-warn: dump csv (now incl. its-recommends-plan), continue]
        → chart prep remainder (visits/visits_covered/xbins/estimates_by_month/…)
        → chart build → smells → recipients/subject
        → stuff_plans_contract(...) → site_pre_render → render/send
```

Consequences, each argued safe:

- **DB write/read order preserved (corrected in final review).** The initial D7 reorder
  put `load_overage_protection_window` (recommend_plan's read) *before*
  `build_traffic_table_rows` — which is **not** a pure read: it persists+commits this
  window's `pantheon_overage_protection` rows (its docstring says so), and recommend_plan
  reads them back. On a first render, with no prior OP rows, the read then missed and the
  cost model fell back to its January-reset simulation, rendering a different (and
  run-order-dependent) cost table. Shipped resolution: `main()` hoists the traffic-table
  build (and the `first_plan_day`/`last_plan_day`/`site_plan_start` locals it needs) above
  the recommendation, so the write-commit precedes the read on every path — full-report
  output returns byte-identical to baseline and deterministic. Consequence, human-approved:
  `--only-warn` now runs that build too and persists OP rows (it already writes traffic
  rows), so its recommendation matches the full report's. recommend_plan's one-ranged-query
  comment is corrected to name the write as running before it. (Ledger records the
  deviation.)
- **`--only-warn` now performs the op-window DB read and `plan_costs`** for sites
  with >4 in-window months — the point of D7.
- **The empty-`plan_on_day` guard** (its console message included) now also runs on
  `--only-warn` (stdout change, §8-free; behavior change is D7's sanctioned purpose:
  a new site gets `plan_on_day = {end_date: current}`, one month, ≤4 → no
  recommendation, same as the full path).
- **Goldens byte-identical** (Invariant 1): all four take the ≤4-month path
  (`months_until_recommendations > 0`), where `recommend_plan` returns the
  same defaults today's `:3202–3214` inits produce and no DB op-read happens
  (the `len(v) > 4` guard is unchanged); every hoisted value (`estimate`, `dates`,
  `plan_over_time`, …) is computed from the same inputs by the same expressions, so
  every template value is bit-identical. `test_recommendation_e2e.py` covers the
  >4-month full path unchanged.
- `all_warnings` row content on `--only-warn` gains `its-recommends-plan` rows
  (D7's deliverable — `-notices.csv` row *shape* unchanged at 5 columns via D-i7-5;
  §8 "structure NEVER change" is honored, content growth is the sanctioned D7
  change). Full-report-path `all_warnings` content is unchanged (notices were always
  dumped post-recommendation there, B56).

### D-i7-7: `recommend_plan` seam

```python
recommend_plan(db_session, site, catalog, visits_by_month, site_plan_start,
               estimate, start_date, end_date, portal_site_id, site_context)
    -> PlanRecommendation
```

(`site_plan_start`, not `plan_over_time`: the B47 core's only use of
`plan_over_time` is the one-line `site_plan_start` derivation at `:3177`, and
`main()`'s B46 call needs that same local after the gate — so the line stays in
`main()` before the call, and the function takes the derived date.)

`PlanRecommendation` (frozen dataclass, `psh/plans.py`): `months_until_recommendations:
int`, `median_visitors` (0 when no recommendation), `cost_same: dict`,
`costs_median: dict`, `costs_best: dict`, `cost_table_rows: dict` (all `{}` when ≤4
months), `current_plan: str`, `recommended_plan: str` (== `current_plan` when
unchanged), `current_plan_index: int`, `recommended_plan_index: int` (today's
end-state values, including the guardrail-mutation subtleties — verbatim logic),
`savings: float` (0.0 when none), `estimate_start_date` / `estimate_end_date:
datetime.date`, `savings_entry: dict | None`. Internals verbatim from `:3200–3337`:
`site_plan_start` from `plan_over_time[0]["start"]`, the `k`/`v` filter, the op-window
`db_retry` load + `op_lookup` closure, `plan_costs`, `min(costs_best)`, the
Basic/Performance-Small guardrails, the upgrade-branch
`site_context.add_notice(build_plan_recommendation_notice(...))` (the function adds
the notice itself — it holds `site_context`, the I6 flow-function pattern), the
cost-table-rows build, the estimate-date computation. `main()` appends
`rec.savings_entry` to `site_savings` when not `None` (run accumulators stay in
`main()` — §3.4, I13's `RunState`). `end_date_yyyy_mm` is derived inside (one caller,
one derivation).

### D-i7-8: contract stuffing

`stuff_plans_contract(site_context, current_plan, recommended_plan, plan_costs,
savings)` in `psh/plans.py`; `CONTRACT["site_pre_render"]` becomes
`("current_plan", "recommended_plan", "plan_costs", "savings")`. Key shapes
(CLAUDE.md table row, same wording discipline as the existing rows): `current_plan`
(str), `recommended_plan` (str; == `current_plan` when no change recommended or not
enough data), `plan_costs` (dict `{"same": {plan: float}, "median": {plan: float},
"best": {plan: float}}`; `{}` when ≤4 in-window months), `savings` (float; `0.0` when
no recommendation). Stuffed in `main()` from the `PlanRecommendation` just before
`invoke_hooks("site_pre_render", ...)` — full-report path only (gating unchanged,
Invariant 11; `--only-warn` never reaches `site_pre_render`, exactly as today).
`validate_hooks` conditions are unaffected (new core-produced keys; no hook consumes
them yet — `site_pre_render` keeps "no consumer yet" status but is no longer
key-empty).

### D-i7-9: `Notice` adoption deferred (unchanged from LEDGER I3)

`its-recommends-plan` keeps 3 extra csv fields even after D-i7-5; adopting `Notice`
requires the §6 csv-field amendment reserved for the first adopting increment. Not
this one — the dict form moves verbatim. (LEDGER I3's candidates list shrinks by the
"or I7" option; noted in this increment's ledger entry.)

## 3. `psh/plans.py` module shape (imports; no cycles)

Module-level imports: stdlib (`copy` if `recommend_plan` keeps its `copy.copy(costs_best)`,
`datetime`, `dataclasses`), `numpy`, `import script_context as sc` (I6 `psh/traffic.py`
precedent), `from psh.db import db_retry, load_overage_protection_window`,
`from psh.gateway import terminus` (for `resolve_plan_name`). **NEVER imports
`psh.traffic`** (traffic imports plans for `overage_blocks` — D-i6-2 discharge) and
never `psh._legacy`. `script_context` does not import `psh.plans`; `psh.db`/
`psh.gateway` import neither — no cycle. `psh/_legacy.py` re-imports the Deliverable-A
six + `PlanCatalog` + `PlanInfo` + `PlanRecommendation` + `resolve_plan_name` +
`recommend_plan` + `stuff_plans_contract`.

## 4. Deliverables

- **A — the move**: six defs/globals → `psh/plans.py`, bodies verbatim except: real
  annotations (§6/§7-ob-3: `overage_blocks(overage: int, overage_block_size: int) ->
  int`; `plan_costs(...) -> tuple[dict, dict, dict, float]`-shaped real annotation
  replacing none-present; `build_plan_over_time(plan_on_day: dict, plot_right_date:
  datetime.date) -> list`), the D-i7-5 csv edit in
  `build_plan_recommendation_notice`, ratchet dispositions (§5). The four column-0
  `f"""` literals in `build_plan_recommendation_notice` move **verbatim**
  (Invariant 8 — byte-compare, never `git diff -w`).
- **B — `PlanCatalog`/`PlanInfo`** (D-i7-2) + `main()` B9/B12 replacement.
- **C — flow extraction**: `resolve_plan_name` (D-i7-3), `recommend_plan` +
  `PlanRecommendation` (D-i7-7), `main()` B17/B47 replacement.
- **D — D7 reorder** (D-i7-6) incl. the `savings_entry` append and gate move.
- **E — contract** (D-i7-8): registry, stuffer, `main()` call, CLAUDE.md row,
  `test_contract_registry.py` pin.
- **F — D-i6-2 discharge** in `psh/traffic.py`.
- **G — tests** (§7-Tests), **docs/amendment/ledger** (§1 item 9).

## 5. Ratchet (§13) — expected findings, MUST be confirmed against real tool output

`psh/plans.py` born gated (broad ruff + pyright standard, 0 findings after
dispositions). Anticipated (the I3 lesson: this table is a prediction, the
implementer runs the tools and corrects it in the task report): `PLR0913` on
`plan_costs` (10 params — pinned signature; noqa with reason) and on
`recommend_plan` (10 params; noqa: one per flow input — the I6
`build_traffic_table_rows` precedent); `C901`/`PLR0912`/`PLR0915` on `plan_costs` and `recommend_plan`
(verbatim move, no algorithmic redesign — §3.1); `FBT001` on
`build_plan_recommendation_notice`'s positional `umich: bool` → make it keyword-only
(`*, umich: bool`) and update the one call site + unit tests (signature change is
in-repo-only, grep-verified); `PLR2004` candidates in the guardrail indexes
(`> 1`) — ruff's allowlist covers 1, expect none (I3 lesson); `S101` none expected.
`np.median` returns `np.floating` — pyright may want `float(...)` around
`median_visitors`; if so, wrap at the return boundary only if provably
value-identical for the f-string formats that consume it, else annotate honestly.
Nothing leaves `ruff-broad.toml` `extend-exclude` (fresh gated file, I2–I6 precedent).

## 6. Behavior bar (§8) application

| Surface | This increment |
|---|---|
| Four goldens | byte-identical (D-i7-6 argument; `./run-tests` proves) |
| Artifacts structure | unchanged (`-notices.csv` stays 5-col for this code — D-i7-5 *fixes* the variable-count defect) |
| Notice csv values | ONE sanctioned change via §8 amendment: `its-recommends-plan` savings field format (D-i7-5) |
| stdout | changes freely (reordered debug output, guard message on `--only-warn`, savings summary gains non-Basic downgrade entries) |
| Config | no changes |
| Exit codes / resume / gating | unchanged (B17 fatals keep `sys.exit`; `--only-warn` still never renders/sends/reaches `site_pre_render`) |

## 7. Tests (test-first at these seams; RED shown where behavior changes)

- **Unit `tests/unit/test_plan_catalog.py`** (new): `PlanCatalog.from_config` —
  `"-"`→`None` normalization (and that the *config dict itself* is mutated, the
  D-i7-2 contract), typed `PlanInfo` fields, `plan_names` order, overage constants,
  `KeyError` on missing keys.
- **Unit — existing** `test_plan_math.py` / `test_plan_costs.py` /
  `test_plan_over_time.py` / `test_property_plan.py`: untouched (resolve via
  `psh.<name>`). `test_plan_recommendation_notice.py` + render snapshot: csv-pin
  update only (D-i7-5).
- **Integration `tests/integration/test_plan_flow.py`** (new; the
  `test_traffic_flow.py` sibling): `recommend_plan` against a seeded sqlite session —
  (a) ≤4 months → default `PlanRecommendation`, no DB op-read, no notice; (b) upgrade
  → notice added + `savings_entry`; (c) downgrade-to-Basic with Performance-Small
  floor (guardrail, `savings == 0`, entry appended — today's behavior); (d)
  downgrade-to-Basic better-intermediate-alt path; (e) **non-Basic downgrade →
  `savings_entry` present — RED first against today's omission** (D-i7-4); (f)
  no-change → `savings_entry is None`, no notice. Plus `resolve_plan_name` via the
  `gateway` fixture: non-Elite passthrough / Elite happy / transient → `None` /
  missing-SKU + unknown-SKU → `SystemExit` (message pinned).
- **Contract**: `test_contract_registry.py` extended — `stuff_plans_contract` pinned
  against `CONTRACT["site_pre_render"]`; `test_hook_dag.py` stays green (proves the
  new core keys break no real package's declarations).
- **e2e `tests/e2e/test_only_warn_e2e.py`** (new; D7): six seeded months at **6×**
  the standard seed volume (`seed_traffic` gains a backward-compatible
  `visits_scale=1` keyword; the default recipe's median 35,960 lands in the
  Basic-guardrail case, which adds NO notice — at 6× the cost model recommends an
  upgrade, `Performance Small` → `Performance Large`, savings `2755.00` against
  `minimal.toml`'s plan table) + `--only-warn` → exit 0, stdout contains the
  5-field `its-recommends-plan,...` csv row, **no** `build/<site>.html` written;
  and a ≤4-month `--only-warn` run → no `its-recommends-plan` row. (`run_program`
  permits `--only-warn`; interlock untouched — Invariant 7.) **RED first**: the
  >4-month assertion fails on today's code (gate precedes the recommendation).
- **Goldens**: all four byte-identical; `test_recommendation_e2e.py` unchanged and
  green (it pins the >4-month full path incl. the Performance-Small guardrail).

## 8. Acceptance (pasted at close, §16)

Full `./run-tests` (live tier if credentials present, else `--fast` + ledger note);
all three gates; goldens byte-identical (`git diff <start-sha> --
tests/e2e/__snapshots__/` empty — the render-tier `.ambr` under
`tests/integration/__snapshots__/` MAY change per D-i7-5); collected count = current
baseline (790 passed / 1 skipped full-tier at I6 close; `--fast` baseline re-measured
at start) plus this increment's new tests; ruff-broad + pyright clean on
`psh/plans.py` and `psh/traffic.py`.

## 9. Acceptance results

Pasted at increment close (2026-07-21, HEAD = `15fb36d` + this closing docs commit):

```
$ ./run-tests --llm   (FULL suite, live tier included — Terminus credentials present)
LLM_SUMMARY passed=810 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
27 snapshots passed.
810 passed, 1 skipped in 42.20s
Linting (ruff, narrow PD set) ... [pass]
Linting (ruff-broad.toml, campaign ratchet) ... [pass]
Type-checking (pyright, campaign ratchet) ... [pass]

$ git diff 3195c81 -- tests/e2e/__snapshots__/ | wc -c
0
```

`--fast` tier at close: 808 passed / 1 skipped / 2 deselected — baseline 788 + 20 new
tests (4 plan-catalog, 5 resolve_plan_name, 6 recommend_plan flow, 2 contract-registry,
2 only-warn e2e, 1 recommendation-determinism e2e). The one skip is
`test_db_credentials.py`'s `importorskip("MySQLdb")` on a sqlite-only install. Four e2e
goldens byte-identical across the increment (0-byte diff above). The
`test_plan_recommendation_notice_render.ambr` render-tier snapshot changed only its two
`csv:` lines (sanctioned, D-i7-5).
