# I0 Campaign Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch implementers as `psh-implementer` per CLAUDE.md § Dispatching subagents.

**Goal:** Turn the 4,752-line script into `psh/_legacy.py` behind a thin committed shim, rework the test harness to import it normally, and install the campaign's lint/type ratchet — with zero behavior change (goldens byte-identical, 727/1/2 test numbers reproduced).

**Architecture:** Whole-file `git mv` into a new `psh/` package (no logic edits), a 7-line launcher shim at the old path, one conftest edit replacing `SourceFileLoader` with `importlib.import_module`, and a second ruff config (`ruff-broad.toml`, `select = ["ALL"]`) gating only non-grandfathered files while today's narrow pyproject config keeps running unchanged everywhere. pyright (standard mode, `psh/` minus `_legacy.py`) joins `run-tests` as a gate.

**Tech Stack:** Python 3.12, pytest, ruff (via `uvx` fallback), pyright, setuptools (deps-only install).

## Global Constraints

- SPEC: `development/2026-07-17-mod-I0-bootstrap/SPEC.md`; campaign rules: `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (§8 behavior bar, §9 invariants).
- `psh/_legacy.py` content is byte-identical to the current script — **no** edits, not even comments or annotations.
- Fast tier must reproduce exactly `727 passed, 1 skipped, 2 deselected`; collect-only totals identical before/after.
- The four goldens must pass unmodified (they run inside the fast tier's e2e subset).
- `psh/_legacy.py` is exempt from the broad ruff set but NEVER from `E722`,`BLE001`,`S105`,`S106` (which stay in pyproject, untouched).
- Tests are load-bearing: no golden/snapshot may be regenerated; a red existing test means the change is wrong, not the test.
- All work happens on `main` (no branch — CLAUDE.md: only branch if explicitly directed). Per-task commits, each leaving the tree green; Task 5's final commit closes the increment with the dev folder included. (Amends CAMPAIGN §12's "one commit" — ledgered in Task 5; finer checkpoints serve PROMPT.md's stated revert/inspect intent.)

---

### Task 1: Capture the pre-change baseline

**Files:** none modified. Output goes into `development/2026-07-17-mod-I0-bootstrap/SPEC.md` § ACCEPTANCE (create the section).

**Interfaces:** Produces: the "before" numbers Task 2's gate compares against.

- [ ] **Step 1: Collection count (must use `python -m`; bare `pytest` cannot collect — pre-existing, not yours to fix)**

Run: `cd /workspace && .venv/bin/python -m pytest -p no:cacheprovider --collect-only -q 2>&1 | tail -2`
Expected: a `N tests collected` / summary line. Record N verbatim.

- [ ] **Step 2: Fast tier**

Run: `./run-tests --fast --llm 2>&1 | tail -4`
Expected: `LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0`, `25 snapshots passed`. Paste into a new `## ACCEPTANCE` section at the end of SPEC.md under "Baseline (Task 1)".

### Task 2: Package move, shim, conftest, coverage

**Files:**
- Move: `pantheon-sitehealth-emails` → `psh/_legacy.py` (git mv, then recreate the shim at the old path)
- Create: `psh/__init__.py`, `psh/cli.py`
- Modify: `tests/conftest.py` (lines 24, 63–95 region), `pyproject.toml` (`[tool.setuptools]`, `[tool.coverage.run]`)
- Test: the existing suite is the test (SPEC § Seams: no new permanent tests)

**Interfaces:** Produces: importable `psh._legacy` (everything the script defined), `psh.cli.main`/`psh.cli.parse_args` (used by the shim now, by everything later). The `pantheon-sitehealth-emails.py` symlink is untouched (it now exposes the shim).

- [ ] **Step 1: Move the file and create the package**

```bash
cd /workspace
mkdir psh
git mv pantheon-sitehealth-emails psh/_legacy.py
```

Create `psh/__init__.py`:

```python
"""pantheon-sitehealth-emails core package.

Being carved out of the legacy single-file script one increment at a time --
see development/2026-07-17-modularization-campaign/CAMPAIGN.md.  Until an
increment moves a symbol into a real module here, it lives in psh._legacy.
"""
```

Create `psh/cli.py`:

```python
"""CLI entry point.

Today a re-export of the legacy module's entry functions; becomes the
orchestrator as increments I2-I13 carve psh._legacy apart (CAMPAIGN.md section 3.1).
"""

from psh._legacy import main, parse_args

__all__ = ["main", "parse_args"]
```

