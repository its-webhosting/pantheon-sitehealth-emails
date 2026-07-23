# I11 `psh/charts.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the per-site traffic-chart build (B13 cap geometry + B44 data prep + B45
matplotlib build) out of `main()` into `psh/charts.py` as `build_chart(...) -> bytes`,
behavior-preserving, per `development/2026-07-23-mod-I11-charts/SPEC.md`.

**Architecture:** One new Tier-1 module, one public function, re-imported by
`psh/_legacy.py` (the I2–I10 import-back pattern). The exact module content was
pre-measured and smoke-tested during spec writing and is archived at
`development/2026-07-23-mod-I11-charts/charts-scratch-measured.py` — Task 2 installs it
rather than re-deriving the move by hand, then verifies it against the live source.

**Tech Stack:** Python 3.12, matplotlib/numpy (existing deps), pytest (integration tier),
ruff broad config + pyright standard (campaign ratchet).

## Global Constraints

- SPEC.md governs; it cites CAMPAIGN.md by section. Deviations surface via task status,
  never silently (implementation-standards § Deviation discipline).
- TDD loop is `mattpocock-skills:tdd` (NOT superpowers:test-driven-development). Seam:
  `psh.charts.build_chart`, declared in SPEC §4 — the only sanctioned test seam.
- Four e2e goldens byte-identical; no golden/fixture refresh (Invariants 1, 10).
- `psh/charts.py` must be clean under `uvx ruff check --config ruff-broad.toml` and
  pyright standard (`./run-tests` gate 3) from birth; narrow ruff set stays green
  whole-tree.
- Single atomic code commit for tests+move (Tasks 1–2): a partial move cannot be green
  (I5/I6 precedent, SPEC §7).
