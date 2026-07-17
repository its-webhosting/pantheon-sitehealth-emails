# I0 — Campaign bootstrap (increment spec)

Campaign: `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (cited by §
below; this spec re-derives nothing). Blocks moved: **none** — I0 moves the *file*, not
logic (§11 row I0). Behavior bar §8 and invariants §9 apply in full: goldens
byte-identical, artifact structure unchanged, every existing config key and CLI behavior
unchanged.

## Assumptions (stated per Karpathy #1; each verified 2026-07-17)

- The script's only entry tail is `if __name__ == "__main__": sc.options = parse_args(); main()` (verified, file tail).
- Exactly one `SourceFileLoader` call site loads the program: `tests/conftest.py:87` (verified by grep; `checkload.py` loads check packages, not the program).
- `run_program()` executes the program by absolute path with `cwd=` a temp workdir, so the subprocess's `sys.path[0]` is the repo root and `import psh` resolves there — the same mechanism that already resolves `import script_context` (verified: `PROGRAM = REPO_ROOT / "pantheon-sitehealth-emails"`).
- Today's `pip install .` is deps-only (`py-modules = []`, verified in pyproject.toml); nothing imports the program as an installed distribution.
- Baselines (§13): fast tier 727 passed / 1 skipped / 2 deselected; ruff `--isolated` 45 findings; pyright unmeasured.

## Campaign amendments this spec makes (ledgered on I0 completion)

1. **No console-script entry point** (amends §11 I0 / D10 wording). The program is
   repo-rooted by design: `find_modules`, templates, `inline-styles.php`, `vendor/`,
   and the config symlink are all CWD-relative. A pip-installed entry point would
   require a data-file overhaul that serves no campaign goal. D10's actual benefits
   (normal imports, native ruff/pyright/CodeGraph coverage, no SourceFileLoader) all
   arrive via the package + shim without installation.
2. **The ratchet's grandfathered file is `psh/_legacy.py`** (amends §13, which named
   `pantheon-sitehealth-emails.py` — written before the legacy-module mechanics were
   settled).

## Design

### T1 — the package and the legacy module

`git mv pantheon-sitehealth-emails psh/_legacy.py` with **zero content changes** (the
`__main__` tail becomes inert in a module; leave it — deleting it is I13's business).
New files, each minimal (Karpathy #2):

- `psh/__init__.py` — docstring only (what the package is, pointer to CAMPAIGN.md).
- `psh/cli.py` — `from psh._legacy import main, parse_args` plus `__all__`; the
  orchestrator's future home, today a re-export.

`[tool.setuptools]` additionally gains `packages = []`: with a `psh/` directory present,
setuptools auto-discovery would otherwise start installing it into site-packages, and a
stale installed copy shadowing the repo copy is a silent-failure hazard (PD#1). The
install stays deps-only, matching the no-console-script amendment.

`script_context.py` and `dns_classify.py` stay top-level (§3.1).

### T2 — the shim

`./pantheon-sitehealth-emails` (new content, same path/mode/shebang; committed):

```python
#!/usr/bin/env python
"""Thin launcher for psh.cli.main() — see development/2026-07-17-modularization-campaign/CAMPAIGN.md."""
import script_context as sc
from psh.cli import main, parse_args

if __name__ == "__main__":
    sc.options = parse_args()
    main()