Create the shim at `pantheon-sitehealth-emails` (repo root) and make it executable:

```python
#!/usr/bin/env python
"""Thin launcher for the pantheon-sitehealth-emails program.

The program's code lives in the psh package (psh/_legacy.py until the
modularization campaign finishes carving it up); this file only preserves the
operator-facing ./pantheon-sitehealth-emails invocation.  Running it from the
repo root puts the repo root on sys.path (script-dir rule), which is what
resolves `import psh` and `import script_context`.
See development/2026-07-17-modularization-campaign/CAMPAIGN.md.
"""

import script_context as sc
from psh.cli import main, parse_args

if __name__ == "__main__":
    sc.options = parse_args()
    main()
```

```bash
chmod +x pantheon-sitehealth-emails
git add pantheon-sitehealth-emails psh/
```

- [ ] **Step 2: conftest rework**

In `tests/conftest.py`: delete line 24 (`from importlib.machinery import SourceFileLoader`) and replace the `_load_main_module` body:

```python
def _load_main_module():
    global _main_module
    if _main_module is None:
        # Normal import: run-tests execs `python -m pytest` with cwd = repo root,
        # which puts the repo root on sys.path -- the same mechanism that resolves
        # `import script_context`.  (MPLBACKEND is pinned above, before this ever
        # runs, because psh._legacy imports matplotlib.pyplot at its top.)
        _main_module = importlib.import_module("psh._legacy")
    return _main_module
```

Update the module docstring's sentence about SourceFileLoader (lines ~5–9) to say the program is imported as `psh._legacy`; leave every other line of conftest alone — `PROGRAM`, `_CWD_ASSETS`, `run_program`, interlocks all still apply (PROGRAM now points at the shim, which is exactly what e2e should launch).

- [ ] **Step 3: pyproject guards**

In `pyproject.toml` `[tool.setuptools]`, add `packages = []` under `py-modules = []` with this comment:

```toml
[tool.setuptools]
# Deps-only install, on purpose: the program is repo-rooted (CWD-relative check/,
# plugin/, templates, config symlink), so installing psh into site-packages would
# create a stale shadow copy -- a silent-failure hazard.  packages = [] stops
# setuptools auto-discovery from picking up psh/ now that it exists.
py-modules = []
packages = []
```

