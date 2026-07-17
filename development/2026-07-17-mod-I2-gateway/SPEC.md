# I2 — Gateway extraction (`psh/gateway.py`)

**Increment I2 of the modularization campaign.** Governing documents (read in full before
implementing, CAMPAIGN.md §7.1): `../2026-07-17-modularization-campaign/CAMPAIGN.md`,
`../2026-07-17-modularization-campaign/LEDGER.md`,
`../2026-07-17-modularization-campaign/BLOCKMAP.md`, `/workspace/CLAUDE.md`. This spec cites
CAMPAIGN.md by section number and re-derives nothing from it.

## Glossary (this increment)

- **Gateway** — `psh/gateway.py`, the new module through which every Terminus/WP-CLI/Drush
  subprocess flows (CAMPAIGN.md §Glossary; the future Pantheon-API transport seam, D1).
- **Wrapper** — one of the eleven Terminus/WP/Drush subprocess-facing defs listed in §Scope.
- **`GatewayResult`** — the NamedTuple `(result, errors, fatal)` introduced here (CAMPAIGN.md §6),
  the typed replacement for the wrappers' anonymous 3-tuple returns.
- **Canonical seam** — `psh.gateway.run_terminus`, the single in-process monkeypatch point for
  everything routed through the wrappers after this move (§Seams).
- **Remnant** — `psh/_legacy.py`, whatever of the original program has not yet moved.
- **Façade** — `script_context.py` (`sc`), the stable import surface for `check/`/`plugin/`
  packages (CAMPAIGN.md §3.5).

MUST / NEVER / SHOULD / MAY per CAMPAIGN.md §Glossary.

## Scope (exhaustive)

I2 moves exactly these eleven module-level defs from `psh/_legacy.py` to a new `psh/gateway.py`
(CAMPAIGN.md §3.1 gateway row is authoritative; the "302–597" line span in §11 row I2 is the
baseline region, and its first def `escape_url` is **NOT** in scope — §3.1 assigns `escape_url`
to `psh/render.py`, I12):

| Def | Current `_legacy` line | Notes |
|---|---|---|
| `run_terminus` | 306 | the only `subprocess.Popen` of a terminus command |
| `TerminusError` | 396 | exception class |
| `terminus` | 411 | session-expiry retry; self-recursive |
| `terminus_data` | 448 | raises `TerminusError` |
| `wp` | 463 | |
| `wp_eval` | 479 | |
| `wp_error` | 490 | contains a **column-0** `f"""` notice literal — Invariant 8 |
| `fix_drush_output` | 516 | returns a 2-tuple |
| `drush` | 538 | |
| `drush_php_script` | 555 | |
| `drush_error` | 572 | contains a **column-0** `f"""` notice literal — Invariant 8 |

**Also delivered** (CAMPAIGN.md §11 row I2): the `GatewayResult` type (§6); the
no-subprocess-outside-gateway house rule and the `sc`-façade-names assertion (§3.5), both as
tests; `sc` re-exports verified intact.

**Explicitly out of scope:** `escape_url` (I12); the `subprocess.run` PHP-inliner call in `_legacy`
B54 (I12, `psh/render.py`) — it is not a Terminus/WP/Drush spawn and stays; every other block.

## Why a gateway now (CAMPAIGN.md D1)

The Pantheon-API transport swap is deferred to post-campaign, but the **seam** is built now so
that swap is a one-module change instead of a scattered edit. Consolidating the eleven wrappers
into one importable, typed, gated module is that seam, and is the first real logic move of the
campaign (LEDGER.md I0 open-question for I2).

## Move mechanics

### The import-back strategy (keeps the remnant working, one seam for tests)