```

The `pantheon-sitehealth-emails.py` symlink stays (it now exposes the shim; the reasons
in CLAUDE.md still hold for the shim file itself; re-evaluated at §17 Q5).

### T3 — conftest rework

Replace the `SourceFileLoader` block with `importlib.import_module("psh._legacy")`
inside the existing load-once helper. No `sys.path` work is needed or wanted:
`./run-tests` executes `python -m pytest` with `cwd` = repo root, which puts the repo
root on `sys.path` — the exact mechanism that already resolves `import script_context`
today (verified; bare `pytest` fails collection today for the same reason and that
behavior stays as-is). The loader's `"psh_main"` module name is referenced nowhere else
(verified by grep).
Fixture name `psh` and all downstream uses unchanged. The docstring's loader rationale
is rewritten to match. Nothing else in conftest changes (Karpathy #3): `PROGRAM`,
`_CWD_ASSETS`, `run_program`, interlocks all stay — except `_CWD_ASSETS` MUST gain
`psh` **only if** the workdir run proves to need it (assumption says no; the goldens
decide).

**Amendment (found during implementation):** the "one SourceFileLoader call site"
assumption was true but incomplete — 25 sites across 23 test files (plus
`tests/helpers/checkload.py`) anchor repo paths on `Path(psh.__file__).parent`, which
the move changes from repo root to `psh/`. Authorized fix, mechanical and minimal:
`Path(psh.__file__).parent` → `Path(psh.__file__).resolve().parents[1]` at exactly
those sites, nothing else. These call sites get properly cleaned when their increments
un-grandfather the test files (and the `psh` fixture itself is redesigned when
`_legacy` dies at I14) — ledgered as a discovered task.

**Gate:** `pytest --collect-only -q` totals identical before/after the rework, and the
fast tier reproduces exactly `727 passed, 1 skipped, 2 deselected`.

### T4 — coverage config

`[tool.coverage.run] include` becomes `["*/psh/*", "*/script_context.py", "*/dns_classify.py"]`
— the current glob matches a file that will no longer contain code. (Adding the two
top-level modules corrects a pre-existing blind spot; they are program code. If the
measured coverage command errors on the new include, fix forward — do not ship a config
that silently measures nothing: PD#14.)

### T5 — the ratchet (requirements; exact TOML shape resolved in the plan against ruff's documented capabilities)

- **R1** The four PD rules (`E722`, `BLE001`, `S105`, `S106`) remain global — every
  file including `psh/_legacy.py`, no exception, as today (§13).
- **R2** The broad rule set is ruff `select = ["ALL"]` with an explicit global `ignore`
  list, each entry justified in a comment (illustrative candidates, finalized in the
  plan: formatter-territory `COM`/`Q`/`E501`/`ISC001`, `ANN` where pyright owns it, `D`
  pydocstyle pending a docstring-convention decision — if deferred, README TODO it).
  It gates everything **except** `psh/_legacy.py`, which is grandfathered for all rules
  outside R1. `tests/` keeps its existing S105/S106 carve-out and MAY gain
  test-appropriate ignores (e.g. `S101`), each justified.
- **R3** pyright enters `./run-tests` as a gate: strict-leaning for `psh/` excluding
  `_legacy.py`; `_legacy.py` and not-yet-moved code excluded/basic. Binary via the
  `pyright` pip package (add to the `test` extra). Baseline over the whole tree
  measured and recorded in the ledger (replacing README's unverified "39").
- **R4** `.claude/hooks/ruff-check.sh` and `run-tests` keep reading the same config
  with no `--select` (existing invariant); if two config files prove necessary for the
  except-grandfather semantics, each carries a comment naming the other and `run-tests`
  runs both (PD#1 — a config that silently doesn't run is the failure mode to design
  out).
- **Red-capability** (PD#14, acceptance below): a deliberate violation of a broad rule
  in `psh/cli.py` must fail `run-tests`; the same violation in `psh/_legacy.py` must
  not; an `E722` in `psh/_legacy.py` must fail. All three demonstrated and pasted, then
  reverted.

### T6 — docs

- README: replace the stale ruff-TODO figures with measured ones; mark the
  ruff/pyright-broadening TODO as being executed by the campaign ratchet (pointer to
  CAMPAIGN.md §13); add the campaign pointer to the TODO intro. No other TODO edits —
  §15 dispositions left every other item in place.
- CLAUDE.md: update **Commands** (unchanged invocation, new layout note), the
  **symlink** bullet (points at the shim now; program code lives in `psh/_legacy.py`,
  which CodeGraph/ruff/pyright index natively), **Testing** (conftest imports
  `psh._legacy`; SourceFileLoader gone from conftest — `checkload.py` still uses it for
  check packages), and add a short **Modularization campaign** section pointing at
  CAMPAIGN.md/LEDGER.md. Verify-then-update the "no covering tests found" CodeGraph
  limitation note: after T3 the tests import a real module name, so the limitation may
  have dissolved — check `codegraph_explore` output for a `psh/_legacy.py` symbol and
  write what is actually observed (PD: verify, don't assume).

### T7 — ledger

Append the I0 entry (template §12) including the two amendments above, the pyright
baseline, and the ruff-ignore list as pinned.

## NOT in I0 (exhaustive)

Any logic move (I2+); deleting the `__main__` tail from `_legacy` (I13); fixing any of
the 45 default-set findings in `_legacy` (they retire as code moves); `[Check.*]`
config sections (I8+); memory updates beyond the ledger unless a durable fact changes.

## Seams and tests

No runtime seams change — the program's I/O surface is untouched. The test cover for
I0 **is the existing suite plus the goldens**: T1–T3 are proven by the collect-count
gate and `727 passed, 1 skipped, 2 deselected` reproduced; the shim is proven by the
e2e tier (it subprocess-launches the real program through the new entry path); the
ratchet by the red-capability demonstrations. New permanent tests: none — a test that
"the lint config is loaded" would duplicate the run-tests gate itself (Karpathy #2; the
gate is already red-capable by R-demonstrations). This "no new permanent tests" call is
explicit spec content per the Spine's seam rule: the highest existing seam (the full
suite + goldens) reaches every behavior I0 touches.

## Acceptance criteria (run and pasted into this file's ACCEPTANCE section by the implementer)

```bash
# 1. Identical collection (before-count captured pre-change, after-count post-change;
#    python -m form is required -- bare `pytest` cannot collect, before or after):
.venv/bin/python -m pytest --collect-only -q | tail -2
# 2. Fast tier byte-for-byte on the baseline numbers:
./run-tests --fast --llm   # expect: LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 ...
# 3. Full tier incl. e2e goldens through the shim (live tier per §16 availability rule):
./run-tests --llm
# 4. The program still runs as an operator runs it:
./pantheon-sitehealth-emails --help   # expect: usage text, exit 0
# 5. Ratchet red-capability: three demonstrations per T5, output pasted, then reverted.
# 6. pyright baseline: command + count pasted; ledger updated.
```

## ACCEPTANCE

### Baseline (Task 1, run 2026-07-17 at 2d742d1)

```
$ .venv/bin/python -m pytest -p no:cacheprovider --collect-only -q | tail -2
730 tests collected in 0.52s

