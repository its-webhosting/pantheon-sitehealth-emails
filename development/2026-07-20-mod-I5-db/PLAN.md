# I5 — `psh/db.py` (DB layer move) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch
> every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via
> `mattpocock-skills:tdd` (NOT superpowers TDD). The authoritative design is `SPEC.md` in this
> folder — read it in full; this plan is the step sequence, the SPEC carries rationale,
> decisions (D-i5-1…4), and invariants.

**Goal:** Move the ORM models, detached row types, connection-resilience layer, idempotent
DB units of work, and `db_engine_args` into a new gated `psh/db.py`; move the two reconnect
counter dicts to `script_context.py`; four e2e goldens byte-identical throughout.

**Architecture:** Import-back move (I2/I3/I4 precedent): `psh/_legacy.py` re-imports every
moved name so its call sites, the tests' `psh.<name>` references, and the
`sc.db_engine_args` exposure resolve unchanged. The mutable counters do NOT live in
`psh/db.py` (CAMPAIGN §3.4): they become `sc.db_reconnects_by_site` /
`sc.db_reconnect_failures_by_site` — one owning namespace, attribute-accessed at call time
by the writer (`db_retry`, moving) and the remnant readers (`finish_run`/`abort_run`,
staying until I13) — SPEC D-i5-1. `psh/db.py` imports `script_context` at module level
(no cycle; `psh/gateway.py` precedent — SPEC D-i5-2).

**Tech Stack:** Python 3.12+, SQLAlchemy 2.x, ruff (`ruff-broad.toml` `select=ALL`),
pyright (standard), pytest.

## Global Constraints

- **Four e2e goldens byte-identical** (Invariant 1). `--update-goldens` FORBIDDEN. Verify
  `git diff 1cf37d3 HEAD -- tests/e2e/__snapshots__/` is empty at each task end.
- **`psh/db.py` passes the full gate from birth**: `uvx ruff check --config ruff-broad.toml
  psh/db.py script_context.py` → "All checks passed!"; pyright standard → 0 errors.
  `script_context.py` is un-grandfathered (since I4) — its edits must stay clean too.
- **Run pyright via `./run-tests`, NOT `uv run pyright`** (uv.lock churn; `git checkout --
  uv.lock` if it shows modified).
- **No `sc` name removed** (Invariant 9): `sc.db_engine_args` must keep resolving (the
  façade house-rule test pins it). The counters are `sc` **additions** (§3.5 allows).
- **Invariant 5**: the read-release commits in the two loaders and `db_retry`'s
  unit-granularity move byte-identically; `test_load_traffic_rows_releases_the_connection`
  must stay green **unweakened**.
- **Moved bodies are verbatim** except the SPEC Deliverable-A named edits (repeated inline
  below). The Task 1 report MUST paste the region diff proving the only differences are
  those edits.
- **No test dropped, no assertion weakened** (SPEC D-i5-3 "intact"): expected counts
  unchanged from I4 close — `--fast` = 780 passed / 1 skipped; full (live tier) = 782 / 1.
- **Safety interlock**: no `--all`/`--for-real`/live `--create-tables` in tests.
- Clear stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 note).
- Baseline commit (I5 start) = `1cf37d3`.
- Every task report cites Spine directives by number with a verbatim quote (agent config).
- The inner loop is `./run-tests --fast --llm`; run it at every task end.

---

### Task 1: The move — `psh/db.py` + counters to `sc` + re-imports + test repoints

One atomic commit: the code, the state, the re-imports, and the test repoints — partial
application cannot be green. Behavior-preserving relocation; **no new tests are owed**
(SPEC §4 Deliverable D) — the existing suites are the guard and must stay green unchanged
in count.

**Files:**
- Create: `psh/db.py`
- Modify: `script_context.py` (add the two counter dicts + their moved comments)
- Modify: `psh/_legacy.py` (delete lines 93–167, 821–826, 829–838, 841–1061 **minus**
  1064–1076 which stays, 1079–1109; add the re-import; repoint 4 counter reads; orphaned
  imports)
- Modify: `tests/conftest.py` (`_SC_ATTRS` + `reset_sc`)
- Modify: `tests/unit/test_db_resilience.py`, `tests/unit/test_traffic_table_rows.py`,
  `tests/integration/test_db_credentials.py`, `tests/integration/test_abort_run.py`,
  `tests/integration/test_finish_run.py` (counter-seam repoints only)

