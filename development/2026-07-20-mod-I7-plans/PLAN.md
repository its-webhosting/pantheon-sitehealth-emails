# I7 — `psh/plans.py` (plans layer + D7 `--only-warn` recommendation) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch
> every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via
> `mattpocock-skills:tdd` (NOT superpowers TDD). The authoritative design is `SPEC.md` in this
> folder — read it in full; this plan is the step sequence, the SPEC carries rationale,
> decisions (D-i7-1…9), and invariants.

**Goal:** Move the six plan/cost defs into a new gated `psh/plans.py`, add
`PlanCatalog`/`PlanInfo`, extract B17 (`resolve_plan_name`) and the B47 recommendation core
(`recommend_plan`), run the recommendation before the `--only-warn` gate (D7), publish the
four `site_pre_render` contract keys, and discharge I6's `overage_blocks` bridge — four e2e
goldens byte-identical throughout.

**Architecture:** Import-back move (I2/I3/I5/I6 precedent): `psh/_legacy.py` re-imports every
moved/new name so `main()`'s call sites and the tests' `psh.<name>` references resolve
unchanged. Flow functions signal via return values; every `continue` and the two run
accumulators stay in `main()` (SPEC D-i7-1/D-i7-7). `psh/plans.py` imports
`psh.db`/`psh.gateway`/`psh.configuration`/`sc` and is imported by `psh/traffic.py`
(module-level `overage_blocks`) — plans NEVER imports traffic or `_legacy` (SPEC §3).

**Tech Stack:** Python 3.12+, SQLAlchemy 2.x, numpy, ruff (`ruff-broad.toml` `select=ALL`),
pyright (standard), pytest + syrupy.

## Global Constraints

- **Four e2e goldens byte-identical** (Invariant 1). `--update-goldens` is allowed ONLY for
  the Task 1 render-tier snapshot refresh (`test_plan_recommendation_notice_render`), whose
  diff MUST touch only `csv:` lines. Verify `git diff 3195c81 -- tests/e2e/__snapshots__/`
  is empty at each task end.
- **`psh/plans.py` passes the full gate from birth**: `uvx ruff check --config
  ruff-broad.toml psh/plans.py psh/traffic.py` → "All checks passed!"; pyright (via
  `./run-tests`, NOT `uv run pyright` — uv.lock churn) → 0 errors. SPEC §5 findings table is
  a *prediction*: run the tools, record actual findings + dispositions in the task report
  (I3 lesson).
- **Moved bodies are verbatim** except the SPEC-named edits (repeated inline per task). Task
  reports MUST paste the region diff proving the only differences are those edits. The four
  column-0 `f"""` literals in `build_plan_recommendation_notice` move byte-identically
  (Invariant 8 — never justify with `git diff -w`).
- **No `sc` name removed** (Invariant 9); nothing new joins the documented façade.
- **Safety interlock untouched** (Invariant 7): tests use `--only-warn`, never
  `--all`/`--for-real`.
- **No import removals in `_legacy.py` except what this change orphans** — grep before
  deleting; expectation: `copy` becomes orphaned in `_legacy.py` when B47 moves (its only
  use is `copy.copy(costs_best)` at `:3270`) — verify with `grep -n "copy\." psh/_legacy.py`
  and remove `import copy` only if nothing else remains.
- Clear stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 note).
- Baseline commit (I7 start) = `3195c81`. `--fast` baseline measured 2026-07-20 at that
  commit: **788 passed / 1 skipped / 2 deselected**, all three gates green. Track the
  collected-count delta per task.
- Every task report cites Spine directives by number with a verbatim quote (agent config).
- The inner loop is `./run-tests --fast --llm`; run it at every task end.
- Commit style: `refactor(campaign-I7): …` / `test(campaign-I7): …` / `docs(campaign-I7): …`
  (I6 precedent). Commit only at green.

**Current-line anchors** (verified 2026-07-20 against `3195c81`; re-grep before editing —
they drift within this increment as tasks land): `cost_table_columns` `:54–59`;
`overage_blocks` `:395–397`; `contract_year_end` `:400–402`; `plan_costs` `:405–483`;
`build_plan_over_time` `:486–510`; `build_plan_recommendation_notice` `:1278–1325`; B9
constants `:1411–1412`; B12 normalization `:1445–1457`; B17 `:1552–1574` + tail inits
`:1575–1578`; `--only-warn` gate `:2758–2764`; B43+prep `:2766–2798`; chart-prep
`:2799–2830`; estimate `:2831–2832`; `site_plan_start` `:3177`; B46 `:3178–3198`; B47 core
`:3200–3337`; smells `:3339`; `site_pre_render` invoke `:3410`; template `:3415–3444`.

---

### Task 1: Move the six defs; discharge D-i6-2; fix the csv comma (D-i7-5)

**Files:**
- Create: `psh/plans.py`
- Modify: `psh/_legacy.py` (delete `:54–59`, `:395–510` five defs, `:1278–1325`; add the
  re-import block), `psh/traffic.py` (`:10–13` docstring bridge note, `:169–170` call-time
  import), `tests/unit/test_plan_recommendation_notice.py:29–32`,
  `tests/integration/__snapshots__/test_plan_recommendation_notice_render.ambr` (refresh)
- Test: existing suites only (`test_plan_math.py`, `test_plan_costs.py`,
  `test_plan_over_time.py`, `test_property_plan.py`, `test_plan_recommendation_notice.py`,
  render snapshot)