`psh/gateway.py` holds the eleven defs with their **logic and the two column-0 `f"""` notice
literals preserved byte-for-byte**; the only edits are (a) return statements wrapped in
`GatewayResult(...)`, (b) house-style tuple-hint annotations replaced with real annotations, and
(c) the enumerated broad-ruff fixes/suppressions of §Broad-ruff findings. "Verbatim" below means
that byte-preserved core, not a literally-unedited file. `psh/_legacy.py` re-imports the defs so
its ~54 existing call sites and the `sc`-exposure block keep resolving unchanged:

```python
# psh/_legacy.py, replacing the removed defs:
from psh.gateway import (
    GatewayResult,
    TerminusError,
    drush,
    drush_error,
    drush_php_script,
    fix_drush_output,
    run_terminus,
    terminus,
    terminus_data,
    wp,
    wp_error,
    wp_eval,
)
```

`psh/gateway.py`'s own import block (the moved bodies require exactly these):

```python
import html
import json
import re
import subprocess
import time
from typing import Any, NamedTuple

from rich.markup import escape

import script_context as sc
```

Consequences, all verified:

- `psh._legacy.terminus` / `psh._legacy.run_terminus` / `psh._legacy.TerminusError` /
  `psh._legacy.GatewayResult` etc. still exist (bound to the gateway objects), so `psh.<name>`
  through the test `psh` fixture keeps resolving. `sc.terminus = terminus` (`_legacy` line 1643)
  still assigns the gateway function, so `reset_sc.terminus is psh.terminus` stays true
  (`test_terminus_contract.py::test_check_helpers_are_exposed_on_sc`).
- **No `_legacy` imports are orphaned by the move.** Every import the moved code used has other
  live users in `_legacy`: `html` (plugin/module notice bodies, ~9 sites), `time` (`time.sleep`
  at db-retry line 1373), `escape` (50 call sites), `Any` (`process_config`), `subprocess`
  (PHP inliner), `json`/`re`/`NamedTuple`. Verified by grep; the implementer re-verifies and
  removes only what its change actually orphans (there should be none).

### `GatewayResult` (CAMPAIGN.md §6)

```python
class GatewayResult(NamedTuple):
    result: Any
    errors: str
    fatal: bool
```

Applied as the return annotation and constructed at each return of the 3-tuple wrappers:
`run_terminus`, `terminus`, `wp`, `wp_eval`, `drush`, `drush_php_script`. `fix_drush_output`
keeps its 2-tuple, annotated `-> tuple[str, str]`. `terminus_data` returns just the result,
annotated `-> Any`. `wp_error`/`drush_error` return `-> list[dict[str, str]]`. This discharges
CAMPAIGN.md §6's house-style-tuple-hint replacement for every moved def in one pass (D2 — cleaned
as it moves, never fixed in place in the remnant).

`GatewayResult` is a `tuple` subclass, so every positional unpack (`result, errors, fatal = …`)
and every `== (a, b, c)` comparison in call sites and tests is unchanged — behavior-preserving,
no golden impact (the return type is invisible to rendered output). The first element of
`run_terminus`/`wp_eval` is textual output; the generic field name `result` covers it and no
caller reads the fields by name, so this is a naming nicety only.

`GatewayResult` is **not** added to `sc`: no `check`/`plugin` consumer references the type name
(they unpack positionally), so adding it would be dead façade surface (CAMPAIGN.md §17 Q4).

### Broad-ruff findings on the moved code (decided here, not left to the implementer)

Under `ruff-broad.toml` (`select = ["ALL"]`), the moved code trips seven findings beyond the
tuple-hint replacement. They are enumerated with a **decided** disposition so a fresh-context
implementer never has to choose (CAMPAIGN.md §Spec quality bar: the spec is the only place a
decision can be agreed). None of these dispositions changes `ruff-broad.toml`'s frozen ignore
list (that would be a §13 amendment) — all are inline, per-line `# noqa` or behavior-preserving
edits.