Replace `[tool.coverage.run] include` (keep the surrounding comment's first sentence updated):

```toml
[tool.coverage.run]
# Program code now lives in the psh package plus two top-level modules; measure all
# three (the old single-file include glob would match only the 7-line shim).
# In-process tiers only; see tests/README.md for the subprocess-coverage caveat.
include = ["*/psh/*", "*/script_context.py", "*/dns_classify.py"]
```

- [ ] **Step 4: Verify — collection identical, fast tier green, program runs**

Run: `cd /workspace && .venv/bin/python -m pytest -p no:cacheprovider --collect-only -q 2>&1 | tail -2`
Expected: same total as Task 1 Step 1.

Run: `./run-tests --fast --llm 2>&1 | tail -4`
Expected: `LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0` and `25 snapshots passed`. The e2e goldens inside this run are the proof the shim + package work end-to-end. If ruff's narrow pass fails on `psh/_legacy.py` path change: it must not — the four rules had zero findings in the script and content is identical; investigate, don't suppress.

Run: `./pantheon-sitehealth-emails --help; echo "exit=$?"`
Expected: usage text, `exit=0`.

Paste all three outputs into SPEC.md § ACCEPTANCE under "Task 2", then commit:

```bash
git add -A
git commit -m "refactor(campaign-I0): move program into psh/_legacy.py behind a thin shim

Whole-file git mv, no content changes; psh/cli.py re-exports main/parse_args;
conftest imports psh._legacy normally (SourceFileLoader retired for the
program); setuptools kept deps-only (packages=[]); coverage include follows
the code. Goldens byte-identical, 727/1/2 and collection count reproduced.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3: The ratchet — ruff-broad.toml, pyright, run-tests, edit hook

**Files:**
- Create: `ruff-broad.toml`
- Modify: `pyproject.toml` (`[tool.ruff.lint]` stale comment, `[project.optional-dependencies].test`, new `[tool.pyright]`), `run-tests` (lint section), `.claude/hooks/ruff-check.sh`

**Interfaces:** Consumes: `psh/` layout from Task 2. Produces: the two-pass lint gate every later increment relies on; increments un-grandfather files by deleting them from `ruff-broad.toml`'s `exclude`.

- [ ] **Step 1: Create `ruff-broad.toml`**

```toml
# The modularization campaign's ratchet (CAMPAIGN.md section 13) -- ruff pass 2.
# Pass 1 is pyproject.toml's narrow PD-rule set, which runs EVERYWHERE including
# the files excluded here; run-tests and .claude/hooks/ruff-check.sh run BOTH
# passes.  This file dies at I14 when its settings merge into pyproject.toml.
#
# select = ALL, minus the ignores below, gates every file NOT excluded.  An
# increment "un-grandfathers" a file by deleting it from exclude.  Adding an
# ignore requires a justification comment here and a LEDGER.md entry.

# Same inference rule as pyproject.toml: no target-version (PD#14 -- pinning it
# masks the 3.12-only f-string syntax detection).
extend-exclude = [
    # Grandfathered until their increment moves/cleans them:
    "psh/_legacy.py",       # the remnant; shrinks I2-I13, dies I14
    "script_context.py",    # facade; cleaned when I4 moves the hook engine
    "dns_classify.py",      # cleaned if/when moved (I14 MAY, CAMPAIGN section 3.1)
    "check/",               # cleaned as I8-I10 restructure them
    "plugin/",              # cleaned as increments touch them
    "tests/",               # cleaned per-increment alongside their code
    "development/",         # historical archive, never linted
]

[lint]
select = ["ALL"]
ignore = [
    # -- Formatter territory (no autoformatter is adopted; these fight hand style):
    "COM812",  # trailing-comma
    "ISC001",  # implicit str concat (conflicts with COM812 tooling advice)
    "E501",    # line length -- house style has long notice literals; revisit at I14
    "Q000", "Q001", "Q002", "Q003",  # quote style
    # -- Owned by pyright, not ruff:
    "ANN",     # type annotations -- pyright gates typing (pyproject [tool.pyright])
    # -- Deliberate house practice:
    "TD002", "TD003", "FIX002",  # TODOs are tracked in README/ledger, not as issues
    "EM101", "EM102",  # message-in-raise is accepted; PD#2 covers the real risk
    "TRY003",  # long exception messages in-line -- same rationale as EM
    "D",       # docstring convention undecided -- README TODO (see Task 4)
    "CPY001",  # no per-file copyright headers in this repo
]

[lint.per-file-ignores]
# (none yet -- tests/ is excluded wholesale above; when an increment
# un-grandfathers a test file, add S101 etc. HERE with justification)
```

- [ ] **Step 2: pyproject — stale comment, pyright config, test extra**

In `[tool.ruff.lint]`, replace the second/third comment lines ("NOT adopted -- it reports 55 unrelated findings" and "Broadening is deferred until after the modularization campaign; see the TODO in README.md.") with:

```toml
# NARROW BY DESIGN.  Every rule here mechanizes a standard that already exists in prose;
# nothing here is new policy.  This narrow set runs EVERYWHERE, including files the
# campaign ratchet grandfathers.  The broad best-practice set lives in ruff-broad.toml
# (campaign ratchet, CAMPAIGN.md section 13); both passes run in ./run-tests and the
# edit-time hook.  The two files merge at campaign increment I14.
```

Append `"pyright"` to the `test` extra's dependency list. Add after the ruff sections:

```toml
[tool.pyright]
# Campaign ratchet, type half (CAMPAIGN.md section 13).  Standard mode at I0 because
# psh/cli.py re-exports from the untyped legacy module; the strictness ratchets up as
# increments move typed code in (ledger tracks).  _legacy.py is grandfathered like in
# ruff-broad.toml.
include = ["psh"]
exclude = ["psh/_legacy.py"]
typeCheckingMode = "standard"
```

- [ ] **Step 3: run-tests — second ruff pass + pyright pass**

In `run-tests`, generalize the lint step. After the existing `ruff_argv()` def add:

```python
def pyright_argv():
    """How to invoke pyright here, or None.  Same fallback pattern as ruff_argv()."""
    if shutil.which("pyright"):
        return ["pyright"]
    if shutil.which("uvx"):
        return ["uvx", "pyright"]
    return None
```

In the lint section (currently one `subprocess.call([*argv, "check", ...])`), run three gates in order, each aborting on nonzero exactly like the current single call: (1) the existing narrow pass unchanged; (2) `[*argv, "check", "--config", "ruff-broad.toml", "--output-format", "concise", "."]`; (3) `[*pyright_argv()]` (project root; reads `[tool.pyright]`). Print a one-line label before each (`"Linting (ruff, narrow PD set) ..."`, `"Linting (ruff-broad.toml, campaign ratchet) ..."`, `"Type-checking (pyright, campaign ratchet) ..."`) so a failure names its gate (PD#1). If `pyright_argv()` is None, fail with an actionable message (install hint), not a skip — a gate that silently doesn't run is the failure mode CLAUDE.md's shim story warns about.

- [ ] **Step 4: `.claude/hooks/ruff-check.sh` — same two ruff passes**

Read the script first; add the second pass (`--config ruff-broad.toml`) alongside the existing one, keeping its advisory (non-blocking) character and the shared-binary-resolution comment in sync with `run-tests` (the two must agree — existing invariant, now covering both passes). Do not add pyright here (edit-time latency; the run-tests gate covers it — note this asymmetry in a comment).

- [ ] **Step 5: Red-capability demonstrations (PD#14) — run, paste, revert**

1. Append `import os  # noqa-free deliberate violation` as the last line of `psh/cli.py` → `./run-tests --fast --llm 2>&1 | head -8` must FAIL the broad pass (F401 unused import). Paste.
2. Same line appended to `psh/_legacy.py` → broad pass must stay green (grandfathered; the narrow pass ignores F401 too). Paste.
3. Append `try:\n    pass\nexcept:\n    pass` to `psh/_legacy.py` → the NARROW pass must FAIL (E722 — never grandfathered). Paste.

`git checkout -- psh/cli.py psh/_legacy.py` after each. All three outputs go into SPEC.md § ACCEPTANCE under "Task 3".

- [ ] **Step 6: Full verification**

Run: `uv pip install .[test] 2>&1 | tail -1` (brings in pyright), then `./run-tests --fast --llm 2>&1 | tail -6`.
Expected: three gate labels, then `LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0`. Paste.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(campaign-I0): install the lint/type ratchet

ruff-broad.toml (select=ALL, grandfathered exclude list) as a second ruff
pass; pyright (standard, psh/ minus _legacy) as a run-tests gate; edit hook
runs both ruff passes. Red-capability of all three gates demonstrated in
SPEC.md ACCEPTANCE.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4: Documentation — README, CLAUDE.md, CodeGraph note

**Files:** Modify: `README.md` (TO DO section), `CLAUDE.md` (Commands, Architecture symlink bullet, Testing, new campaign pointer).

- [ ] **Step 1: README TO DO edits**

In the ruff bullet: replace "it reports ~55 unrelated findings" with "45 findings measured 2026-07-17" and state the broadening is now being executed by the campaign ratchet (`ruff-broad.toml` + `[tool.pyright]`, per `development/2026-07-17-modularization-campaign/CAMPAIGN.md` §13) rather than deferred. In the pyright bullet: note the run-tests gate now exists (standard mode, `psh/` minus `_legacy.py`) and record the measured baseline number from Task 5. Add one new bullet at the TO DO top: "**Modularization campaign in progress** — see `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (architecture) and `LEDGER.md` (state); items marked (campaign) below are being absorbed by it." Add "(post-campaign — needs a deliberate golden refresh)" parenthetical to the CSV-attachment and %-cached bullets, and "(post-campaign — becomes a ~50-line check/ package)" to the environment-lock bullet (CAMPAIGN §15 dispositions). No other TODO edits.

- [ ] **Step 2: CLAUDE.md edits**

(a) In "## Commands": after the "one executable script" sentence, add that the executable is now a thin shim over the `psh` package (`psh/_legacy.py` until the campaign completes) and invocation is unchanged. (b) Rewrite the `pantheon-sitehealth-emails.py` symlink bullet: it still exists and still must not be deleted, but now exposes the 7-line shim; the program body lives in `psh/_legacy.py`, which CodeGraph/pyright/ruff index natively as a normal `.py` file. (c) In "## Testing", first bullet: the script is imported as `psh._legacy` via a normal import (repo root on `sys.path` from `python -m pytest`); `SourceFileLoader` remains only in `tests/helpers/checkload.py` for check packages. (d) Update the "run-tests lints before it tests" paragraph: three gates (narrow ruff everywhere / broad ruff on un-grandfathered files via `ruff-broad.toml` / pyright on `psh/`), edit hook runs both ruff passes. (e) Add a short "## Modularization campaign (in progress)" section after "## Architecture" heading's intro pointing at CAMPAIGN.md/LEDGER.md/BLOCKMAP.md and stating the increment-session reading rule. Keep each edit minimal — CLAUDE.md is rewritten wholesale at I14, not now.

- [ ] **Step 3: Verify the CodeGraph claim before writing it**

Run `codegraph explore "psh/_legacy.py main"` (shell form). If the index now reports symbols/covering-tests for `psh/_legacy.py`, update CLAUDE.md's known-limitation sentence ("tests import the program via SourceFileLoader on the dash name, so CodeGraph cannot link tests") to what is actually observed; if the index hasn't caught up (~1s watcher lag, or needs reindex), leave the limitation text but change the file name it cites. Write only what was observed (SPEC T6).

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(campaign-I0): update README TODO and CLAUDE.md for the psh layout

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 5: pyright baseline, ledger, acceptance, commit

**Files:** Modify: `development/2026-07-17-modularization-campaign/LEDGER.md`, `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (two amendments), `development/2026-07-17-mod-I0-bootstrap/SPEC.md` (ACCEPTANCE), `README.md` (pyright number from Step 1).

- [ ] **Step 1: Measure the whole-tree pyright baseline (informational, not the gate)**

Run: `uvx pyright --outputjson --project /dev/null . 2>/dev/null | tail -4` — if `--project /dev/null` errors, run `uvx pyright .` from a temp dir config-free equivalent; the goal is a whole-tree error count ignoring the scoped `[tool.pyright]`. Simplest reliable form: `cd /workspace && uvx pyright --ignoreexternal . 2>&1 | tail -3` — if flags fight, fall back to a scratch `pyrightconfig.json` in `/tmp/claude-501/-workspace/8e027ab4-f2e6-4cc5-8533-5476c106edfb/scratchpad` listing `include: ["/workspace"]`. Record the summary line (`X errors, Y warnings`) in the ledger and README (replacing the unverified "39"). Exact flags are the implementer's to settle; the deliverable is a reproducible command + count, pasted.

- [ ] **Step 2: CAMPAIGN.md amendments (SPEC § amendments, verbatim)**

In §11 row I0, change "pyproject console-script + thin shim" → "thin shim (console-script dropped — see LEDGER I0 amendment)". In §13, change the grandfather file name `pantheon-sitehealth-emails.py` → `psh/_legacy.py` (and "per-file-ignores" → "ruff-broad.toml exclude", matching the shipped mechanism). In §12, change "one commit (code + dev folder)" → "per-task commits, each green; the increment's final commit includes the dev folder" (third amendment).

- [ ] **Step 3: Ledger entry**

Append to LEDGER.md using the §12 template: moved (whole file → `psh/_legacy.py`; no logic), deviations (the two amendments + ruff two-config mechanism + pyright standard-not-strict with rationale), contract/config/sc additions (none), discovered tasks (any), open questions for I1/I2. Include the pyright baseline and the ruff ignore list as pinned.

- [ ] **Step 4: Final gate + single commit**

Run: `./run-tests --llm 2>&1 | tail -6` (full; if the live tier lacks credentials in this environment, rerun `--fast` and add the §16 ledger note). Expected: all gates green, goldens byte-identical. Then the closing commit:

```bash
git add -A
git commit -m "docs(campaign-I0): close the bootstrap increment

pyright baseline measured and recorded; CAMPAIGN.md amendments (no
console-script; grandfather is psh/_legacy.py; per-task commits); ledger
entry appended; SPEC acceptance outputs pasted.

Campaign: development/2026-07-17-modularization-campaign/CAMPAIGN.md (I0).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (spec coverage)

SPEC T1→Task 2, T2→Task 2, T3→Task 2, T4→Task 2 Step 3, T5→Task 3, T6→Task 4, T7→Task 5; amendments→Task 5 Step 2; acceptance→Tasks 1/2/3/5. NOT-in-I0 list respected: no `_legacy` edits (red-capability appends are reverted), no `[Check.*]`, no finding fixes. Type consistency: `psh.cli.main`/`parse_args` names match shim, cli.py, and conftest usage throughout.