**Interfaces produced:** `psh.plans.{cost_table_columns, overage_blocks, contract_year_end,
plan_costs, build_plan_over_time, build_plan_recommendation_notice}`, re-imported by
`psh/_legacy.py` so `psh.<name>` still resolves. Signatures unchanged.

- [ ] **Step 1 (RED): update the csv pins to the D-i7-5 format**

In `tests/unit/test_plan_recommendation_notice.py`, change the expectation:

```python
def test_csv_is_variant_independent(psh):
    # D-i7-5 (campaign I7): the savings field is comma-free -- a thousands separator
    # inside a comma-separated row split the field and made the column count variable.
    assert _notice(psh, True)["csv"] == _notice(psh, False)["csv"] == (
        "s,its-recommends-plan,Performance Medium,Performance Small,1234.50"
    )
```

Run: `./run-tests --fast --llm tests/unit/test_plan_recommendation_notice.py`
Expected: FAIL — actual csv still `…,1,234.50`.

- [ ] **Step 2: create `psh/plans.py` with the six moved items**

Module docstring (adapt, do not copy `psh/traffic.py`'s): plans layer — plan catalog, cost
model, recommendation; moved at campaign I7 (CAMPAIGN.md §3.1, this folder's SPEC.md).
Imports for this task: `import datetime`, `import numpy as np`,
`import script_context as sc`. **Cut** each def/global from `psh/_legacy.py` (anchors
above) and paste verbatim, ordered: `cost_table_columns`, `overage_blocks`,
`contract_year_end`, `plan_costs`, `build_plan_over_time`,
`build_plan_recommendation_notice`. Named edits ONLY:

1. In `build_plan_recommendation_notice`, the csv line becomes (both body texts keep
   `{savings:,.2f}` — owner-facing copy is NOT touched):

```python
        "csv": f"{site_name},its-recommends-plan,{current_plan},{recommended_plan},{savings:.2f}",
```

2. Ratchet dispositions measured in Step 4 (SPEC §5 predicts `PLR0913`+`C901`/`PLR0912`/
   `PLR0915` noqa on `plan_costs` with pinned-signature/verbatim-move reasons; `SIM118` on
   `for month in visits_by_month.keys():` — rewrite to `.items()` ONLY if ruff demands and
   the I6 equivalence argument holds; record every disposition).

In `psh/_legacy.py`: delete the moved regions (collapse leftover blank runs to 2 — I5
precedent), and extend the re-import block after the `from psh.traffic import (…)` group
(`:237–246`):

```python
from psh.plans import (
    build_plan_over_time,
    build_plan_recommendation_notice,
    contract_year_end,
    cost_table_columns,
    overage_blocks,
    plan_costs,
)
```

- [ ] **Step 3: discharge D-i6-2 in `psh/traffic.py`**

Replace `:169–170`:

```python
    # Cycle: _legacy imports this module.  overage_blocks moves to psh.plans at I7.
    from psh._legacy import overage_blocks  # noqa: PLC0415
```

with a module-level `from psh.plans import overage_blocks` (alphabetical, next to the
existing `from psh.gateway import …` group), and delete the "Bridge note (SPEC D-i6-2)"
paragraph from the module docstring (`:10–13`), replacing it with one line: overage_blocks
is imported from psh.plans (bridge discharged at I7 per LEDGER I6).

- [ ] **Step 4: gates + suite green**

Run: `uvx ruff check --config ruff-broad.toml psh/plans.py psh/traffic.py` → All checks
passed (after recorded dispositions). Run `./run-tests --fast --llm` → the Step-1 test now
PASSES; render snapshot fails → refresh with
`./run-tests --update-goldens tests/integration/test_plan_recommendation_notice_render.py`
then `git diff` the `.ambr` and confirm ONLY `csv:` lines changed. Full fast tier green;
`git diff 3195c81 -- tests/e2e/__snapshots__/` empty.

- [ ] **Step 5: commit**

```bash
git add psh/plans.py psh/_legacy.py psh/traffic.py tests/unit/test_plan_recommendation_notice.py tests/integration/__snapshots__/test_plan_recommendation_notice_render.ambr
git commit -m "refactor(campaign-I7): move the plans layer into psh/plans.py; fix its-recommends-plan csv"
```

---

### Task 2: `PlanCatalog`/`PlanInfo` + `resolve_plan_name` (B9/B12/B17)

**Files:**
- Modify: `psh/plans.py`, `psh/_legacy.py`
- Test: Create `tests/unit/test_plan_catalog.py`, extend
  `tests/integration/test_plan_flow.py` (create the file; `recommend_plan` cases arrive in
  Task 3)

**Interfaces produced:** `psh.plans.PlanInfo` (frozen dataclass), `psh.plans.PlanCatalog`
(frozen dataclass; `from_config(pantheon_config, *, overage_block_size,
overage_block_cost) -> PlanCatalog`; fields `plan_info: dict`, `plan_names: list[str]`,
`plans: dict[str, PlanInfo]`, `overage_block_size: int`, `overage_block_cost: float`),
`psh.plans.resolve_plan_name(site: dict) -> str | None`. All re-imported by `_legacy.py`.
Task 3 consumes `catalog` in `recommend_plan`.

- [ ] **Step 1 (RED): write `tests/unit/test_plan_catalog.py`**

```python
"""PlanCatalog/PlanInfo (campaign I7, SPEC D-i7-2): the typed view over
[Pantheon].plan_info.  from_config performs B12's "-" -> None normalization MUTATING the
config sub-dict (main()'s plan_info alias and the I11/I12 regions read the same object)."""
import pytest

from psh.plans import PlanCatalog, PlanInfo

pytestmark = pytest.mark.unit


def _pantheon_config():
    return {
        "plan_info": {
            "Basic": {"cost": 300.0, "traffic_limit": 1000, "upgrade_at": 800,
                      "upgrade_to": "Performance Small", "downgrade_to": "-"},
            "Performance Small": {"cost": "1200.00", "traffic_limit": "5000",
                                  "upgrade_at": 4000,
                                  "upgrade_to": "Performance Medium",
                                  "downgrade_to": "Basic"},
        },
    }


def _catalog(cfg=None):
    cfg = cfg or _pantheon_config()
    return PlanCatalog.from_config(cfg, overage_block_size=1000, overage_block_cost=100.0)


def test_normalization_mutates_the_config_dict():
    cfg = _pantheon_config()
    _catalog(cfg)
    assert cfg["plan_info"]["Basic"]["downgrade_to"] is None       # "-" -> None, in place
    assert cfg["plan_info"]["Basic"]["upgrade_to"] == "Performance Small"


def test_catalog_exposes_raw_alias_and_ordered_names():
    cfg = _pantheon_config()
    catalog = _catalog(cfg)
    assert catalog.plan_info is cfg["plan_info"]                   # alias, not a copy
    assert catalog.plan_names == ["Basic", "Performance Small"]    # insertion order
    assert catalog.overage_block_size == 1000
    assert catalog.overage_block_cost == 100.0


def test_typed_plans_cast_string_config_values():
    # The umich portal substitution supplies cost/traffic_limit as strings.
    p = _catalog().plans["Performance Small"]
    assert p == PlanInfo(cost=1200.0, traffic_limit=5000, upgrade_at=4000,
                         upgrade_to="Performance Medium", downgrade_to="Basic")


def test_missing_plan_info_key_raises_keyerror():
    with pytest.raises(KeyError):
        PlanCatalog.from_config({}, overage_block_size=1, overage_block_cost=1.0)
```

Then write the `resolve_plan_name` half of `tests/integration/test_plan_flow.py`:

```python
"""Integration tier: the psh.plans flow functions extracted from main()'s per-site loop at
campaign I7 (SPEC D-i7-3/D-i7-7) -- resolve_plan_name (B17) and recommend_plan (B47).

Seams: psh.gateway.run_terminus (the gateway fixture) and a temp sqlite DB (temp_db).
Loop control stays in main(): resolve_plan_name returns None for the skip path."""
import json

import pytest

import script_context as sc
from helpers.dnsfake import recording_console
from psh.plans import resolve_plan_name

pytestmark = pytest.mark.integration


def test_non_elite_passthrough_no_terminus_call(psh, gateway, monkeypatch, reset_sc):
    def boom(*a, **k):
        raise AssertionError("terminus must not run for non-Elite plans")
    monkeypatch.setattr(gateway, "run_terminus", boom)
    assert resolve_plan_name({"name": "t1", "plan_name": "Basic"}) == "Basic"


def test_elite_sku_resolves_to_configured_name(psh, gateway, monkeypatch, reset_sc):
    sc.config = {"Pantheon": {"plan_sku_to_name": {"plan-elite-x": "Elite 1M"}}}
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps({"sku": "plan-elite-x"}), "", False))
    assert resolve_plan_name({"name": "t1", "plan_name": "Elite"}) == "Elite 1M"


def test_elite_transient_failure_returns_none(psh, gateway, monkeypatch, reset_sc):
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: ("", "boom [warning]", True))
    console = recording_console(monkeypatch, sc)
    assert resolve_plan_name({"name": "t1", "plan_name": "Elite"}) is None
    out = console.export_text()
    assert "could not fetch plan info for t1" in out
    assert "boom [warning]" in out  # Invariant 6: stderr escape()d, rich must not eat it


def test_elite_missing_sku_is_fatal(psh, gateway, monkeypatch, reset_sc):
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps({}), "", False))
    with pytest.raises(SystemExit, match="Bailing out."):
        resolve_plan_name({"name": "t1", "plan_name": "Elite"})


def test_elite_unknown_sku_is_fatal(psh, gateway, monkeypatch, reset_sc):
    sc.config = {"Pantheon": {"plan_sku_to_name": {}}}
    monkeypatch.setattr(gateway, "run_terminus",
                        lambda *a, **k: (json.dumps({"sku": "plan-weird"}), "", False))
    with pytest.raises(SystemExit, match="Bailing out."):
        resolve_plan_name({"name": "t1", "plan_name": "Elite"})
```

Run both files. Expected: FAIL/ERROR with `ImportError: cannot import name 'PlanCatalog'`
(and `resolve_plan_name`) — the right red.

- [ ] **Step 2: implement in `psh/plans.py`**

Add `import dataclasses`, `import sys`, `from rich.markup import escape`,
`from psh.gateway import terminus`.

```python
@dataclasses.dataclass(frozen=True)
class PlanInfo:
    """One [Pantheon].plan_info entry, typed (CAMPAIGN.md section 6, campaign I7)."""

    cost: float
    traffic_limit: int
    upgrade_at: int
    upgrade_to: str | None
    downgrade_to: str | None


@dataclasses.dataclass(frozen=True)
class PlanCatalog:
    """The typed view over [Pantheon].plan_info plus the two overage constants.

    from_config() performs the B12 "-" -> None normalization MUTATING the plan_info
    sub-dict in place: main()'s plan_info alias and the chart/annual-billing regions
    (I11/I12) read the same object, and a copy would fork two views of one config.
    plan_info/plan_names are the raw views main() aliases; plans is the typed view --
    its heavy consumers arrive as I11/I12 move their regions (SPEC D-i7-2).
    """

    plan_info: dict
    plan_names: list[str]
    plans: dict[str, PlanInfo]
    overage_block_size: int
    overage_block_cost: float

    @classmethod
    def from_config(cls, pantheon_config: dict, *, overage_block_size: int,
                    overage_block_cost: float) -> "PlanCatalog":
        plan_info = pantheon_config["plan_info"]
        for plan in plan_info:
            upgrade_to = plan_info[plan]["upgrade_to"]
            downgrade_to = plan_info[plan]["downgrade_to"]
            plan_info[plan]["upgrade_to"] = upgrade_to if upgrade_to != "-" else None
            plan_info[plan]["downgrade_to"] = (
                downgrade_to if downgrade_to != "-" else None
            )
        plans = {
            name: PlanInfo(
                cost=float(info["cost"]),
                traffic_limit=int(info["traffic_limit"]),
                upgrade_at=int(info["upgrade_at"]),
                upgrade_to=info["upgrade_to"],
                downgrade_to=info["downgrade_to"],
            )
            for name, info in plan_info.items()
        }
        return cls(plan_info=plan_info, plan_names=list(plan_info.keys()), plans=plans,
                   overage_block_size=overage_block_size,
                   overage_block_cost=overage_block_cost)
```

`resolve_plan_name`: body = `_legacy.py:1552–1574` verbatim inside the function, with the
named edits only — the guard becomes the early return, `site_name` → `site["name"]` in the
error print (I6's identical-value substitution, ledger-noted), and the transient-skip
comment moves in from `main()`:

```python
def resolve_plan_name(site: dict) -> str | None:
    """Resolve the billing plan name for a site (B17).

    Pantheon uses the same display name (but a different SKU) for each Elite plan, so an
    Elite site's real plan comes from `terminus plan:info` via [Pantheon].plan_sku_to_name.
    Returns None on a transient/undecodable Terminus failure (caller skips the site --
    loop control stays in main(), SPEC D-i7-1); unknown/missing SKU stays fatal.
    """
    if site["plan_name"] != "Elite":
        return site["plan_name"]
    site_plan_info, errors, fatal = terminus("plan:info", site["name"])
    if fatal or site_plan_info is None:
        # A transient/undecodable Terminus failure for one site skips that site rather
        # than aborting the whole run (consistent with the other per-site terminus calls).
        sc.console.print(
            f":exclamation: [bold red] ERROR: could not fetch plan info for {site['name']}: {escape(errors)}"
        )
        return None
    if "sku" not in site_plan_info:
        sc.console.print(
            f":exclamation: [bold red] ERROR: {site['name']} doesn't have a plan SKU"
        )
        sys.exit("Bailing out.")
    plan_sku = site_plan_info["sku"]
    if plan_sku not in sc.config["Pantheon"]["plan_sku_to_name"]:
        sc.console.print(
            f":exclamation: [bold red] ERROR: {site['name']} has an unknown plan SKU: {plan_sku}"
        )
        sys.exit("Bailing out.")
    return sc.config["Pantheon"]["plan_sku_to_name"][plan_sku]
```

- [ ] **Step 3: rewire `main()`**

B12 region `:1445–1457` becomes (B9 lines `:1411–1412` stay verbatim — SPEC D-i7-2):

```python
    catalog = PlanCatalog.from_config(
        sc.config["Pantheon"],
        overage_block_size=overage_block_size,
        overage_block_cost=overage_block_cost,
    )
    # Aliases for readability; the chart (I11) and annual-billing (I12) regions read the
    # raw normalized dict.
    plan_info = catalog.plan_info
    plan_names = catalog.plan_names
```

B17 region `:1552–1574` becomes (the tail inits `:1575–1578` stay verbatim):

```python
            plan_name = resolve_plan_name(site)
            if plan_name is None:
                continue
            site["plan_name"] = plan_name
```

Extend the `from psh.plans import (…)` block with `PlanCatalog`, `PlanInfo`,
`resolve_plan_name`.

- [ ] **Step 4: green + gates**

`./run-tests --fast --llm` → Step-1 tests pass, whole tier green, goldens diff vs
`3195c81` empty. `uvx ruff check --config ruff-broad.toml psh/plans.py` clean (record
dispositions). Pyright via `./run-tests` → 0 errors.

- [ ] **Step 5: commit**

```bash
git add psh/plans.py psh/_legacy.py tests/unit/test_plan_catalog.py tests/integration/test_plan_flow.py
git commit -m "refactor(campaign-I7): PlanCatalog/PlanInfo and resolve_plan_name (B9/B12/B17)"
```

---

### Task 3: `recommend_plan` + D7 reorder + contract keys (B47)

**Files:**
- Modify: `psh/plans.py`, `psh/_legacy.py`, `psh/modules.py` (CONTRACT),
  `tests/conftest.py` (`seed_traffic` gains `visits_scale`),
  `tests/unit/test_contract_registry.py`
- Test: extend `tests/integration/test_plan_flow.py`; create
  `tests/e2e/test_only_warn_e2e.py`

**Interfaces produced:** `psh.plans.PlanRecommendation` (frozen dataclass, fields below),
`psh.plans.recommend_plan(db_session, site, catalog, visits_by_month, site_plan_start,
estimate, start_date, end_date, portal_site_id, site_context) -> PlanRecommendation`,
`psh.plans.stuff_plans_contract(site_context, current_plan, recommended_plan, costs,
savings)`; `CONTRACT["site_pre_render"] == ("current_plan", "recommended_plan",
"plan_costs", "savings")`. All re-imported by `_legacy.py`.

- [ ] **Step 1 (RED): flow tests — append to `tests/integration/test_plan_flow.py`**

Add imports: `import datetime`, `from psh.plans import PlanCatalog, recommend_plan`.
Shared fixture code (module level):

```python
PLAN_CONFIG = {
    "plan_info": {
        "Basic": {"cost": 300.0, "traffic_limit": 1000, "upgrade_at": 800,
                  "upgrade_to": "Performance Small", "downgrade_to": "-"},
        "Performance Small": {"cost": 1200.0, "traffic_limit": 5000, "upgrade_at": 4000,
                              "upgrade_to": "Performance Medium", "downgrade_to": "Basic"},
        "Performance Medium": {"cost": 3000.0, "traffic_limit": 10000, "upgrade_at": 8000,
                               "upgrade_to": "-", "downgrade_to": "Performance Small"},
    },
}
SIX_MONTHS = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"]
START = datetime.date(2025, 3, 1)
END = datetime.date(2026, 3, 31)
PLAN_START = datetime.date(2025, 10, 1)


def _recommend(temp_db, reset_sc, *, current_plan, visits, months=SIX_MONTHS):
    """Run recommend_plan against an empty overage-protection table.

    Cost model with this catalog, 6 x visits=3000 (overage 2000 on Basic -> 2 blocks x
    $100): cost_same/best Basic 2700, PS 1200, PM 3000.  With visits=100: Basic 300,
    PS 1200, PM 3000 (no overage anywhere).
    """
    catalog = PlanCatalog.from_config(
        {"plan_info": {k: dict(v) for k, v in PLAN_CONFIG["plan_info"].items()}},
        overage_block_size=1000, overage_block_cost=100.0)
    site = {"id": "s-id-1", "name": "t1", "plan_name": current_plan}
    site_context = reset_sc.SiteContext({"name": "t1"})
    rec = recommend_plan(
        temp_db.session(), site, catalog, dict.fromkeys(months, visits), PLAN_START,
        -1, START, END, 0, site_context,
    )
    return rec, site_context


def test_too_few_months_returns_defaults(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Basic", visits=3000,
                          months=SIX_MONTHS[:3])
    assert rec.months_until_recommendations == 2
    assert rec.median_visitors == 0
    assert rec.cost_same == {} and rec.cost_table_rows == {}
    assert rec.recommended_plan == "Basic" and rec.current_plan == "Basic"
    assert rec.current_plan_index == 0 and rec.recommended_plan_index == 0
    assert rec.savings == 0.0 and rec.savings_entry is None
    assert ctx["notices"] == []


def test_upgrade_adds_notice_and_savings_entry(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Basic", visits=3000)
    assert rec.recommended_plan == "Performance Small"
    assert (rec.current_plan_index, rec.recommended_plan_index) == (0, 1)
    assert rec.savings == 1500.0            # |cost_same[Basic] 2700 - best[PS] 1200|
    assert rec.savings_entry == {"site": "t1", "savings": 1500.0,
                                 "current_plan": "Basic",
                                 "recommended_plan": "Performance Small"}
    [notice] = ctx["notices"]
    assert notice["csv"] == "t1,its-recommends-plan,Basic,Performance Small,1500.00"


def test_non_basic_downgrade_gets_a_savings_entry(psh, temp_db, reset_sc):
    # RED against the verbatim extraction (D-i7-4): non-Basic downgrades used to
    # vanish from the operator's savings summary.  Still no owner notice (SPEC).
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Medium",
                          visits=3000)
    assert rec.recommended_plan == "Performance Small"
    assert rec.savings == 1800.0            # |cost_same[PM] 3000 - best[PS] 1200|
    assert rec.savings_entry == {"site": "t1", "savings": 1800.0,
                                 "current_plan": "Performance Medium",
                                 "recommended_plan": "Performance Small"}
    assert ctx["notices"] == []


def test_basic_downgrade_floors_at_performance_small(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Small", visits=100)
    assert rec.recommended_plan == "Performance Small"   # guardrail held at the floor
    assert rec.savings == 0.0
    assert rec.savings_entry == {"site": "t1", "savings": 0.0,
                                 "current_plan": "Performance Small",
                                 "recommended_plan": "Performance Small"}
    assert ctx["notices"] == []


def test_basic_downgrade_finds_better_intermediate_plan(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Medium",
                          visits=100)
    assert rec.recommended_plan == "Performance Small"   # alt between PM and Basic
    assert rec.savings == 1800.0            # |cost_same[PM] 3000 - best[PS] 1200|
    assert rec.savings_entry is not None and ctx["notices"] == []


def test_no_change_recommended(psh, temp_db, reset_sc):
    rec, ctx = _recommend(temp_db, reset_sc, current_plan="Performance Small",
                          visits=3000)
    assert rec.recommended_plan == "Performance Small"
    assert rec.savings == 0.0 and rec.savings_entry is None and ctx["notices"] == []
    assert "Recommended Plan" in rec.cost_table_rows["Performance Small"]["notes"]
    assert "Current Plan" in rec.cost_table_rows["Performance Small"]["notes"]
```

(If `temp_db.session()` differs from `test_traffic_flow.py`'s usage, follow that file —
it is the sibling pattern and the fixture's contract wins over this plan's sketch.)

- [ ] **Step 2 (RED): contract-registry pins**

In `tests/unit/test_contract_registry.py`: remove `"site_pre_render"` from
`test_contract_empty_phases`' tuple loop, and add:

```python
def test_site_pre_render_contract_keys(psh):
    import psh.modules
    assert psh.modules.CONTRACT["site_pre_render"] == (
        "current_plan", "recommended_plan", "plan_costs", "savings")


def test_plans_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    import psh.plans
    ctx = _fresh_ctx(reset_sc)
    psh.plans.stuff_plans_contract(ctx, "Basic", "Performance Small",
                                   {"same": {"Basic": 1.0}, "median": {}, "best": {}},
                                   12.5)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_pre_render"])
    assert ctx["current_plan"] == "Basic"
    assert ctx["recommended_plan"] == "Performance Small"
    assert ctx["plan_costs"]["same"] == {"Basic": 1.0}
    assert ctx["savings"] == 12.5
```

- [ ] **Step 3 (RED): the D7 e2e — `tests/e2e/test_only_warn_e2e.py`**

First add the backward-compatible seed knob in `tests/conftest.py::seed_traffic`: new
keyword `visits_scale=1`, and `visits = (1000 + day.day * 10) * visits_scale` (default
unchanged — existing callers unaffected).

```python
"""Offline e2e for D7 (campaign I7): --only-warn computes the plan recommendation before
dumping warnings, so warning-only runs surface its-recommends-plan rows.

At the default seed volume (median 35,960) the cost model lands in the Basic-downgrade
guardrail (no notice -- see test_recommendation_e2e.py), so this seeds 6x: median 215,760,
where Performance Large's cost (best 6,920) beats current Performance Small (cost_same
4,165 is beaten as best 8,005) -> upgrade notice, savings |4165 - 6920| = 2755.00.
Derivation in the I7 PLAN.md (Task 3); verify by hand against minimal.toml before
adjusting any pinned value here.
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e

_SIX_MONTHS = [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)]


def _only_warn(work):
    return run_program(
        [E2E_SITE, "--date", E2E_DATE, "--only-warn", "--smtp-username",
         E2E_SMTP_USERNAME, "--config", str(MINIMAL_CONFIG)],
        cwd=work,
    )


def test_only_warn_includes_plan_recommendation(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    for year, month in _SIX_MONTHS:
        seed_traffic(work / "test.db", year=year, month=month, visits_scale=6)

    proc = _only_warn(work)

    assert proc.returncode == 0, proc.stderr
    row = next(l for l in proc.stdout.splitlines()
               if f"{E2E_SITE},its-recommends-plan," in l)
    # D-i7-5: fixed 5-column row, comma-free savings (2,755.00 would split the field).
    assert row.strip() == (
        f"{E2E_SITE},its-recommends-plan,Performance Small,Performance Large,2755.00"
    )
    # --only-warn still renders and sends nothing.
    assert not (work / "build" / f"{E2E_SITE}.html").exists()
    assert not (work / "build" / f"{E2E_SITE}.eml").exists()


def test_only_warn_without_enough_data_has_no_recommendation(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "test.db")  # one month -> months_until_recommendations > 0

    proc = _only_warn(work)

    assert proc.returncode == 0, proc.stderr
    assert "its-recommends-plan" not in proc.stdout
    assert not (work / "build" / f"{E2E_SITE}.html").exists()
```

Run all Step-1/2/3 tests. Expected: FAIL — flow tests on `ImportError: recommend_plan`,
registry pins on the old empty tuple, e2e on the missing csv row (genuine behavioral red:
today the gate precedes the recommendation).

- [ ] **Step 4: implement — `psh/plans.py`**

Add `import copy` and `from psh.configuration import umich_enabled` and
`from psh.db import db_retry, load_overage_protection_window`.

```python
@dataclasses.dataclass(frozen=True)
class PlanRecommendation:
    """Everything main() and the site_pre_render contract need from the cost model."""

    months_until_recommendations: int
    median_visitors: float
    cost_same: dict
    costs_median: dict
    costs_best: dict
    cost_table_rows: dict
    current_plan: str
    recommended_plan: str
    current_plan_index: int
    recommended_plan_index: int
    savings: float
    estimate_start_date: datetime.date
    estimate_end_date: datetime.date
    savings_entry: dict | None
```

`recommend_plan(db_session, site, catalog, visits_by_month, site_plan_start, estimate,
start_date, end_date, portal_site_id, site_context)`: body = `_legacy.py:3200–3337`
verbatim (including the `:3175` op-load comment and the `:3217–3220` one-ranged-query
comment, its "above/below" wording corrected to name `build_traffic_table_rows` as
running later), with ONLY these named edits (paste the region diff in the task report):

1. Prologue locals so the verbatim interior resolves:
   `plan_info = catalog.plan_info`, `plan_names = catalog.plan_names`,
   `overage_block_size = catalog.overage_block_size`,
   `overage_block_cost = catalog.overage_block_cost`,
   `site_current_plan = site["plan_name"]`,
   `end_date_yyyy_mm = end_date.strftime("%Y-%m")`,
   plus the init defaults that lived at `:3202–3214` and B17's tail: `savings = 0.0`,
   `savings_entry = None`, `site_recommended_plan = site["plan_name"]`,
   `site_current_plan_index = 0`, `site_recommended_plan_index = 0`.
2. The two `site_savings.append({...})` sites become `savings_entry = {...}` with the
   D-i7-4 restructure — the downgrade branch's assignment moves OUT of the
   `if site_recommended_plan == "Basic":` block so every surviving downgrade
   recommendation produces an entry (the guardrail interior above it stays verbatim,
   including its `# TODO: if Basic still looks best…` comment):

```python
                if site_current_plan_index > site_recommended_plan_index:
                    if site_recommended_plan == "Basic":
                        # …guardrail interior verbatim, WITHOUT the trailing append…
                    # D-i7-4 (campaign I7): every surviving downgrade recommendation
                    # reaches the operator's savings summary -- non-Basic downgrades
                    # used to vanish from it.  Still no owner notice (campaign non-goal;
                    # README TODO).
                    savings_entry = {
                        "site": site["name"],
                        "savings": savings,
                        "current_plan": site["plan_name"],
                        "recommended_plan": site_recommended_plan,
                    }
                else:
                    site_context.add_notice(
                        build_plan_recommendation_notice(
                            site["name"], site["plan_name"], site_recommended_plan,
                            savings, portal_site_id, umich_enabled(),
                        )
                    )
                    savings_entry = {
                        "site": site["name"],
                        "savings": savings,
                        "current_plan": site["plan_name"],
                        "recommended_plan": site_recommended_plan,
                    }
```

3. Ends with `return PlanRecommendation(months_until_recommendations=…, …,
   savings_entry=savings_entry)` mapping each field from the same-named local
   (`current_plan=site_current_plan`, `recommended_plan=site_recommended_plan`, …).

Then the stuffer:

```python
def stuff_plans_contract(site_context, current_plan: str, recommended_plan: str,
                         costs: dict, savings: float) -> None:
    """Publish the site_pre_render contract keys (psh.modules.CONTRACT is authoritative).

    costs is {"same": {plan: cost}, "median": {...}, "best": {...}} -- {} when the site
    has too few in-window months for a recommendation.  recommended_plan equals
    current_plan when no change is recommended."""
    site_context["current_plan"] = current_plan
    site_context["recommended_plan"] = recommended_plan
    site_context["plan_costs"] = costs
    site_context["savings"] = savings
```

- [ ] **Step 5: implement — `psh/modules.py` CONTRACT + `psh/_legacy.py` rewire**

`CONTRACT["site_pre_render"]` → `("current_plan", "recommended_plan", "plan_costs",
"savings")`; update the registry's header comment (it still says site_pre_render "adds
nothing").

`_legacy.py` edits (anchors will have drifted — locate by content):

1. Delete the `:2758–2760` D7 TODO comment; move the gate block (`if sc.options.only_warn:`
   … `continue`) below the new rec-call (next edit). The `# TODO: Warn if no Autopilot`
   comment stays where it is.
2. Move the estimate pair (`:2831–2832`, comment + `estimate = estimate_month_visits(…)`)
   to directly after the `visits = list(visits_by_month.values())` line (`:2798`).
3. Replace `:3175–3177` (op-load comment + `site_plan_start` line) and `:3200–3337` (B47
   core) with — positioned after the estimate hoist and BEFORE the moved gate:

```python
            # Load the overage protection data and compare current-plan cost to the other
            # plans (psh.plans.recommend_plan).  Runs before the --only-warn gate so
            # warning-only runs include the plan recommendation (D7, campaign I7).
            site_plan_start = plan_over_time[0]["start"].replace(day=1)
            rec = recommend_plan(
                db_session,
                site,
                catalog,
                visits_by_month,
                site_plan_start,
                estimate,
                start_date,
                end_date,
                portal_site_id,
                site_context,
            )
            site_recommended_plan = rec.recommended_plan
            site_current_plan_index = rec.current_plan_index
            site_recommended_plan_index = rec.recommended_plan_index
            median_visitors = rec.median_visitors
            cost_table_rows = rec.cost_table_rows
            months_until_recommendations = rec.months_until_recommendations
            estimate_start_date = rec.estimate_start_date
            estimate_end_date = rec.estimate_end_date
            if rec.savings_entry is not None:
                site_savings.append(rec.savings_entry)

            if sc.options.only_warn:
                for n in site_context["notices"]:
                    all_warnings.append(n["csv"])
                continue
```

   B46 (`db_retry(build_traffic_table_rows…)` + its `sc.debug`) stays in place after the
   chart build; it reads the `site_plan_start` local set above.
4. Insert before `sc.invoke_hooks("site_pre_render", site_context)`:

```python
            stuff_plans_contract(
                site_context,
                site_current_plan,
                site_recommended_plan,
                {"same": rec.cost_same, "median": rec.costs_median,
                 "best": rec.costs_best}
                if rec.cost_same
                else {},
                rec.savings,
            )
```

5. Extend the `from psh.plans import (…)` block with `PlanRecommendation`,
   `recommend_plan`, `stuff_plans_contract`; grep for orphaned `copy` usage and drop
   `import copy` only if nothing else uses it.

- [ ] **Step 6: green sequence**

Run the flow tests: expect all green EXCEPT `test_non_basic_downgrade_gets_a_savings_entry`
if the extraction was done verbatim-first — the D-i7-4 restructure (Step 4 edit 2) is what
turns it green; if it never showed red, re-check the restructure landed *after* a verbatim
extraction (record the sequence in the report). Then `./run-tests --fast --llm`: everything
green including the e2e (its exact `2755.00` row — if the value differs, STOP and re-derive
by hand against `minimal.toml`; do not adjust the pin to match observed output without the
derivation). Goldens diff vs `3195c81` empty. Ruff-broad + pyright clean (record
dispositions; SPEC §5 predicts `PLR0913` on `recommend_plan`).

- [ ] **Step 7: commit**

```bash
git add psh/plans.py psh/modules.py psh/_legacy.py tests/conftest.py tests/unit/test_contract_registry.py tests/integration/test_plan_flow.py tests/e2e/test_only_warn_e2e.py
git commit -m "refactor(campaign-I7): recommend_plan + D7 --only-warn recommendation + site_pre_render contract keys"
```

---

### Task 4: Docs, amendment, README TODO

**Files:**
- Modify: `CLAUDE.md`, `README.md`,
  `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (§8 row),
  `/home/node/.claude/projects/-workspace/memory/` (update `modularization-campaign.md`
  or add a plans-layer memory + MEMORY.md line)

- [ ] **Step 1: CLAUDE.md** — (a) § Single-module core: add the `psh/plans.py` sentence
  block (move set + `PlanCatalog`/`PlanInfo` + `resolve_plan_name`/`recommend_plan`/
  `stuff_plans_contract`, import-back pattern, D-i6-2 bridge note REPLACED — delete the
  "temporary until I7" sentence in the `psh/traffic.py` block and state the module-level
  import); (b) contract table: `site_pre_render` row now lists the four keys + shapes
  (SPEC D-i7-8 wording); (c) § Key flags: `--only-warn` now "checks sites for warnings —
  including the plan recommendation — without generating reports or sending mail";
  (d) § Testing pure-helper seam: `overage_blocks`/`contract_year_end`/`plan_costs`/
  `build_plan_over_time` now live in `psh/plans.py` (still importable as `psh.<name>`);
  (e) § Per-site pipeline: note the recommendation runs before the `--only-warn` gate.
- [ ] **Step 2: README.md TODO** — add: owner-facing downgrade-recommendation notice
  (post-campaign; I1 deleted the dead `extra_message` that was presumably meant for it —
  see LEDGER I7/D-i7-4).
- [ ] **Step 3: CAMPAIGN.md §8 amendment** — the "Notice csv *values*" row gains "and I7
  (`its-recommends-plan` savings-field format, D-i7-5)"; ledger entry records the
  amendment (Task 5).
- [ ] **Step 4: memory** — update `modularization-campaign.md` progress note (through I7)
  and any memory naming the traffic-layer bridge.
- [ ] **Step 5: commit**

```bash
git add CLAUDE.md README.md development/2026-07-17-modularization-campaign/CAMPAIGN.md
git commit -m "docs(campaign-I7): document the plans layer, D7, and the section-8 amendment"
```

(Memory files live outside the repo — write them, don't `git add` them.)

---

### Task 5: Increment close (controller, not a subagent dispatch)

- [ ] `/code-review` over the whole increment range (`3195c81..HEAD`); triage per
  `superpowers:receiving-code-review`; fix-subagents are `psh-implementer`.
- [ ] Full `./run-tests` (live tier if Terminus credentials present; else `--fast` +
  ledger note). Paste results into SPEC §9 (Acceptance).
- [ ] `git diff 3195c81 -- tests/e2e/__snapshots__/` → empty; paste into SPEC §9.
- [ ] LEDGER.md I7 entry (template §12): moved set, deviations (D-i7-1 ledger notes,
  D-i7-4 decision + README TODO, D-i7-5 amendment, `site_name`→`site["name"]`
  substitutions), contract/sc additions (four keys; re-imported names), discovered tasks,
  open questions for I8.
- [ ] `/archive-session`, then the closing docs commit
  (`docs(campaign-I7): close the plans increment` — ledger + SPEC acceptance + dev
  folder).

## Self-Review notes (run against SPEC)

- Every SPEC §1 item maps: 1→Task 1, 2/3(B17)→Task 2, 3(B47)/4/5→Task 3, 6→Task 1,
  7→Tasks 1–3, 8→Tasks 1–3, 9→Task 4/5.
- Type consistency: `PlanCatalog.from_config(pantheon_config, *, overage_block_size,
  overage_block_cost)` used identically in Tasks 2 and 3;
  `recommend_plan(db_session, site, catalog, visits_by_month, site_plan_start, estimate,
  start_date, end_date, portal_site_id, site_context)` matches SPEC D-i7-7;
  `stuff_plans_contract(site_context, current_plan, recommended_plan, costs, savings)`
  matches the registry pin test.
- The e2e arithmetic (2755.00) is derived in this plan's history and summarized in the
  test docstring; the flow-test numbers (1500/1800/0) are derived in the `_recommend`
  docstring. Any mismatch during GREEN is a STOP-and-rederive, not a pin adjustment.
