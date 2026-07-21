# I6 — `psh/traffic.py` (traffic layer move + flow extraction) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch
> every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via
> `mattpocock-skills:tdd` (NOT superpowers TDD). The authoritative design is `SPEC.md` in this
> folder — read it in full; this plan is the step sequence, the SPEC carries rationale,
> decisions (D-i6-1…5), and invariants.

**Goal:** Move `traffic_table_columns`, `get_old_metrics`, `estimate_month_visits`, and
`build_traffic_table_rows` into a new gated `psh/traffic.py`, and extract the B22–B24+B26
loop-body flow and the B43 aggregation into four new functions there — loop control stays
in `main()`; four e2e goldens byte-identical throughout.

**Architecture:** Import-back move (I2/I3/I5 precedent): `psh/_legacy.py` re-imports every
moved/new name so `main()`'s call sites and the tests' `psh.<name>` references resolve
unchanged. Flow functions signal via return values (`update_site_traffic -> bool`,
`load_site_traffic -> list[TrafficRow]`); every `continue` stays in `main()` (SPEC D-i6-1;
CAMPAIGN §3.3 keeps B25 there verbatim). `overage_blocks` bridges via a call-time import
until I7 (SPEC D-i6-2). The `psh.db` re-imports in `_legacy.py` are NOT removed (test
façade, 22 references — SPEC D-i6-3).

**Tech Stack:** Python 3.12+, SQLAlchemy 2.x, ruff (`ruff-broad.toml` `select=ALL`),
pyright (standard), pytest.

## Global Constraints

- **Four e2e goldens byte-identical** (Invariant 1). `--update-goldens` FORBIDDEN. Verify
  `git diff 5de11a4 -- tests/e2e/__snapshots__/` is empty at each task end.
- **`psh/traffic.py` passes the full gate from birth**: `uvx ruff check --config
  ruff-broad.toml psh/traffic.py` → "All checks passed!"; pyright standard → 0 errors.
  (Both measured clean 2026-07-20 on the exact intended content — reference assembly at
  `/tmp/claude-501/-workspace/ebac038f-1d88-475c-8e72-f40844ecb1c3/scratchpad/traffic-scratch-measured.py`,
  cross-check only; BUILD the file from `psh/_legacy.py` per Task 2, never copy the scratch.)
- **Run pyright via `./run-tests`, NOT `uv run pyright`** (uv.lock churn; `git checkout --
  uv.lock` if it shows modified).
- **Moved bodies are verbatim** except the SPEC §3/§5 named edits (repeated inline below).
  The Task 2 report MUST paste the region diff proving the only differences are those edits.
- **No `sc` name removed** (Invariant 9); nothing new joins the documented façade.
- **Invariant 8 pre-check:** grep the moved regions for column-0 `f"""` — there are none in
  scope; confirm before de-indenting loop-body lines.
- **No import removals in `_legacy.py`** (SPEC §1 — the move orphans nothing; the `psh.db`
  re-imports stay).
- **Safety interlock**: no `--all`/`--for-real`/live `--create-tables` in tests.
- Clear stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 note).
- Baseline commit (I6 start) = `5de11a4`. `--fast` baseline = **780 passed / 1 skipped /
  2 deselected**; this increment adds **8** tests → expect **788 passed / 1 skipped**.
- Every task report cites Spine directives by number with a verbatim quote (agent config).
- The inner loop is `./run-tests --fast --llm`; run it at every task end.

---

### Task 1: Tests RED — the two new seam suites

The `mattpocock-skills:tdd` red step. **No commit** (red tests cannot be committed green);
the files land in Task 2's atomic commit. Deliverable: both files written exactly as below,
shown failing for the right reason (`ModuleNotFoundError: No module named 'psh.traffic'`).

**Files:**
- Create: `tests/unit/test_traffic_aggregation.py`
- Create: `tests/integration/test_traffic_flow.py`

**Interfaces (consumed from Task 2, defined by SPEC D-i6-1/D-i6-4):**
- `psh.traffic.update_site_traffic(db_session, site: dict, live_site: str, start_date, end_date) -> bool`
- `psh.traffic.import_older_site_metrics(db_session, site: dict, live_site: str, end_date) -> None`
- `psh.traffic.load_site_traffic(db_session, site: dict, start_date, end_date) -> list[TrafficRow]`
- `psh.traffic.aggregate_visits_by_month(rows, start_date, end_date) -> tuple[dict[str, int], dict[datetime.date, str]]`