- Baseline `--fast` tier ≈ 989 passed / 1 skipped / 2 deselected (derived from LEDGER
  I10's 991 full-tier close; Task 1 measures and pins the real figure).

---

### Task 1: RED tests at the `build_chart` seam + pre-move baselines

**Files:**
- Create: `tests/integration/test_charts.py`
- Create: `development/2026-07-23-mod-I11-charts/chart-hashes-before.txt`

**Interfaces:**
- Produces: the five tests Task 2 must turn green; the pre-move chart-payload hashes
  Task 2's acceptance compares against.

- [ ] **Step 1: Measure the real `--fast` baseline**

Run: `./run-tests --fast --llm 2>&1 | tail -3`
Record the `LLM_SUMMARY passed=… skipped=…` line in the task report (expected ≈
`passed=989 skipped=1`).

- [ ] **Step 2: Write the failing tests**

Create `tests/integration/test_charts.py` with exactly:

```python
"""Seam tests for psh.charts.build_chart (campaign I11, SPEC section 4 Deliverable C).

Integration tier: real matplotlib (Agg backend -- conftest sets MPLBACKEND before any
import), real sc (the autouse reset_sc fixture provides sc.options, which sc.debug
reads).  The chart PNG is NOT pinned by the e2e goldens (the .eml has no byte golden),
so these tests are the permanent behavioral cover for the chart build; the increment's
move-time byte-preservation evidence was SPEC section 6's before/after payload-hash
comparison, recorded in the dev folder.
"""

import datetime
import struct

import matplotlib.pyplot as plt
import pytest

from psh.charts import build_chart

pytestmark = pytest.mark.integration

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# One plan spanning the whole window keeps the fixture minimal; upgrade_at 20,000
# puts the surge threshold at 30,000 (upgrade_at_max * 1.5).
PLAN_INFO = {
    "Basic": {"traffic_limit": 25000, "upgrade_at": 20000, "downgrade_to": None},
}
SURGE_SPIKE = 90_000  # far above the 30,000 threshold
MONTHS = [
    "2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01",
    "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
]


def png_size(png):
    """Width/height from the IHDR chunk (always first, big-endian uint32 at 16/20)."""
    return struct.unpack(">II", png[16:24])


def shaped_locals(spike=None):
    """The 13 build_chart kwargs, shaped like main()'s locals (SPEC D-i11-1).

    plan_on_day carries every month midpoint -- the documented precondition
    (SPEC D-i11-7): the clamp in the covered-visits loop must land on existing keys.
    """
    visits_by_month = {m: 1000 + 500 * i for i, m in enumerate(MONTHS)}
    if spike is not None:
        visits_by_month[MONTHS[5]] = spike
    dates = [datetime.date.fromisoformat(m + "-15") for m in MONTHS]
    plan_on_day = {d: "Basic" for d in dates}
    return {
        "site": {"name": "charts-test"},
        "site_url": "https://charts.example.edu",
        "visits_by_month": visits_by_month,
        "plan_on_day": plan_on_day,
        "plan_info": PLAN_INFO,
        "plan_over_time": [
            {"plan": "Basic", "start": dates[0], "end": datetime.date(2026, 7, 31)},
        ],
        "dates": dates,
        "estimate": 4200,
        "first_plan_day": dates[0],
        "last_plan_day": dates[-1],
        "start_date": datetime.date(2025, 8, 1),
        "end_date": datetime.date(2026, 7, 31),
        "plot_right_date": datetime.date(2026, 7, 31),
    }


def test_returns_png_bytes():
    png = build_chart(**shaped_locals())
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 1000


def test_surge_renders_taller_two_axes_figure():
    """The surge branch builds the 12x12 GridSpec figure vs the plain 12x9 one, so at
    equal dpi the surge PNG is strictly taller -- proves the branch ran, not just that
    some PNG came back."""
    plain = build_chart(**shaped_locals())
    surge = build_chart(**shaped_locals(spike=SURGE_SPIKE))
    plain_w, plain_h = png_size(plain)
    surge_w, surge_h = png_size(surge)
    assert plain_w == surge_w
    assert surge_h > plain_h


def test_estimate_changes_the_render():
    """estimate=-1 (month already over) must drop the estimate bars/labels.  Guards the
    estimates=[] prologue init (SPEC D-i11-4) against a regression that skips the
    estimate histogram entirely."""
    kwargs = shaped_locals()
    with_estimate = build_chart(**kwargs)
    kwargs["estimate"] = -1
    without_estimate = build_chart(**kwargs)
    assert with_estimate != without_estimate


def test_deterministic_bytes():
    """Two identical calls -> identical bytes: the property the .eml reproducibility
    and SPEC section 6's hash evidence rest on (PD#14: prove it, don't assume it)."""
    assert build_chart(**shaped_locals()) == build_chart(**shaped_locals())


def test_no_leaked_figures():
    """Guards the moved plt.close(fig): a leak is invisible until a 300-site --all run
    exhausts memory."""
    build_chart(**shaped_locals())
    build_chart(**shaped_locals(spike=SURGE_SPIKE))
    assert plt.get_fignums() == []
```

- [ ] **Step 3: Watch the tests fail for the right reason**

Run: `.venv/bin/python -m pytest tests/integration/test_charts.py -v 2>&1 | tail -5`
Expected: collection error — `ModuleNotFoundError: No module named 'psh.charts'`
(NOT an assertion failure, NOT a fixture error). Paste the output in the task report.

- [ ] **Step 4: Record the pre-move chart-payload hashes**

Run SPEC §6's procedure from repo root and save its output:

```bash
.venv/bin/python - <<'EOF' | tee development/2026-07-23-mod-I11-charts/chart-hashes-before.txt
import email, hashlib, pathlib, sys, tempfile
sys.path.insert(0, "tests"); sys.path.insert(0, ".")
from conftest import make_workdir, build_rendered_report, E2E_SITE
work = make_workdir(pathlib.Path(tempfile.mkdtemp()))
build_rendered_report(work)
msg = email.message_from_bytes((work / "build" / f"{E2E_SITE}.eml").read_bytes())
for part in msg.walk():
    if part.get_content_type() == "image/png":
        payload = part.get_payload(decode=True)
        print(part.get_filename(), len(payload), hashlib.sha256(payload).hexdigest())
EOF
```

Expected: two lines — the wordmark banner and `pantheon-traffic_its-wws-test1_*.png`
(the chart). Both recorded; the chart line is the one Task 2 compares.

- [ ] **Step 5: No commit** — the suite is red (`test_charts.py` cannot import). The
  atomic commit happens at the end of Task 2 (Global Constraints; I5/I6 precedent).

---

### Task 2: The move — install `psh/charts.py`, rewire `psh/_legacy.py`, go green

**Files:**
- Create: `psh/charts.py` (from the archived measured assembly)
- Modify: `psh/_legacy.py` (import add, four deletion sites, one call-site insertion)
- Create: `development/2026-07-23-mod-I11-charts/chart-hashes-after.txt`

**Interfaces:**
- Consumes: Task 1's tests and `chart-hashes-before.txt`.
- Produces: `psh.charts.build_chart(site, site_url, visits_by_month, plan_on_day,
  plan_info, plan_over_time, dates, estimate, first_plan_day, last_plan_day,
  start_date, end_date, plot_right_date) -> bytes` — exactly SPEC D-i11-1's signature.

- [ ] **Step 1: Install the measured assembly**

```bash
cp development/2026-07-23-mod-I11-charts/charts-scratch-measured.py psh/charts.py
```

Then replace ONLY its one-line docstring (line 1) with the final module docstring:

```python
"""The per-site traffic chart: cap geometry, data prep, matplotlib build -> PNG bytes.

Moved out of main()'s per-site loop by campaign increment I11 (CAMPAIGN.md section 3.1:
B13's cap-shape geometry + B44 chart data prep + B45 matplotlib build).  main() calls
build_chart() with the shaped per-site locals (SPEC D-i11-1) and attaches the returned
PNG to the report email (B55, still in psh/_legacy.py until I12).

Precondition (documented, not handled -- the D-i6-4 posture): plan_on_day must contain
every month midpoint clamped to [first_plan_day, last_plan_day].  Production data always
satisfies this (plan_on_day maps every traffic-row date, and first_plan_day /
last_plan_day are its min/max), and a violation raises KeyError exactly as the pre-move
code did.

Two scoped-suppression families live in this file (each site carries the narrowest
per-line ignore; see SPEC section 5):
- pyright reportArgumentType: matplotlib's stubs reject runtime-valid dynamic API use
  (datetime bin edges, BarContainer unions, NDArray xlims, tuple transform points);
  the code is moved verbatim and exercised end-to-end by the e2e goldens.
- pyright reportPossiblyUnboundVariable: ax_surge / est_bars / bars are bound iff the
  surge branch or the axes loop ran, which pyright cannot correlate.  A None init would
  trade these for optional-member errors and a fabricated default would silently draw
  on the wrong axes (PD#1) -- the loud runtime NameError is the correct failure mode.
"""
```

- [ ] **Step 2: Verify the assembly is the verbatim move (Invariant 8 evidence)**

Regenerate the raw extraction and diff it against the installed module; every hunk must
be one of SPEC §3's named edits (paste the diff in the task report):

```bash
.venv/bin/python - <<'EOF' > /tmp/charts-raw-extract.py
import pathlib
src = pathlib.Path("psh/_legacy.py").read_text().splitlines(keepends=True)
cap = [l[4:] if l.strip() else l for l in src[1092:1101]]   # 1093-1101, de-indent 4
body = [l[8:] if l.strip() else l for l in src[1489:1851]]  # 1490-1851, de-indent 8
print("".join(cap) + "".join(body), end="")
EOF
diff /tmp/charts-raw-extract.py psh/charts.py | head -150
```

Also confirm no triple-quoted literal is in the moved regions:
`sed -n '1093,1101p;1490,1851p' psh/_legacy.py | grep -c '"""'` → `0`.

- [ ] **Step 3: Rewire `psh/_legacy.py`** (all edits anchored, exhaustive):

1. **Import add** — insert before the `from psh.gather import (` block:
   ```python
   from psh.charts import build_chart
   ```
2. **Delete the orphaned imports** (each name's only uses moved — SPEC §1 item 3):
   `import io` (line 17), `import matplotlib`, `import matplotlib.dates as mdates`,
   `import matplotlib.patheffects as path_effects`, `import matplotlib.pyplot as plt`,
   `import numpy as np` (lines 33–37), `from matplotlib.gridspec import GridSpec`,
   `from matplotlib.patches import Polygon` (lines 40–41).
3. **Delete the `end_date_yyyy_mm` line** (anchor: the line
   `end_date_yyyy_mm = end_date.strftime("%Y-%m")` between `end_date = sc.options.date`
   and the `start_date = end_date.replace(` line).
4. **Delete the cap-geometry block** (anchor: from the comment
   `# Generate a cap shape to use at the end of the traffic surge chart bars` through
   `cap_points = np.concatenate(([[0, 0]], cap_points, [[cap_size, 0]]), axis=0)`).
5. **Delete the `visits` line** (anchor: `visits = list(visits_by_month.values())`
   directly below the `dates = [datetime.date.fromisoformat(...)]` line).
6. **Replace the chart region** — from `visits_covered_by_month = {}` (the line after
   the `--only-warn` gate's `continue` + blank line) through `plt.close(fig)` AND the
   `# TODO: Create SVG chart` line two lines below — with:
   ```python
               chart_image = build_chart(
                   site, site_url, visits_by_month, plan_on_day, plan_info,
                   plan_over_time, dates, estimate, first_plan_day, last_plan_day,
                   start_date, end_date, plot_right_date,
               )
   ```
   (12-space indent — inside the per-site loop; the following
   `site_context.add_notices(build_smell_notices(...))` call is the next statement.)
7. Collapse any blank-line runs the deletions leave to the file's standard 2
   (the I5 disclosed-precedent rule; no code line touched).

- [ ] **Step 4: Watch Task 1's tests pass**

Run: `.venv/bin/python -m pytest tests/integration/test_charts.py -v`
Expected: 5 passed.

- [ ] **Step 5: Full fast suite + goldens**

Run: `./run-tests --fast --llm 2>&1 | tail -4`
Expected: `passed = <Task 1 baseline> + 5`, `failed=0`, goldens among the snapshots
passing. Then: `git diff -- tests/e2e/__snapshots__/ | wc -l` → `0`.

- [ ] **Step 6: Post-move chart-payload hashes**

Re-run Task 1 Step 4's script, saving to
`development/2026-07-23-mod-I11-charts/chart-hashes-after.txt`, then:

```bash
diff development/2026-07-23-mod-I11-charts/chart-hashes-{before,after}.txt && echo BYTE-IDENTICAL
```

Expected: `BYTE-IDENTICAL`. A differing chart hash is a STOP — the move changed
rendering; find the divergence, do not proceed.

- [ ] **Step 7: Ratchet gates**

```bash
uvx ruff check --config ruff-broad.toml psh/charts.py   # All checks passed!
uvx ruff check .                                        # All checks passed! (narrow set)
pyright                                                 # 0 errors (scoped gate)
```

- [ ] **Step 8: Commit (single atomic commit: tests + module + rewire + hash records)**

```bash
git add tests/integration/test_charts.py psh/charts.py psh/_legacy.py \
        development/2026-07-23-mod-I11-charts/chart-hashes-before.txt \
        development/2026-07-23-mod-I11-charts/chart-hashes-after.txt
git commit -m "feat(campaign-I11): move the chart build into psh/charts.py

B13 cap geometry + B44 data prep + B45 matplotlib build -> psh.charts.build_chart,
returning PNG bytes; main() threads the shaped locals (SPEC D-i11-1).  Chart payload
proven byte-identical before/after (hash records in the dev folder).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Docs, memory, ledger, acceptance (closing)

**Files:**
- Modify: `CLAUDE.md`, `development/2026-07-23-mod-I11-charts/SPEC.md` (§9),
  `development/2026-07-17-modularization-campaign/LEDGER.md`,
  `/home/node/.claude/projects/-workspace/memory/modularization-campaign.md`

- [ ] **Step 1: CLAUDE.md** (SPEC §8): add the `psh/charts.py` sentence to § Single-module
  core (what lives there, 13-param threading, re-imported by `_legacy.py`, same
  import-back pattern); reword § Testing's conftest MPLBACKEND note to name
  `psh/charts.py` as the matplotlib importer (reached transitively via `_legacy`'s
  re-import); delete/adjust any prose that described the chart living in `main()`.
  Report the line-count delta (implementation-standards Definition of Done).
- [ ] **Step 2: Memory**: update `modularization-campaign.md`'s progress line (I11 done,
  I12 next).
- [ ] **Step 3: LEDGER.md I11 entry** per SPEC §8's list (D-i11-2/3/4/6/7, ratchet
  dispositions, discovered tasks, open questions for I12).
- [ ] **Step 4: Acceptance into SPEC §9**: `terminus auth:whoami`; full `./run-tests --llm`
  (live tier if creds present, else `--fast` + ledger note); `git diff <increment-start-sha>
  -- tests/e2e/__snapshots__/ | wc -l` → 0; both ruff commands; the §6 hash outputs.
  All outputs pasted verbatim, never summarized.
- [ ] **Step 5: Closing docs commit** including the dev folder:

```bash
git add CLAUDE.md development/2026-07-23-mod-I11-charts/ \
        development/2026-07-17-modularization-campaign/LEDGER.md
git commit -m "docs(campaign-I11): close the charts increment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(The `/archive-session` transcript step runs after review, per the campaign session flow.)