$ ./run-tests --fast --llm   (tail)
25 snapshots passed.
727 passed, 1 skipped, 2 deselected in 27.99s
```

### Task 2 (package move / shim / conftest / coverage, run 2026-07-17)

```
$ .venv/bin/python -m pytest -p no:cacheprovider --collect-only -q | tail -2
730 tests collected in 0.65s

$ ./run-tests --fast --llm   (tail)
LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
--------------------------- snapshot report summary ----------------------------
25 snapshots passed.
727 passed, 1 skipped, 2 deselected in 25.35s

$ ./pantheon-sitehealth-emails --help ; echo "exit=$?"
usage: pantheon-sitehealth-emails [-h] [--all] [--resume-from SITE_NAME]
                                  [--date DATE] [--update] [--for-real]
                                  [--config CONFIG] [--only-warn]
...
exit=0
```

### Task 3 (lint/type ratchet: ruff-broad.toml + pyright + run-tests + edit hook, run 2026-07-17)

**Settled details (T5, decided empirically against ruff 0.15.22 / pyright 1.1.411):**

1. *CPY001* is recognized by ruff 0.15.22 but is a **preview** rule ("This rule is in
   preview... The `--preview` flag is required for use"), so it cannot fire under our
   non-preview `select=["ALL"]`. Ruff accepts it in `ignore` with **no warning or error**
   (`ruff check --config ruff-broad.toml psh/` emitted no selector warnings). The intent
   (no per-file copyright headers, documented + suppressed) holds, so the line is **kept
   verbatim** — no adjustment needed. Every other ignore code (COM812, ISC001, E501,
   Q000–Q003, ANN, TD002/TD003, FIX002, EM101/EM102, TRY003, D) is a stable, recognized
   rule/prefix.
2. `psh/cli.py`, `psh/__init__.py`, and the shim **pass the broad pass out of the box**
   (`All checks passed!`, exit 0) — no INP001 on the shim (repo root is a project root and
   `psh/` is a proper package), no D-rule interplay (D is ignored). No fixes or ignores
   were added to the new files.

**Demo 1 — unused import in `psh/cli.py` → broad pass FAILS (F401):**

```
$ printf '\nimport os  # noqa-free deliberate violation\n' >> psh/cli.py
$ ./run-tests --fast --llm 2>&1 | head -8
warning: Invalid `# noqa` directive on psh/cli.py:11: expected `:` followed by a comma-separated list of codes (e.g., `# noqa: F401, F841`).
All checks passed!
warning: Invalid `# noqa` directive on psh/cli.py:11: expected `:` followed by a comma-separated list of codes (e.g., `# noqa: F401, F841`).
psh/cli.py:11:8: F401 [*] `os` imported but unused
Found 1 error.
[*] 1 fixable with the `--fix` option.