- [ ] **Step 1: Baseline green.** Run `./run-tests --fast --llm`; record the LLM_SUMMARY line
  (expect `passed=780 … skipped=1`).

- [ ] **Step 2: Write `tests/unit/test_traffic_aggregation.py`:**

```python
"""Unit tier: psh.traffic.aggregate_visits_by_month -- the B43 aggregation extracted at
campaign I6 (SPEC D-i6-4).

Pure function (CAMPAIGN.md section 3.4): no sc, no I/O.  Imported from psh.traffic
directly -- the new gated module, not the psh._legacy fixture (whose re-import also
resolves, but the module is the seam under test).
"""
import datetime

import pytest

import psh.traffic
from psh.db import TrafficRow

pytestmark = pytest.mark.unit


def _row(day: str, visits: int = 0, plan: str = "Basic") -> TrafficRow:
    return TrafficRow(
        site_id="test-site-id",
        traffic_date=datetime.date.fromisoformat(day),
        site_plan=plan,
        visits=visits,
        pages_served=0,
        cache_hits=0,
    )


def test_seeds_every_window_month_to_zero_with_no_rows():
    visits, plans = psh.traffic.aggregate_visits_by_month(
        [], datetime.date(2026, 1, 15), datetime.date(2026, 3, 31)
    )
    assert visits == {"2026-01": 0, "2026-02": 0, "2026-03": 0}
    assert plans == {}


def test_sums_visits_within_each_month():
    rows = [
        _row("2026-02-27", visits=7),
        _row("2026-03-01", visits=10),
        _row("2026-03-02", visits=5),
    ]
    visits, _plans = psh.traffic.aggregate_visits_by_month(
        rows, datetime.date(2026, 2, 1), datetime.date(2026, 3, 31)
    )
    assert visits == {"2026-02": 7, "2026-03": 15}


def test_plan_on_day_maps_each_date_last_row_wins():
    rows = [
        _row("2026-03-01", plan="Basic"),
        _row("2026-03-02", plan="Performance Small"),
        _row("2026-03-02", plan="Performance Medium"),
    ]
    _visits, plans = psh.traffic.aggregate_visits_by_month(
        rows, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
    )
    assert plans == {
        datetime.date(2026, 3, 1): "Basic",
        datetime.date(2026, 3, 2): "Performance Medium",
    }


def test_window_spanning_a_year_boundary_seeds_the_right_months():
    visits, _plans = psh.traffic.aggregate_visits_by_month(
        [], datetime.date(2025, 11, 10), datetime.date(2026, 2, 28)
    )
    assert list(visits) == ["2025-11", "2025-12", "2026-01", "2026-02"]
```

- [ ] **Step 3: Write `tests/integration/test_traffic_flow.py`:**