| Rule | Where | Disposition |
|---|---|---|
| `F541` ×2 | `wp_error`/`drush_error` `"short": f"fix WP CLI error"` / `f"fix drush error"` | **Fix**: drop the `f` prefix. Placeholder-less f-string → identical `str`; not in a fragile path. |
| `E713` | `run_terminus` stderr-filter loop (`not "…read-only Git mode" in line`) | **Fix**: `"…read-only Git mode" not in line`. One-operator swap, provably identical, outside the escaping/exit-code logic. |
| `PLW2901` | `run_terminus` same loop (`line = line.strip()` shadows the loop var) | **Fix**: iterate `for raw_line in lines: line = raw_line.strip()` (keep `line` as the working name so the conditions/append are unchanged). Behavior-preserving. |
| `C901` | `run_terminus` (complexity 12 > 10) | **`# noqa: C901`** on the `def`. "Fixing" it means restructuring `run_terminus`, whose stderr/markup escaping is under-tested (only `test_run_terminus_markup.py` + the goldens cover it, and CLAUDE.md records it shipped as a bug twice). Refactoring is a review activity, not part of a behavior-preserving move (`prompts/implementation-standards.md` § Test discipline). |
| `PLR0912` | `run_terminus` (branches 13 > 12) | **`# noqa: PLR0912`** on the `def`, same rationale as `C901`. |
| `S603` | `run_terminus` `subprocess.Popen(command, …)` | **`# noqa: S603`** with an inline reason: `command` is a fixed `["terminus", …]` argv (no shell, no untrusted-input execution path); the spawn is the gateway's entire purpose. |

So `run_terminus`'s **body logic** is moved unchanged except the two cosmetic loop fixes (`E713`,
`PLW2901`), which touch only the benign-warning stderr filter — not the escaping, the returncode
handling, or the `wp`/`composer` output filter. The three suppressions carry inline reasons (a
bare `# noqa` is itself a silent failure — PD#1 / `prompts/implementation-standards.md` §1). With
these applied, acceptance criterion #3 (`ruff check --config ruff-broad.toml psh/gateway.py` →
"All checks passed!", pyright 0 errors) is reachable; the implementer MUST paste it.

### Column-0 literal invariant (Invariant 8)

`wp_error` and `drush_error` each contain a multi-line `f"""..."""` whose continuation lines
begin at **column 0**. They are module-level defs today and stay module-level defs in
`gateway.py` — identical nesting, so the interior bytes must be unchanged. The implementer MUST
move these literals **verbatim** and MUST NOT re-indent them; `git diff -w` is not acceptable
evidence (CAMPAIGN.md Invariant 8).

**The goldens are NOT a tripwire here.** No golden renders either notice — `wp_error`/`drush_error`
fire only on a WP/Drush *command failure*, which the offline fixtures never produce
(`grep -rc 'START WP CLI ERROR\|START DRUSH ERROR' tests/e2e/__snapshots__/*.ambr` → all zero).
The existing `test_wp_error_shape`/`test_drush_error_shape` assert with substring `in`, which
survives added leading whitespace, so they are not a tripwire either. The **sole** real
instrument is therefore mandatory and primary: extract the two `f"""…"""` bodies from the pre-move
source (`git show <I1-closing-sha>:psh/_legacy.py`) and from `psh/gateway.py`, and assert them
**byte-identical** (a `diff` of the extracted blocks is empty). The task report pastes that diff.

## Seams (declared before implementation — CAMPAIGN.md §Spec quality bar)

The canonical in-process seam for anything routed through the wrappers becomes
**`psh.gateway.run_terminus`**. Reason: after the move, `terminus`/`wp`/`drush` resolve
`run_terminus` in the **gateway** module's namespace, not `_legacy`'s. Patching
`psh._legacy.run_terminus` (i.e. `setattr(psh, "run_terminus", …)`) would rebind only the
remnant's name and the wrappers would call the real subprocess — a silent test defect (PD#14).

A conftest fixture provides the handle:

```python
@pytest.fixture
def gateway(psh):
    """The psh.gateway module (psh._legacy has already imported it)."""
    import psh.gateway
    return psh.gateway
```

**What must repoint (function-attribute patches):** only the four files whose tests patch
`run_terminus` **and then call a wrapper** — the patch target changes from `psh` to `gateway`:

| File | Lines patching `run_terminus` |
|---|---|
| `tests/integration/test_terminus_contract.py` | 21, 29, 38, 44, 49, 57, 67, 82 |
| `tests/integration/test_wrappers.py` | 23, 31, 38, 46, 54, 62 |
| `tests/integration/test_terminus_seam.py` | 15, 26 |
| `tests/integration/test_regressions.py` | 31, 48 |

**What must NOT repoint (module-singleton patches — verified they keep working):**

- `setattr(psh.time, "sleep", …)` and `setattr(psh.subprocess, "Popen", …)` mutate the shared
  `time` / `subprocess` **module** objects, which gateway and `_legacy` both `import`. Gateway's
  `time.sleep(5)` / `subprocess.Popen(…)` resolve the attribute on the same module at call time,
  so the patch applies without repointing. This covers `test_run_terminus_markup.py`
  (`psh.subprocess.Popen`, calls `psh.run_terminus` directly — no change), the `psh.time.sleep`
  lines in `test_terminus_contract.py`/`test_regressions.py`, and every `psh.time.sleep` in the
  DB suites (`test_db_resilience.py`, `test_traffic_table_rows.py`, `test_db_credentials.py`),
  whose sleeps are in `db_retry` code that stays in `_legacy` (I5). Leave all of these unchanged —
  touching them would be unrequested scope.

`tests/README.md:63` documents the seam as `monkeypatch.setattr(psh, "run_terminus", fake)`;
update it to the `gateway` seam.

**One non-wrapper direct caller keeps a different seam (latent-trap note for later increments).**
`psh/_legacy.py:3403` (the Drupal composer dry-run, B35/B39) calls `run_terminus(command)`
directly, not through a wrapper. After the import-back, that name resolves to `_legacy`'s imported
binding, so its in-process patch point stays `psh.run_terminus` (i.e. `setattr(psh, …)`), **not**
`gateway.run_terminus` — patching the gateway binding would not intercept it (separate name
bindings to the same function object). No current test drives line 3403 via monkeypatch (it is
exercised only by the e2e PATH-shim `terminus`), so nothing breaks in I2; this is a note so the
author who relocates B39 (I8/I9) does not assume the gateway seam reaches it. It is shown as the
dashed edge in the diagram below.

### Diagram — where the wrapper seam lives after I2 (non-local; PD#8)

```
 check/plugin packages ──sc.terminus──►┐
                                        │
 psh/_legacy.py wrapper call sites ─────┤ (imported names bound to gateway objects)
   (B6,B14,B17,B21,B22,B29,B35,B38,B49) │
                                        ▼
                         psh/gateway.py: terminus / wp / drush / …
                                        │  (resolve run_terminus in THIS namespace)
                                        ▼
                         psh/gateway.py: run_terminus ──► subprocess.Popen(["terminus", …])
                                        ▲
                    tests ── monkeypatch.setattr(gateway, "run_terminus", fake) ─┘

 psh/_legacy.py:3403 (composer dry-run) ┈┈► run_terminus  [resolves _legacy's binding;
                                             seam stays psh.run_terminus until B39 relocates]
```

## New tests (instruments — CAMPAIGN.md §7, PD#14)

Three new assertions. Each names its red demonstration, per the `test_house_rules.py` convention
(an instrument that cannot be shown to go red is not evidence).