**Interfaces:**
- Produces: `psh.db.{Base, PantheonTraffic, PantheonOverageProtection, TrafficRow,
  OverageProtectionRow, DatabaseUnavailableError, record_db_reconnect, db_retryable,
  db_retry, update_traffic_rows, insert_traffic_rows, load_traffic_rows,
  load_overage_protection_window, db_engine_args}` — all re-imported by `psh._legacy`;
  `sc.db_reconnects_by_site: dict[str, int]`, `sc.db_reconnect_failures_by_site:
  dict[str, int]`.

- [ ] **Step 1: Baseline green.** Run `./run-tests --fast --llm`; record the LLM_SUMMARY
  line (expect `passed=780 … skipped=1`).

- [ ] **Step 2: Create `psh/db.py`.** Header verbatim:

```python
"""The database layer: every table this program touches and every query it runs.

ORM models (PantheonTraffic, PantheonOverageProtection), their detached row types
(TrafficRow, OverageProtectionRow), the connection-resilience layer (DatabaseUnavailableError /
record_db_reconnect / db_retryable / db_retry), the idempotent units of work it protects
(update_traffic_rows, insert_traffic_rows, load_traffic_rows, load_overage_protection_window),
and db_engine_args -- the ONE engine builder, also exposed as sc.db_engine_args so
plugin/umich/portal.py gets the same pool settings (CLAUDE.md § Database).

Moved from psh/_legacy.py at campaign increment I5 (CAMPAIGN.md section 3.1;
development/2026-07-20-mod-I5-db/SPEC.md).  The governing design is
development/2026-07-13-db-connection-resilience/SPEC.md, which the docstrings below cite by
bare section number.

The run-scoped reconnect counters (db_reconnects_by_site / db_reconnect_failures_by_site)
live in script_context, NOT here: CAMPAIGN.md section 3.4 bars module-level mutable state in
psh/ modules, and the remnant's finish_run/abort_run read them until I13's RunState absorbs
them -- one owning namespace (sc), attribute-accessed at call time by the writer (db_retry,
below) and the remnant readers (SPEC D-i5-1).
"""
import datetime
import sys
import time
from typing import NamedTuple

from rich.markup import escape
from sqlalchemy import (
    Boolean,
    Date,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    insert,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR

import script_context as sc
```

  Then the bodies, moved **verbatim** from `psh/_legacy.py` in this order, with exactly
  these edits (SPEC Deliverable A) and no others:

  1. Lines 93–167 (`Base`, `PantheonTraffic`, `PantheonOverageProtection`, `TrafficRow`,
     `OverageProtectionRow`). ONE edit — delete line 100:
     `    # id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)`
  2. Lines 821–826 (`DatabaseUnavailableError`). No edits.
  3. Lines 841–926 (`record_db_reconnect`, `db_retryable`, `db_retry`). Edits in
     `db_retry` only:
     - signature: `def db_retry(session, unit, *, what: str, site: str | None = None):`
     - the four counter calls gain the `sc.` prefix:
       `record_db_reconnect(sc.db_reconnect_failures_by_site, site)` (3×, lines
       901/917/919) and `record_db_reconnect(sc.db_reconnects_by_site, site)` (line 925).
  4. Lines 929–961 (`update_traffic_rows`). ONE edit — the strptime line gains a noqa:

```python
        traffic_date = datetime.datetime.strptime(  # noqa: DTZ007 -- Pantheon env:metrics timestamps are naive date markers; only .date() is taken, and attaching a tzinfo risks an off-by-one-day shift (a behavior change a move may not make)
            entry["datetime"], "%Y-%m-%dT%H:%M:%S"
        ).date()
```

  5. Lines 964–980 (`insert_traffic_rows`). No edits.
  6. Lines 983–1021 (`load_traffic_rows`). No edits — including the
     `session.commit()  # releases the connection …` line (Invariant 5).
  7. Lines 1024–1061 (`load_overage_protection_window`). No edits — same commit rule.
  8. Lines 1079–1109 (`db_engine_args`). ONE edit — signature:
     `def db_engine_args(db_config: dict) -> tuple[str, dict]:`

  Do NOT move lines 817–818 (`ResumeSiteNotFoundError`), 1064–1076
  (`sites_from_resume_point`), 1112–1141 (`merge_prior_results`) — they stay for I13.

- [ ] **Step 3: `script_context.py` gains the counters.** After the existing mutable-state
  globals (`plugin_context` block), insert (comments verbatim from `_legacy.py:829–838`,
  with the one named doc-accuracy edit: the bare `(SPEC 3.6)` becomes the full path, since
  the comment leaves the file whose convention resolved it):