```python
"""Integration tier: the psh.traffic flow functions extracted from main()'s per-site loop
at campaign I6 (SPEC D-i6-1) -- update_site_traffic (B22+B23), import_older_site_metrics
(B24), load_site_traffic (B26).

Seams: psh.gateway.run_terminus (the gateway fixture -- CLAUDE.md section "Two mock
seams") and a temp sqlite DB (temp_db).  Loop control stays in main(): these functions
signal via return value; they never continue/raise for the skip paths.
"""
import datetime
import json

import pytest

import psh.traffic
import script_context as sc
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

SITE = {"id": "test-site-id", "name": "its-wws-test1", "plan_name": "Basic"}
START = datetime.date(2025, 8, 1)
END = datetime.date(2026, 3, 31)


def _metrics_json(*entries):
    """A terminus env:metrics payload; entries are ("%Y-%m-%dT%H:%M:%S", visits) pairs."""
    return json.dumps(
        {
            "timeseries": {
                dt: {"datetime": dt, "visits": visits, "pages_served": 0, "cache_hits": 0}
                for dt, visits in entries
            }
        }
    )


def _period_of(command):
    return next(a for a in command if a.startswith("--period="))


def test_update_site_traffic_false_and_no_rows_on_fatal_metrics(
    psh, gateway, temp_db, monkeypatch
):
    monkeypatch.setattr(
        gateway, "run_terminus", lambda *a, **k: ("", "boom [warning]", True)
    )
    console = recording_console(monkeypatch, sc)
    session = temp_db.session()
    ok = psh.traffic.update_site_traffic(session, SITE, "test-site-id.live", START, END)
    assert ok is False
    assert session.query(temp_db.PantheonTraffic).count() == 0
    out = console.export_text()
    assert "could not fetch metrics for its-wws-test1" in out
    # Invariant 6: the untrusted stderr is escape()d, so rich must not eat "[warning]".
    assert "boom [warning]" in out


def test_update_site_traffic_merges_rows_and_skips_the_end_date(
    psh, gateway, temp_db, monkeypatch
):
    payload = _metrics_json(("2026-03-01T00:00:00", 10), ("2026-03-31T00:00:00", 99))
    monkeypatch.setattr(gateway, "run_terminus", lambda *a, **k: (payload, "", False))
    session = temp_db.session()
    ok = psh.traffic.update_site_traffic(session, SITE, "test-site-id.live", START, END)
    assert ok is True
    rows = session.query(temp_db.PantheonTraffic).all()
    # The end_date entry is today's partial data and must be skipped (update_traffic_rows'
    # existing rule, exercised through the new wrapper).
    assert [(r.traffic_date, r.visits) for r in rows] == [(datetime.date(2026, 3, 1), 10)]


def test_import_older_site_metrics_fetches_week_then_month_and_inserts(
    psh, gateway, temp_db, monkeypatch
):
    sc.config["Database"] = {"type": "sqlite"}  # insert_traffic_rows' backend switch
    calls = []

    def fake_run(command, input_data=None):
        calls.append(command)
        if _period_of(command) == "--period=week":
            # One week starting Mon 2026-02-02, 70 visits -> 7 daily rows of 10.
            return (_metrics_json(("2026-02-02T00:00:00", 70)), "", False)
        # One month, September 2025 (30 days), 30 visits -> 30 daily rows of 1.
        return (_metrics_json(("2025-09-01T00:00:00", 30)), "", False)

    monkeypatch.setattr(gateway, "run_terminus", fake_run)
    session = temp_db.session()
    psh.traffic.import_older_site_metrics(session, SITE, "test-site-id.live", END)
    # Fetch order is part of the moved contract: week, then month (B24 comment).
    assert [_period_of(c) for c in calls] == ["--period=week", "--period=month"]
    assert session.query(temp_db.PantheonTraffic).count() == 7 + 30
    feb2 = (
        session.query(temp_db.PantheonTraffic)
        .filter_by(traffic_date=datetime.date(2026, 2, 2))
        .one()
    )
    assert feb2.visits == 10


def test_load_site_traffic_returns_the_window_rows(psh, temp_db):
    session = temp_db.session()
    session.add(
        temp_db.PantheonTraffic(
            site_id="test-site-id",
            traffic_date=datetime.date(2026, 3, 1),
            site_plan="Basic",
            visits=10,
            pages_served=0,
            cache_hits=0,
        )
    )
    session.commit()
    rows = psh.traffic.load_site_traffic(session, SITE, START, END)
    assert rows == [
        psh.TrafficRow("test-site-id", datetime.date(2026, 3, 1), "Basic", 10, 0, 0)
    ]
```

- [ ] **Step 4: Run both files; verify RED for the right reason.**

Run: `./run-tests --fast --llm tests/unit/test_traffic_aggregation.py tests/integration/test_traffic_flow.py`
Expected: collection ERROR on both files with `ModuleNotFoundError: No module named
'psh.traffic'` — not an assertion failure, not a fixture error. (The lint/type gates run
first and must still pass: the new files must be ruff-clean.)

- [ ] **Step 5: Hand off.** No commit. Report the RED output verbatim.

---

### Task 2: The move + extraction — `psh/traffic.py`, `_legacy.py` rewrite, GREEN

One atomic commit: the new module, the `_legacy.py` deletions/re-imports/region rewrites,
and Task 1's test files — partial application cannot be green.

**Files:**
- Create: `psh/traffic.py`
- Modify: `psh/_legacy.py` (delete 53–68, 265–336, 485–507, 510–633; add the re-import;
  rewrite the 1904–1957 loop region and the 3036–3048 aggregation region — line numbers
  are pre-edit; work bottom-up or by content anchor)
- Include: Task 1's two test files (already on disk, uncommitted)

**Interfaces:**
- Produces: `psh.traffic.{traffic_table_columns, get_old_metrics, estimate_month_visits,
  build_traffic_table_rows, update_site_traffic, import_older_site_metrics,
  load_site_traffic, aggregate_visits_by_month}` — all re-imported by `psh._legacy`, so
  `psh.<name>` keeps resolving for the move set.