1. **`GatewayResult` return type** (test-first, honest red→green; add to
   `tests/integration/test_terminus_contract.py`). `run_terminus` and `terminus` each return a
   `GatewayResult` with `.result`/`.errors`/`.fatal`. RED before the type exists:
   `psh.GatewayResult` raises `AttributeError`. GREEN after. Uses the `gateway` seam for the
   `terminus` case; a `subprocess.Popen` fake for the `run_terminus` case (mirroring
   `test_run_terminus_markup.py`).

2. **No subprocess spawn outside the gateway** (`tests/unit/test_house_rules.py`). Among feature
   code, `subprocess.Popen(` appears only in `psh/gateway.py`. Mechanizes CLAUDE.md's
   "Never shell out to terminus/wp/drush directly": `run_terminus` is the only terminus spawner
   and `subprocess.Popen` is how it spawns; the PHP inliner uses `subprocess.run` and is not a
   terminus/wp/drush call, so it is correctly not matched. Scope
   `("check", "plugin", "dns_classify.py", "script_context.py", "psh")`, allowlist
   `{"psh/gateway.py"}`, same nil-guard shape as the existing tests. **RED demonstration
   (required, then revert):** this test is authored in Task 2, *after* Task 1 has already moved
   `subprocess.Popen` into `gateway.py`, so the pre-move natural-red state no longer exists at
   authoring time. Demonstrate red the way instrument #3 does — by *temporary reintroduction*:
   add a throwaway `subprocess.Popen(` line to a scoped file (e.g. `script_context.py`), observe
   the test fail naming that file, then revert. The task report pastes that red output.
   (Alternatively the implementer MAY author this test at the very start of Task 1, before
   creating `gateway.py`, and capture the genuine pre-move red listing `psh/_legacy.py`; either
   is acceptable, but silence is not — PD#14.)

3. **Documented `sc` façade names exist** (`tests/unit/test_house_rules.py`). Pins CAMPAIGN.md
   Invariant 9 / §3.5 ("sc names never removed mid-campaign"). Asserts every name in CLAUDE.md's
   runtime-exposed block is present on the loaded `sc`:
   `("escape_url", "check_wordpress_plugin", "check_drupal_module", "umich_enabled",
   "cloudflare_enabled", "terminus", "fqdn_re", "db_engine_args")`. This is a **pinning**
   test (it passes when written, like the two existing house rules); its red state is
   demonstrated by temporarily removing an `sc.<name>` assignment and observed in the docstring,
   then reverted — the carve-out the existing house-rules file already documents for itself.

## Ratchet (CAMPAIGN.md §13)

`psh/gateway.py` is a **new** file and therefore **not** in `ruff-broad.toml`'s `extend-exclude`
(only `psh/_legacy.py` and the other named remnants are). It is gated by the broad ruff set and
pyright standard mode (`[tool.pyright]` `include = ["psh"]`, `exclude = ["psh/_legacy.py"]`) from
birth. Nothing is deleted from `extend-exclude` this increment — the "un-grandfather the wrapper
functions" note in LEDGER.md I0 assumed the functions would stay in an excluded file; because
they move to a fresh file the exclude list is untouched and the cleaning obligation is discharged
by gateway.py being born under the full gate. `psh/gateway.py` MUST pass the broad ruff set and
pyright standard with zero findings (§7 obligation 3, D2). Record this reasoning in the ledger.

## Behavior bar & invariants preserved (CAMPAIGN.md §8, §9)

- Four e2e goldens byte-identical (Invariant 1); artifact structure unchanged (§8).
- Per-phase contract untouched — no phase code moves (Invariant 2).
- Non-U-M golden green; no U-M content added (Invariant 3).
- No new module-level mutable state; the move adds none (§3.4 parallel-ready).
- `sc` names unchanged and re-verified by the new façade test (Invariant 9).
- Recorded fixtures not regenerated (Invariant 10).
- Column-0 literals moved verbatim (Invariant 8).

## Tasks (subagent-driven — CAMPAIGN.md §12, `prompts/implementation-standards.md`)

Dispatch every code-touching task as `psh-implementer`, every review as `psh-reviewer`, TDD via
`mattpocock-skills:tdd`. Each task ends green (`./run-tests --fast` at minimum; goldens
byte-identical). Per-task commits.

- **Task 1 — Gateway move + `GatewayResult` + seam repoint.** Create `psh/gateway.py` with the
  eleven defs moved per §Move mechanics (logic + column-0 literals byte-for-byte; returns wrapped
  in `GatewayResult`; real annotations; the §Broad-ruff findings dispositions applied — the three
  `# noqa`s with inline reasons and the four behavior-preserving fixes); import them back into
  `psh/_legacy.py`; add the `gateway` conftest fixture; repoint the four test files' `run_terminus`
  patches to the `gateway` seam (leave every `psh.time.sleep`/`psh.subprocess.Popen` patch
  untouched — §Seams); add the `GatewayResult` return-type test (RED first).
  Gates: `ruff check --config ruff-broad.toml psh/gateway.py` → "All checks passed!" and pyright 0
  errors on `psh/gateway.py`; full `./run-tests --fast` green; four goldens byte-identical; the
  mandatory extracted-literal diff (§Column-0 literal invariant) pasted empty.
- **Task 2 — House-rule instruments.** Add the no-Popen-outside-gateway test (with its RED-then-
  revert demonstration pasted) and the `sc`-façade-names test to `tests/unit/test_house_rules.py`.
- **Task 3 — Docs, memory, ledger.** Update `CLAUDE.md` (gateway added to the carved-out modules;
  wrapper bullet notes the `psh/gateway.py` home + `GatewayResult`; Testing "Two mock seams" note
  gives the `psh.gateway.run_terminus` in-process seam + `gateway` fixture); `tests/README.md:63`
  seam line; add an auto-memory for the gateway extraction + seam move; append the LEDGER.md I2
  entry (template CAMPAIGN.md §12). Report the CLAUDE.md line-count delta (DoD).

Then: `/code-review` (or `prompts/adversarial-review.md`) whole-branch, full `./run-tests` (live
tier if credentialed, else `--fast` with a ledger note), `/archive-session`, closing commit
including this `development/` folder.

## Acceptance criteria (commands + pasted output — CAMPAIGN.md §16)

Baseline (I2 start) = `8b1466b`. Run and pasted at close:

```
# 1. Full suite (live tier present), all three gates, goldens byte-identical:
$ ./run-tests --llm    (tail)
All checks passed!
All checks passed!
0 errors, 0 warnings, 0 informations
LLM_SUMMARY passed=755 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
27 snapshots passed.
755 passed, 1 skipped in 27.94s
# (the 1 skip is test_db_credentials.py's importorskip("MySQLdb") on a sqlite-only install)

# 2. Goldens unchanged across the increment:
$ git diff 8b1466b HEAD -- tests/e2e/__snapshots__/       →  empty (four goldens byte-identical)

# 3. gateway.py under the full gate, zero findings:
$ uvx ruff check --config ruff-broad.toml psh/gateway.py  →  All checks passed!
  pyright (venv, ./run-tests scope psh minus _legacy)      →  0 errors, 0 warnings, 0 informations

# 4. New instruments, shown RED then GREEN (Task reports carry the pasted red states):
#  - GatewayResult return-type test: RED "AttributeError: module 'psh._legacy' has no attribute
#    'GatewayResult'"  →  GREEN "2 passed".
#  - no-Popen-outside-gateway: RED (temp Popen in script_context.py) "['script_context.py'] …
#    == []"  →  reverted, GREEN.
#  - sc-façade-names: RED (commented sc.db_engine_args) "['db_engine_args'] … == []"  →  reverted,
#    GREEN.
#  - ENVIRON_SCOPE widening (review follow-up): RED (os.environ in psh/_legacy.py)
#    "['psh/_legacy.py'] read os.environ directly"  →  reverted, GREEN.
```