```python
# Reconnects HEALED by db_retry() -- the retry ran and succeeded -- attributed to the site that
# caused them.  Counted only after the second attempt returns: counting the attempt instead would
# let an aborted run report a reconnect it never actually made.
db_reconnects_by_site: dict[str, int] = {}

# Connection losses db_retry() could NOT heal, attributed the same way: the retry failed, or the
# rollback before it did.  The counterpart of the dict above, and the reason it can be trusted --
# every lost connection lands in exactly one of the two, so "0 healed" never means "nothing
# happened".  Both are reported on the console and in {ymd}-run.json
# (development/2026-07-13-db-connection-resilience/SPEC.md 3.6).  Written by psh.db.db_retry;
# read by finish_run/abort_run; absorbed into RunState at campaign I13.
db_reconnect_failures_by_site: dict[str, int] = {}
```

- [ ] **Step 4: `psh/_legacy.py` re-import + deletions + reader repoints.**
  - Delete the moved regions (Step 2 list) AND the counter block (829–838).
  - Next to the existing `from psh.gateway import …` / `from psh.configuration import …`
    re-imports, add:

```python
from psh.db import (
    Base,
    DatabaseUnavailableError,
    OverageProtectionRow,
    PantheonOverageProtection,
    PantheonTraffic,
    TrafficRow,
    db_engine_args,
    db_retry,
    db_retryable,
    insert_traffic_rows,
    load_overage_protection_window,
    load_traffic_rows,
    record_db_reconnect,
    update_traffic_rows,
)
```

  - Repoint the four remnant-reader counter reads (post-deletion line numbers will have
    shifted; find by content):

```python
    reconnects = sum(sc.db_reconnects_by_site.values())
    reconnect_failures = sum(sc.db_reconnect_failures_by_site.values())
```

```python
                "reconnects_by_site": dict(sc.db_reconnects_by_site),
                "reconnect_failures_by_site": dict(sc.db_reconnect_failures_by_site),
```

  - Remove ONLY the orphaned imports (SPEC Deliverable C, grep-verify each before
    removing): the seven-name `from sqlalchemy import (Boolean, Date, Integer,
    PrimaryKeyConstraint, String, UniqueConstraint, insert)` block, the `sqlite_insert`
    line, `OperationalError` (keep `DBAPIError` and `SQLAlchemyError` on that line),
    the `from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column` line, the
    `CHAR` line, and `NamedTuple`. KEEP: `sqlalchemy as db`, `time`, `escape`,
    `datetime`.
  - The `sc.db_engine_args = db_engine_args` exposure line stays untouched.

- [ ] **Step 5: conftest isolation.** In `tests/conftest.py`, extend `_SC_ATTRS`:

```python
_SC_ATTRS = (
    "options",
    "config",
    "news",
    "hooks",
    "substitutions",
    "plugin",
    "check",
    "plugin_context",
    "db_reconnects_by_site",
    "db_reconnect_failures_by_site",
)
```

  and in `reset_sc`, after `sc.plugin_context = {}`:

```python
    sc.db_reconnects_by_site = {}
    sc.db_reconnect_failures_by_site = {}
```

- [ ] **Step 6: test-seam repoints.** Find every site with
  `grep -rn 'psh, "db_reconnect\|psh\.db_reconnect' tests/`. In each of the five files,
  add `import script_context as sc` if absent, then mechanically:
  `monkeypatch.setattr(psh, "db_reconnects_by_site", X)` →
  `monkeypatch.setattr(sc, "db_reconnects_by_site", X)` (same for `…_failures_…`), and
  assertions `psh.db_reconnects_by_site` → `sc.db_reconnects_by_site` (same for failures).
  Example (`test_db_resilience.py:74`):

```python
    monkeypatch.setattr(sc, "db_reconnects_by_site", {})  # never assign: sc is shared module state
```

  No other test edits. A missed site fails LOUD (`monkeypatch.setattr` raises
  `AttributeError` on the now-missing `psh` attribute) — zero must remain.

- [ ] **Step 7: byte-verification.** Paste into the task report the proof that the moved
  bodies differ from baseline only by the named edits:

```bash
git show 1cf37d3:psh/_legacy.py | sed -n '93,167p'   > /tmp/old_models.py
git show 1cf37d3:psh/_legacy.py | sed -n '821,826p'  > /tmp/old_dbexc.py
git show 1cf37d3:psh/_legacy.py | sed -n '841,1061p' > /tmp/old_defs.py
git show 1cf37d3:psh/_legacy.py | sed -n '1079,1109p' > /tmp/old_engine.py
# diff each against the corresponding psh/db.py region; every hunk must be one of the
# named edits (deleted ERA001 line, sc.-prefixed counter calls, the two signatures, the
# DTZ007 noqa) or the excluded resume helpers. Paste the diffs.
```