- [ ] **Step 1: Create `psh/traffic.py`.** Module docstring first:

```python
"""Traffic layer: metrics gather, DB update/load flow, and per-month aggregation.

Moved out of the main script at campaign I6 (CAMPAIGN.md section 3.1, development/
2026-07-20-mod-I6-traffic/SPEC.md).  Holds the traffic-report table columns, the
older-metrics backfill, the extracted per-site gather/load flow (B22-B24, B26 -- loop
control stays in main(), these functions signal via return values, SPEC D-i6-1), and the
B43 visits-by-month aggregation.  build_traffic_table_rows remains one of db_retry()'s
five named idempotent units (CLAUDE.md section Database).

Bridge note (SPEC D-i6-2): build_traffic_table_rows calls overage_blocks, which still
lives in psh._legacy (it moves to psh.plans at I7) -- imported at call time because
_legacy imports this module for the re-exports (cycle).  I7 replaces that import with
`from psh.plans import overage_blocks`.
"""
```

Then imports, exactly:

```python
import calendar
import datetime

from rich.markup import escape

import script_context as sc
from psh.db import (
    PantheonOverageProtection,
    TrafficRow,
    db_retry,
    insert_traffic_rows,
    load_traffic_rows,
    update_traffic_rows,
)
from psh.gateway import TerminusError, terminus, terminus_data
```

Then, in this order, the four moved items — **extract from `psh/_legacy.py` verbatim**
(e.g. `sed -n '53,68p;265,336p' psh/_legacy.py` etc.), then apply ONLY these named edits
(SPEC §3/§5; every other byte identical):

1. `traffic_table_columns` (53–68): no edits.
2. `get_old_metrics` (265–336): `-> list:` → `-> list[dict]:`; the `strptime` call (288)
   gains `# noqa: DTZ007 -- Pantheon env:metrics timestamps are naive date markers; only
   .date() is taken, and attaching a tzinfo risks an off-by-one-day shift (a behavior
   change a move may not make)` on its opening line.
3. `estimate_month_visits` (485–507): `if last_day >= 25:` and `elif last_day >= 15:`
   each gain `  # noqa: PLR2004 -- extrapolation-weighting day thresholds; inline per
   the original`.
4. `build_traffic_table_rows` (510–633):
   - def line gains `  # noqa: C901, PLR0912, PLR0915, PLR0913 -- moved verbatim
     (CAMPAIGN.md section 3.1: moves get no algorithmic redesign); the 12-arg signature
     is pinned by tests and the main() call site`
   - first body lines after the docstring become:
     ```python
     # Cycle: _legacy imports this module.  overage_blocks moves to psh.plans at I7.
     from psh._legacy import overage_blocks  # noqa: PLC0415

     traffic_table_rows = {}
     ```
   - `for month in visits_by_month.keys():` → `for month, month_visits in
     visits_by_month.items():`, and the two `visits_by_month[month]` reads (the
     `"visitors"` f-string and the `overage = max(...)` line) → `month_visits`
   - the four clamp sites →
     ```python
     ymd = max(ymd, first_plan_day)
     ymd = min(ymd, last_plan_day)
     ymd1 = max(ymd1, start_date)
     ```
     (replacing the three 2-line `if` guards) and
     `d = max(ymd, first_plan_day)` (replacing the conditional expression)
   - the month-label `strptime` (559) gains `# noqa: DTZ007 -- "YYYY-MM" month label
     parsed only to re-format as "Month YYYY"; no instant, no timezone` on its opening
     line
   - `f"used 1 month, "` → `"used 1 month, "`; `f"1 month remaining"` →
     `"1 month remaining"`

Then the four NEW flow functions, exactly:

```python
def update_site_traffic(
    db_session, site: dict, live_site: str, start_date: datetime.date, end_date: datetime.date
) -> bool:
    """Fetch a site's daily env:metrics and merge them into pantheon_traffic.

    Returns False when the metrics fetch was fatal or undecodable (the caller skips the
    site), True once the rows are merged (B22+B23 of main()'s per-site loop).
    """
    metrics, errors, fatal = terminus("env:metrics", live_site, "--period=day")
    if fatal or metrics is None:
        sc.console.print(
            f":exclamation: [bold red] ERROR: could not fetch metrics for {site['name']}: {escape(errors)}"
        )
        return False

    sc.debug(f"[bold magenta]=== Updating metrics for {site['name']}:")
    db_retry(
        db_session,
        lambda: update_traffic_rows(db_session, site, metrics, start_date, end_date),
        what=f"updating traffic rows for {site['name']}",
        site=site["name"],
    )
    return True


def import_older_site_metrics(
    db_session, site: dict, live_site: str, end_date: datetime.date
) -> None:
    """Backfill daily rows from Pantheon's weekly/monthly aggregates (B24; --import-older-metrics)."""
    sc.console.print(
        f"[bold magenta]=== Importing older metrics for {site['name']}:"
    )
    # The terminus call stays OUTSIDE the retried unit: a retry must not re-run it.
    # Order (fetch week -> insert week -> fetch month -> insert month) is unchanged.
    for period in ("week", "month"):
        new_rows = get_old_metrics(live_site, site, period, end_date)
        db_retry(
            db_session,
            lambda rows=new_rows: insert_traffic_rows(db_session, rows),
            what=f"importing older {period} metrics for {site['name']}",
            site=site["name"],
        )


def load_site_traffic(
    db_session, site: dict, start_date: datetime.date, end_date: datetime.date
) -> list[TrafficRow]:
    """Load the report window's TrafficRows and release the DB connection (B26).

    The retried unit is load_traffic_rows(), whose post-SELECT commit releases the
    connection before the multi-minute per-site gather -- see load_traffic_rows().
    """
    results = db_retry(
        db_session,
        lambda: load_traffic_rows(db_session, site, start_date, end_date),
        what=f"loading traffic rows for {site['name']}",
        site=site["name"],
    )
    sc.debug(
        f"{len(results)} records found in the database for {site['name']} "
        f"between {start_date} and {end_date}:",
        level=2,
    )
    return results


def aggregate_visits_by_month(
    rows: list[TrafficRow], start_date: datetime.date, end_date: datetime.date
) -> tuple[dict[str, int], dict[datetime.date, str]]:
    """Aggregate TrafficRows into (visits_by_month, plan_on_day) -- B43's aggregation.

    visits_by_month seeds every "%Y-%m" month in [start_date, end_date] to 0, then sums
    row.visits into its month; plan_on_day maps each row's traffic_date to its site_plan
    (last row wins).  Rows are assumed in-window (load_traffic_rows() returns only such);
    an out-of-window month KeyErrors, exactly as the inline code this replaces did.
    """
    visits_by_month: dict[str, int] = {}
    plan_on_day: dict[datetime.date, str] = {}
    d = start_date
    while d <= end_date:
        month = d.strftime("%Y-%m")
        visits_by_month[month] = 0
        d = d.replace(day=1) + datetime.timedelta(days=32)
        d = d.replace(day=1)
    for row in rows:
        month = row.traffic_date.strftime("%Y-%m")
        visits_by_month[month] += row.visits
        plan_on_day[row.traffic_date] = row.site_plan
    return visits_by_month, plan_on_day
```

The inner-body lines of `get_old_metrics`'s flow ancestors are already covered above;
the flow-function bodies are the loop-body lines moved verbatim modulo the function
headers/returns shown (SPEC Deliverable B). NOTE: the commented-out
`# for row in results:` / `#    sc.debug(row, level=2)` pair from the B26 region is
**deleted**, not moved (SPEC §5 ERA001 row).