Broad lint gate FAILED (ruff-broad.toml, campaign ratchet) -- fix the findings
```
(Narrow pass "All checks passed!"; broad pass then reports F401 and aborts before pytest.
The cosmetic "Invalid `# noqa` directive" warning is from the brief's verbatim comment
text containing the substring "noqa"; it does not affect the F401 finding.)

**Demo 2 — same unused import in `psh/_legacy.py` → broad pass stays GREEN (grandfathered):**

```
$ printf '\nimport os  # noqa-free deliberate violation\n' >> psh/_legacy.py
$ ./run-tests --fast --llm 2>&1 | head -8
warning: Invalid `# noqa` directive on psh/_legacy.py:4754: expected `:` followed by a comma-separated list of codes (e.g., `# noqa: F401, F841`).
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
...............................s........................................ [  9%]
........................................................................ [ 19%]
........................................................................ [ 29%]
........................................................................ [ 39%]
```
(Both ruff passes "All checks passed!" — the broad pass excludes `_legacy.py`, the narrow
pass ignores F401 — pyright "0 errors", and pytest proceeds. F401 in the grandfathered
file did not fail any gate.)

**Demo 3 — bare `except` in `psh/_legacy.py` → NARROW pass FAILS (E722, never grandfathered):**

```
$ printf '\ntry:\n    pass\nexcept:\n    pass\n' >> psh/_legacy.py
$ ./run-tests --fast --llm 2>&1 | head -8
psh/_legacy.py:4756:1: E722 Do not use bare `except`
Found 1 error.

Lint gate FAILED -- fix the findings above, or add a noqa WITH AN INLINE
REASON if the code is deliberate (a bare noqa is a silent failure).
These rules mechanize prompts/directives.md PD#2 and PD#6; they are not style.
Linting (ruff, narrow PD set) ...
```
(The narrow PD set gates `_legacy.py` too — E722 fires and aborts before the broad/pyright
passes. After each demo: `git checkout -- psh/cli.py psh/_legacy.py`; `git diff psh/`
empty, confirming `_legacy.py` untouched.)

**Extra red-capability (HARD RULE / PD#14) — missing pyright FAILS, never silently skips:**

```
$ python scratchpad/pyright_missing_demo.py   # ruff mocked present, pyright+uvx absent
ERROR: neither `pyright` nor `uvx` is on PATH, so the type gate cannot run.
       The suite is NOT green without it -- it is unverified.
       Install it via `uv pip install .[test]` (adds pyright) or `pip install pyright`.
...
run_gates() returned: 1  (expect 1 -- FAIL, not a skip)
PASS: missing pyright fails loudly with an actionable message.
```

**Step 6 — full verification (install brings in pyright; three gates then green fast tier):**

```
$ uv pip install .[test] 2>&1 | tail -1
 ~ pantheon-sitehealth-emails==0.2.0 (from file:///workspace)

$ ./run-tests --fast --llm 2>&1 | tail -6
25 snapshots passed.
727 passed, 1 skipped, 2 deselected in 26.80s
Linting (ruff, narrow PD set) ...
Linting (ruff-broad.toml, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...

$ ./run-tests --fast --llm   # LLM_SUMMARY line:
LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
```

**pyright baseline (over the gated scope `psh/` minus `_legacy.py`):** `0 errors, 0
warnings, 0 informations` (`uvx pyright`, reading `[tool.pyright]`). Whole-tree baseline
for the ledger is Task 5's line item.