- [ ] **Step 8: gates.** Run and paste output of each:
  - `./run-tests --fast --llm` → `passed=780 failed=0 error=0 skipped=1`, 27 snapshots
  - `git diff 1cf37d3 -- tests/e2e/__snapshots__/ | wc -l` → `0`
  - `uvx ruff check --config ruff-broad.toml psh/db.py script_context.py` → clean
  - `uvx ruff check .` → clean

- [ ] **Step 9: Commit.**

```bash
git add psh/db.py psh/_legacy.py script_context.py tests/conftest.py \
  tests/unit/test_db_resilience.py tests/unit/test_traffic_table_rows.py \
  tests/integration/test_db_credentials.py tests/integration/test_abort_run.py \
  tests/integration/test_finish_run.py
git commit -m "refactor(campaign-I5): move the DB layer into psh/db.py

Models, row types, db_retry/db_retryable, the idempotent units of work, and
db_engine_args move to a new gated psh/db.py (re-imported by _legacy, I2 pattern).
The reconnect counters move to script_context (sc.) -- one owning namespace for
the moving writer and the remnant readers (SPEC D-i5-1); test seams repoint.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Docs, memory, ledger

**Files:**
- Modify: `CLAUDE.md` (§ Database + the two module-map mentions)
- Modify: `/home/node/.claude/projects/-workspace/memory/db-idle-connection-reaped.md`,
  `modularization-campaign.md`, `MEMORY.md` (if hooks change)
- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md` (append I5 entry)
- Modify: `development/2026-07-20-mod-I5-db/SPEC.md` (paste acceptance outputs into §9)

**Interfaces:** none (docs only).

- [ ] **Step 1: CLAUDE.md.** In § Architecture's module list, add `psh/db.py` alongside
  the gateway/configuration/notice/modules entries (models, row types, resilience layer,
  `db_engine_args`; re-imported by `_legacy.py`, same import-back pattern; counters live
  in `script_context.py` as `sc.` attributes until I13's `RunState`). In § Database,
  correct "(see class defs near the top of the script)" to name `psh/db.py`, and note the
  test seam: the counters are patched at the `script_context` module (patching the old
  `psh` binding no longer exists — it fails loudly). In § Testing's mock-seam bullet, no
  change (the `psh.time.sleep` guidance still holds). Delete any prose the move obsoletes;
  report the line-count delta.

- [ ] **Step 2: Memory.** Update `db-idle-connection-reaped.md`: the resilience layer now
  lives in `psh/db.py`; counters are `sc.db_reconnects_by_site`/
  `sc.db_reconnect_failures_by_site` (patch at `script_context`, not `psh`). Update
  `modularization-campaign.md`: I5 complete, I6 (traffic) next.

- [ ] **Step 3: LEDGER.md entry** (template per CAMPAIGN §12): Moved (the §3.1 psh/db.py
  row, by name); Deviations: none expected — ledger notes D-i5-1 (counters to
  `script_context`, why, RunState destination), D-i5-3 ("relocated intact" reading),
  B10/B11 stay for I13; Contract/config/sc additions: the two `sc` counter attributes
  (not façade-documented); Discovered tasks: whatever Task 1 surfaced; Open questions
  for I6: per CAMPAIGN §11 row I6.

- [ ] **Step 4: Acceptance.** Run `./run-tests --llm` (full; live tier if credentials
  present — else `--fast` and note it in the ledger entry). Paste outputs into SPEC §9.

- [ ] **Step 5: Commit.**

```bash
git add CLAUDE.md development/2026-07-20-mod-I5-db/ \
  development/2026-07-17-modularization-campaign/LEDGER.md
git commit -m "docs(campaign-I5): close the DB-layer increment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(The memory files live outside the repo — written, not committed.)

---

## Self-review (run against SPEC.md)

- Spec coverage: SPEC §1 items 1–6 → Task 1 (items 1–5) + Task 2 (item 6). Deliverables
  A/B/C/D → Task 1 Steps 2/3/4/5–6. Ratchet §5 → the named edits + Step 8 gates.
  §8 docs/memory → Task 2. §9 acceptance → Task 2 Step 4. No gaps.
- Placeholder scan: all edits shown concretely; the verbatim-move regions are specified by
  exact baseline line ranges with a mandatory diff-verification step (Step 7) — the source
  of truth for a move is the source file, not a re-typed copy.
- Type consistency: `tuple[str, dict]` and `str | None` appear identically in SPEC
  Deliverable A and Task 1 Step 2; the counter names are spelled identically in Steps 3–6.