- [ ] **Step 2: Rewrite `psh/_legacy.py`.** Bottom-up so line numbers stay valid:

  a. Replace 3036–3052 (the `# Create an array…` comment through the verbose `pprint`
     block) with:

     ```python
                 visits_by_month, plan_on_day = aggregate_visits_by_month(
                     results, start_date, end_date
                 )
                 if sc.options.verbose:
                     pprint(visits_by_month)
                     if sc.options.verbose > 1:
                         pprint(plan_on_day)
     ```

     (12-space indent — inside the per-site loop; the `pprint` block is kept in `main()`
     verbatim, SPEC D-i6-4.)

  b. Replace 1904–1957 (the `# Metrics for an uninitialized…` comment through the
     commented-out debug loop) with:

     ```python
                 # Metrics for an uninitialized live environment will be all zeroes; this is OK.

                 live_site = site["id"] + ".live"
                 if not update_site_traffic(db_session, site, live_site, start_date, end_date):
                     continue

                 if sc.options.import_older_metrics:
                     import_older_site_metrics(db_session, site, live_site, end_date)
                     continue  # skip the rest of the processing for the sites

                 if sc.options.update:
                     sc.console.print("site visitors updated, skipping report")
                     continue

                 results = load_site_traffic(db_session, site, start_date, end_date)
     ```

     (B25 — the `if sc.options.update:` pair — is byte-identical to today; the
     `--import-older-metrics` gate and both `continue`s stay in `main()`, SPEC D-i6-1.)

  c. Delete 510–633 (`build_traffic_table_rows`), 485–507 (`estimate_month_visits`),
     265–336 (`get_old_metrics`), 53–68 (`traffic_table_columns`), collapsing to the
     file's standard 2 blank lines between defs (LEDGER I5 deviation-4 precedent).

  d. Add to the import block, after the `from psh.gateway import …` group:

     ```python
     from psh.traffic import (
         aggregate_visits_by_month,
         build_traffic_table_rows,
         estimate_month_visits,
         get_old_metrics,
         import_older_site_metrics,
         load_site_traffic,
         traffic_table_columns,
         update_site_traffic,
     )
     ```

  e. Remove NO other imports (SPEC §1: the move orphans nothing — verified list there).

- [ ] **Step 3: Byte-verification.** Diff each moved body against
  `git show 5de11a4:psh/_legacy.py` and paste the diff in the report, proving the only
  differences are the named edits of Step 1. Also run the Invariant-8 pre-check:
  `awk 'NR>=1904 && NR<=1957' …` region and the four def regions contain no column-0 `f"""`.

- [ ] **Step 4: Task 1's tests now GREEN.**

Run: `./run-tests --fast --llm tests/unit/test_traffic_aggregation.py tests/integration/test_traffic_flow.py`
Expected: `passed=8`.

- [ ] **Step 5: Full suite + gates.**

Run: `./run-tests --fast --llm`
Expected: `LLM_SUMMARY passed=788 failed=0 error=0 skipped=1` (780 baseline + 8 new),
27 snapshots passed, both ruff gates and pyright clean.

Run: `git diff 5de11a4 -- tests/e2e/__snapshots__/ | wc -l` → `0`.

Run: `uvx ruff check --config ruff-broad.toml psh/traffic.py` → `All checks passed!`.

- [ ] **Step 6: Commit.**

```bash
git add psh/traffic.py psh/_legacy.py tests/unit/test_traffic_aggregation.py tests/integration/test_traffic_flow.py
git commit -m "refactor(campaign-I6): move the traffic layer into psh/traffic.py

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Docs, memory, ledger, acceptance

**Files:**
- Modify: `CLAUDE.md` (§ Single-module core: add the `psh/traffic.py` sentence; § Database:
  note `build_traffic_table_rows`' new home in the five-unit list; § Testing pure-helper
  seam: note `estimate_month_visits`/`build_traffic_table_rows` live in `psh/traffic.py`,
  still `psh.<fn>`-resolvable)
- Modify: `/home/node/.claude/projects/-workspace/memory/modularization-campaign.md`
  (progress: I6 done) — and `MEMORY.md` only if the hook line changes
- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md` (append the I6 entry:
  moved set; D-i6-1…5 as ledger notes; the I7 obligations — `overage_blocks` import
  replacement, `psh/plans.py`; ratchet dispositions incl. ERA001; the
  `traffic_table_columns` duplicate-head observation; acceptance figures)
- Modify: `development/2026-07-20-mod-I6-traffic/SPEC.md` (§9 acceptance filled with
  pasted output)

- [ ] **Step 1: CLAUDE.md edits** per the SPEC §8 list — surgical, delete prose the move
  obsoletes (e.g. any "staying in `_legacy.py` until I6" phrasing in § Database's unit
  list).
- [ ] **Step 2: Memory + ledger** per SPEC §8. The ledger entry follows CAMPAIGN §12's
  template verbatim.
- [ ] **Step 3: Acceptance.** Run the full `./run-tests` (live tier if `terminus
  auth:whoami` succeeds; else `--fast` + ledger note), plus the §9 command list; paste
  outputs into SPEC §9 — never summarized.
- [ ] **Step 4: Commit** (the increment's closing commit; the dev folder is committed by
  `/archive-session` afterwards per campaign flow):

```bash
git add CLAUDE.md development/2026-07-17-modularization-campaign/LEDGER.md development/2026-07-20-mod-I6-traffic/
git commit -m "docs(campaign-I6): close the traffic increment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
