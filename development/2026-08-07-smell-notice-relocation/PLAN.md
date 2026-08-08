# Smell-Notice Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task, layered with
> `prompts/implementation-standards.md`. Steps use checkbox (`- [ ]`) syntax for tracking.
> Dispatch every code-touching subagent as **`psh-implementer`** and every reviewer as
> **`psh-reviewer`** (CLAUDE.md § Dispatching subagents) — `general-purpose` carries none of the
> standards.

**Goal:** Move the three smell notices (`wp-smell`, `drush-smell`, `composer-smell`) out of
`main()` into a new gated `check/smells/` package registered at `site_pre_render`, with zero
observable behavior change, and delete the README TO DO that asked for a `mutates` DAG edge kind
to make this possible.

**Architecture:** The emission becomes a hook at **`site_pre_render`** (phase index 5) rather than
`site_post_gather` (index 4). That single choice replaces all three guarantees the inline call site
provided — ordering after the in-place `wp_smell`/`drush_smell` mutators, the `--only-warn` gate,
and notice list position — so no DAG engine change is needed. Full reasoning:
`development/2026-08-07-smell-notice-relocation/SPEC.md` §3.

**Tech Stack:** Python 3.12+, pytest (+ syrupy snapshots), the repo's self-registering
`check/` package system (`psh/modules.py`), `script_context` (`sc`) façade.

---

## Global Constraints

Copied verbatim from the SPEC; every task's requirements implicitly include this section.

- **Read first, in this order:** `prompts/directives.md` (the Spine), then
  `prompts/implementation-standards.md`, then `CLAUDE.md`, then
  `development/2026-08-07-smell-notice-relocation/SPEC.md`, then your task.
- **Test-first** (`mattpocock-skills:tdd`, *not* `superpowers:test-driven-development`).
  Refactoring is not part of the red→green loop; it belongs to review.
- **Every new test MUST be shown red-capable** on the condition it guards, with the failing output
  pasted into the task report. A green check is a claim, not evidence (PD#14).
- **`build_smell_notices` moves byte-verbatim.** Campaign Invariant 8: the interior whitespace of
  every `html=`/`text=` f-string literal is string content that reaches the rendered email, and
  `git diff -w` is designed to ignore exactly the line that only gained some. The composer literals
  sit at **column 0** (D-i10-8).
- **Exactly five sanctioned substitutions** are permitted in the moved block, and NEVER any other:
  1. `from psh.notice import Notice, Severity, registry` → `import script_context as sc`
  2. `registry.register(` → `sc.registry.register(`
  3. `Notice(` → `sc.Notice(`
  4. `Severity.INFO` → `sc.Severity.INFO`
  5. `-> list[Notice]` → `-> list[sc.Notice]` (the same rename as 3, in annotation position)
- **NEVER regenerate a snapshot or golden in this work.**
  `tests/integration/__snapshots__/test_smell_notice_render.ambr` and all four e2e goldens MUST
  come out **byte-identical**; `git diff --stat` on both snapshot directories MUST be empty. A red
  golden is the signal that the move is wrong — fix the move (Spine).
- **NEVER delete, skip, `xfail`, or weaken a test**, and NEVER lower a gate (ruff, pyright) to pass.
- **Notice code strings and descriptions MUST NOT change** — `wp-smell` / "wp-cli wrote to stderr",
  `drush-smell` / "drush wrote to stderr", `composer-smell` / "composer wrote to stderr" — so
  `tests/integration/test_notice_roster.py`'s frozen roster stays at **36** codes.
- **The gate default is TRUE.** `[Check.smells].enabled` absent, or `[Check]` absent entirely, MUST
  still register the hook: relocating a check that ran unconditionally MUST NOT silently disable it.
- **Commit only what each task's step says to commit.** Do not create branches. Do not push.
- **Verify with** `source .venv/bin/activate && ./run-tests --fast` (the offline gate: ruff →
  pyright → pytest, each aborting on first failure). The live tier is not part of this work.
- **Baseline, measured 2026-08-07 before any change:** ruff `All checks passed!`; pyright
  `0 errors, 0 warnings, 0 informations`; `1841 passed, 3 skipped, 2 deselected`;
  `107 snapshots passed`.
- **Task reports MUST cite the directives applied by number and with a verbatim quote**, grep-
  checkable against `prompts/directives.md`.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `check/smells/__init__.py` | **New.** The `[Check.smells].enabled` gate and the one `site_pre_render` hook registration. Nothing else. | 1 |
| `check/smells/notices.py` | **New.** The three `NOTICE_*` code registrations and `build_smell_notices` — pure builders, no `site_context`, no `sc.options`. | 1 |
| `check/smells/hook.py` | **New.** `emit_smell_notices(site_context)`: reads the three contract keys live and calls `site_context.add_notices(...)`. Nothing else. | 1 |
| `psh/gather.py` | Modify: lose the builder, its three notice codes, the orphaned `import json`, and two docstring claims. | 1 |
| `psh/cli.py` | Modify: lose the five-line emission and one import name. | 1 |
| `sample-pantheon-sitehealth-emails.toml` | Modify: add `[Check.smells]`. | 1 |
| `tests/unit/test_smell_notices.py` | Modify: repoint off the `psh` fixture onto the standalone-loaded module. Assertions unchanged. | 1 |
| `tests/integration/test_smell_notice_render.py` | Modify: same repoint. Test names unchanged so the `.ambr` keys are unchanged. | 1 |
| `tests/integration/test_check_smells_init.py` | **New.** Gating + the load-bearing phase assertion. | 1 |
| `tests/integration/test_check_smells.py` | **New.** The hook seam, including the reads-the-rebound-key instrument. | 1 |
| `tests/integration/test_hook_dag.py` | Modify: one `ALL_PACKAGES` entry. | 1 |
| `tests/integration/test_notice_roster.py` | Modify: regroup three codes under a new comment heading. Set and count unchanged. | 1 |
| `tests/integration/test_regressions.py` | Modify: one stale comment. | 1 |
| `CLAUDE.md`, `CONTEXT.md`, `README.md`, campaign `CAMPAIGN.md` + `LEDGER.md` | Modify: documentation. | 2 |

---

## Why Task 1 is one task and not four

The three notice codes are registered at module import and `psh.notice.registry.register()` raises
`DuplicateNoticeCodeError` on a repeat. `psh.cli` imports `psh.gather` at test-session start, so for
as long as **both** `psh/gather.py` and `check/smells/notices.py` define the codes, any test that
loads the new package raises. Creating the package and removing it from `psh/` therefore cannot be
split across commits without a red suite in between. Steps 8–14 below are consequently one atomic
implementation unit: they are written before the suite is run again, not interleaved with runs.

---

### Task 1: Relocate the smell notices to `check/smells/`

**Files:**
- Create: `check/smells/__init__.py`, `check/smells/notices.py`, `check/smells/hook.py`
- Create: `tests/integration/test_check_smells_init.py`, `tests/integration/test_check_smells.py`
- Modify: `psh/gather.py` (delete lines 65-68, line 37, lines 673-752, and two docstring passages)
- Modify: `psh/cli.py:80`, `psh/cli.py:975-979`
- Modify: `sample-pantheon-sitehealth-emails.toml` (after line 120)
- Modify: `tests/unit/test_smell_notices.py`, `tests/integration/test_smell_notice_render.py`
- Modify: `tests/integration/test_hook_dag.py`, `tests/integration/test_notice_roster.py`,
  `tests/integration/test_regressions.py:154`

**Interfaces:**
- Consumes: nothing from an earlier task (this is the first).
- Produces, for Task 2's documentation:
  - `check.smells.notices.build_smell_notices(site_name: str, wp_smell: str, drush_smell: str,
    composer_smell: str) -> list[sc.Notice]` — signature **unchanged** from `psh/gather.py`.
  - `check.smells.hook.emit_smell_notices(site_context) -> None`
  - Hook registration name string: `"check.smells.hook.emit_smell_notices"`, phase
    `"site_pre_render"`, `consumes: ['wp_smell', 'drush_smell', 'composer_smell']`, `produces: []`.
  - Config key: `[Check.smells].enabled`, default `true`.

---

- [ ] **Step 1: Write the failing gating/declaration test**

Create `tests/integration/test_check_smells_init.py`:

```python
"""check/smells registration + [Check.smells] gating
(development/2026-08-07-smell-notice-relocation/SPEC.md section 6.2).

Default is ENABLED: relocating code must not silently disable notices that rendered
unconditionally before -- the D-i8-6/D-i9-5/D-i10-5 shape."""
import pytest
from helpers.checkload import load_check_package
from helpers.dnsfake import recording_console

pytestmark = pytest.mark.integration

EXPECTED_NAMES = ["check.smells.hook.emit_smell_notices"]


def test_registers_hook_when_config_is_silent(psh, reset_sc, request):
    reset_sc.config = {}
    load_check_package(psh, "smells", "smells_init_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_pre_render"]] == EXPECTED_NAMES


def test_registers_hook_when_explicitly_enabled(psh, reset_sc, request):
    reset_sc.config = {"Check": {"smells": {"enabled": True}}}
    load_check_package(psh, "smells", "smells_on_probe", request)
    assert [h["name"] for h in reset_sc.hooks["site_pre_render"]] == EXPECTED_NAMES


def test_disabled_registers_nothing_and_says_so(psh, reset_sc, request, monkeypatch):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.config = {"Check": {"smells": {"enabled": False}}}
    load_check_package(psh, "smells", "smells_off_probe", request)
    assert not reset_sc.hooks.get("site_pre_render")
    assert "Skipping check.smells" in console.export_text()


def test_the_phase_is_site_pre_render_and_that_is_load_bearing(psh, reset_sc, request):
    """The phase string carries THREE guarantees at once (SPEC section 3.2), which is why it
    gets its own assertion rather than riding along in the gating tests above:

      1. Ordering.  The in-place wp_smell/drush_smell mutators (check.wordpress.ocp,
         check.wordpress.favicon, check.umich.drupal_ua) are all site_post_gather hooks and are
         deliberately DAG-invisible (D-i9-3).  A later phase is unconditionally after them; a
         same-phase hook would need a `mutates` edge kind that this repo deliberately does not
         have (SPEC section 3.3).
      2. The --only-warn gate.  main() `continue`s at psh/cli.py:964, ABOVE the site_pre_render
         firing at :1003.  Move this hook to site_post_gather and every --only-warn run starts
         writing smell rows into -notices.csv -- a silent output-surface change (PD#1).
      3. Notice order.  Nothing between the old emission point and the phase firing appends to
         site_context["notices"], so the info bucket is byte-identical to the pre-move report.

    test_hook_dag.py stays GREEN if this hook moves to site_post_gather -- the declarations are
    legal there too.  This assertion is the only thing that goes red."""
    reset_sc.config = {}
    load_check_package(psh, "smells", "smells_decl_probe", request)

    assert [h["name"] for h in reset_sc.hooks["site_pre_render"]] == EXPECTED_NAMES
    for phase in reset_sc.PHASES:
        if phase == "site_pre_render":
            continue
        assert all(h["name"] not in EXPECTED_NAMES for h in reset_sc.hooks.get(phase, [])), (
            f"the smells hook must be registered ONLY at site_pre_render, not {phase}")

    (hook,) = reset_sc.hooks["site_pre_render"]
    assert hook["consumes"] == ["wp_smell", "drush_smell", "composer_smell"]
    assert hook["produces"] == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `source .venv/bin/activate && python -m pytest tests/integration/test_check_smells_init.py -v`
Expected: all four FAIL — `FileNotFoundError` / `No such file or directory:
'/workspace/check/smells/__init__.py'` from `load_check_package`.

- [ ] **Step 3: Write the failing hook-seam test**

Create `tests/integration/test_check_smells.py`:

```python
"""check.smells.hook seam (SPEC section 6.3): the BLOCKMAP B48 emission as a site_pre_render
hook.

It reads the three smell keys off the SiteContext LIVE.  wp_smell and drush_smell are the two
sanctioned mutate-during-phase contract keys (CLAUDE.md's site_post_gather row): check.wordpress
.ocp / .favicon and check.umich.drupal_ua rebind them IN PLACE during that phase, so a hook that
captured them into locals -- or a caller that passed main()'s stale local -- would emit the
pre-mutation value.  test_reads_the_rebound_wp_smell_not_the_stuffed_one is the only test that
pins that."""
import pytest
from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration

SITE_NAME = "its-wws-test1"
SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"


@pytest.fixture
def hook_mod(psh, request):
    return load_check_module(psh, "smells", "hook", "smells_hook_probe", request)


def _ctx(reset_sc, wp="", drush="", composer=""):
    ctx = reset_sc.SiteContext({"name": SITE_NAME, "id": SITE_ID})
    ctx["wp_smell"] = wp
    ctx["drush_smell"] = drush
    ctx["composer_smell"] = composer
    return ctx


def _codes(ctx):
    # the render dict's csv row is "site,code,*csv_extra" (SiteContext.notice_to_dict); the site
    # name contains no comma, so field 1 is the code.
    return [n["csv"].split(",")[1] for n in ctx["notices"]]


def test_all_three_smells_become_three_notices_in_builder_order(hook_mod, reset_sc):
    ctx = _ctx(reset_sc, wp="wp broke", drush="drush broke", composer="composer broke")
    hook_mod.emit_smell_notices(ctx)
    assert _codes(ctx) == ["wp-smell", "drush-smell", "composer-smell"]


def test_no_smells_adds_no_notices(hook_mod, reset_sc):
    # PD#3's empty-input shadow path: all three keys are "" on a clean site, which is the
    # overwhelmingly common case -- a report must not gain an empty "PHP code problems" notice.
    ctx = _ctx(reset_sc)
    hook_mod.emit_smell_notices(ctx)
    assert ctx["notices"] == []


def test_the_site_name_comes_from_the_site_context(hook_mod, reset_sc):
    ctx = _ctx(reset_sc, wp="wp broke")
    hook_mod.emit_smell_notices(ctx)
    (n,) = ctx["notices"]
    assert n["csv"].startswith(f"{SITE_NAME},wp-smell,")
    assert SITE_NAME in n["message"]


def test_reads_the_rebound_wp_smell_not_the_stuffed_one(hook_mod, reset_sc):
    # Simulates check.wordpress.ocp: core stuffs wp_smell="" at site_post_gather, then the ocp
    # probe rebinds it IN PLACE during the phase.  This hook runs at site_pre_render, after that
    # phase, and MUST report the rebound value.
    ctx = _ctx(reset_sc, wp="")
    ctx["wp_smell"] = "PHP Deprecated: strlen(): Passing null is deprecated"
    hook_mod.emit_smell_notices(ctx)
    (n,) = ctx["notices"]
    assert "PHP Deprecated" in n["message"]
    assert _codes(ctx) == ["wp-smell"]
```

- [ ] **Step 4: Run it to make sure it fails**

Run: `source .venv/bin/activate && python -m pytest tests/integration/test_check_smells.py -v`
Expected: all four FAIL — `FileNotFoundError` on `/workspace/check/smells/__init__.py` from
`load_check_module`'s package shell.

- [ ] **Step 5: Repoint the unit test off the `psh` fixture**

Rewrite `tests/unit/test_smell_notices.py`. Only the module-loading mechanism changes — every
assertion, test name, and comment below the header is preserved verbatim from the current file.
The pattern is `tests/unit/test_annual_billing_notices.py`'s (the same situation: a builder that
relocated into `check/`).

Replace the header and add the fixture:

```python
"""build_smell_notices unit tests (campaign I1, SPEC F1).

Repointed at campaign I14c: the builder returns Notice objects, so the reads are
`.code`/`.csv_extra`/`.html`/`.text` instead of the render dict's subscripts.  The asserted
VALUES are unchanged -- the site-name half of the csv row now comes from the SiteContext at
projection time (SPEC I14c section 2.2), pinned by tests/unit/test_add_notice_from_notice.py.

Repointed again on 2026-08-07: the builder relocated to check/smells/notices.py
(development/2026-08-07-smell-notice-relocation/SPEC.md), so load it standalone -- the
test_annual_billing_notices.py precedent; no psh re-import exists for check/ modules.
load_check_module loads notices.py WITHOUT running check/smells/__init__.py, so no hook is
registered and no config gate is consulted: these stay pure builder tests.
"""
import json

import pytest
from helpers.checkload import load_check_module

pytestmark = pytest.mark.unit


@pytest.fixture
def smells(psh, request):
    return load_check_module(psh, "smells", "notices", "smells_notices_unit_probe", request)
```

Then, in each of the eight existing test functions, replace the `psh` parameter with `smells` and
every `psh.build_smell_notices(` with `smells.build_smell_notices(`. Change nothing else — not a
name, not an assertion, not a comment. For example:

```python
def test_no_smells_returns_empty_list(smells):
    assert smells.build_smell_notices("s", "", "", "") == []


def test_wp_smell_alone(smells):
    (n,) = smells.build_smell_notices("s", "wp broke", "", "")
    assert n.code == "wp-smell"
    assert n.severity == "info"   # rewritten from 'type': 'info' at I14c; nothing else pins it
    assert n.csv_extra == (json.dumps("wp broke").replace(",", "\\,"),)
    assert "wp broke" in n.html and "wp broke" in n.text
```

The parametrized test keeps its decorator and takes `smells` alongside its four params:

```python
@pytest.mark.parametrize(("wp", "drush", "composer", "expected"), [
    ("a, b\nc", "", "", '"a\\, b\\nc"'),
    ("", "d, e", "", '"d\\, e"'),
    ("", "", "f, g", '"f\\, g"'),
])
def test_smell_csv_field_escapes_embedded_commas(smells, wp, drush, composer, expected):
```

- [ ] **Step 6: Repoint the snapshot test**

Rewrite `tests/integration/test_smell_notice_render.py`. **The file name and all three test names
MUST stay exactly as they are** — syrupy keys snapshots by both, and
`tests/integration/__snapshots__/test_smell_notice_render.ambr` MUST come out byte-identical.

```python
"""Syrupy pins of the three build_smell_notices bodies (campaign I10, D-i10-8): the
forward byte-identity guard for the composer-literal de-indent -- CAMPAIGN.md
section 10's grep still finds zero smell renders in any golden, so this file is the
only render coverage for these three notice bodies.

Repointed on 2026-08-07 when the builder relocated to check/smells/notices.py
(development/2026-08-07-smell-notice-relocation/SPEC.md).  The three test names are unchanged
on purpose: syrupy keys the .ambr by file name AND test name, so this file's snapshots stay
byte-identical across the move -- which is precisely the evidence that the literals moved
verbatim."""
import pytest
from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration


@pytest.fixture
def smells(psh, request):
    return load_check_module(psh, "smells", "notices", "smells_notices_render_probe", request)


def test_wp_smell_notice_snapshot(smells, snapshot):
    (n,) = smells.build_smell_notices("its-wws-test1", "wp broke", "", "")
    assert n.html == snapshot
    assert n.text == snapshot
    assert n.short == snapshot


def test_drush_smell_notice_snapshot(smells, snapshot):
    (n,) = smells.build_smell_notices("its-wws-test1", "", "drush broke", "")
    assert n.html == snapshot
    assert n.text == snapshot
    assert n.short == snapshot


def test_composer_smell_notice_snapshot(smells, snapshot):
    # D-i10-8: pins the de-indented (column-0) composer literal, matching the wp/drush
    # siblings' shape.
    (n,) = smells.build_smell_notices("its-wws-test1", "", "", "composer broke")
    assert n.html == snapshot
    assert n.text == snapshot
    assert n.short == snapshot
```

- [ ] **Step 7: Run the two repointed files to make sure they fail**

Run:
```bash
source .venv/bin/activate && python -m pytest tests/unit/test_smell_notices.py \
    tests/integration/test_smell_notice_render.py -v
```
Expected: all 13 FAIL — `FileNotFoundError` on `/workspace/check/smells/__init__.py`.
**NOT** an `AttributeError` on the `psh` module: if you see one, the repoint is incomplete.

- [ ] **Step 8: Extract the builder verbatim**

Do not retype the builder. Extract it, so the literals cannot drift:

```bash
mkdir -p check/smells
export MOVEDIR="$(mktemp -d)" && echo "$MOVEDIR"   # note this path; steps 9 and 10 reuse it
sed -n '673,752p' psh/gather.py > "$MOVEDIR/builder-before.txt"
wc -l "$MOVEDIR/builder-before.txt"                # expect 80
```

If your shell does not persist between tool calls, use a fixed path instead — e.g.
`/tmp/psh-smell-move/` created with `mkdir -p` — and substitute it for `$MOVEDIR` below.

- [ ] **Step 9: Create `check/smells/notices.py` around the extracted block**

Write this header, then paste the extracted 80 lines below it and apply **only** the five
sanctioned substitutions from Global Constraints:

```python
"""The three smell notices: non-fatal wp / drush / composer stderr, reported to the site owner
as "PHP code problems" (BLOCKMAP B48).

Moved verbatim from psh/gather.py:673-752 on 2026-08-07
(development/2026-08-07-smell-notice-relocation/SPEC.md section 5.2), where it had lived since
campaign I10 as a builder whose emission stayed in main().

Campaign Invariant 8: the interiors of the six f-string literals below are string content that
reaches the rendered email.  The composer html/text pair sits at COLUMN 0 (D-i10-8), matching
its wp/drush siblings, and tests/unit/test_smell_notices.py::
test_composer_literals_are_column_zero_like_siblings is what goes red if that changes --
`git diff -w` cannot see it.

Five sanctioned substitutions were applied to the moved block and no others: the psh.notice
import became `import script_context as sc`, and `registry.` / `Notice(` / `Severity.` /
`list[Notice]` became their `sc.`-prefixed forms -- the checks-import-only-sc convention
(Invariant 9) and the check/-registers-through-the-facade rule (CLAUDE.md, Notices vs. news).
"""
import html
import json

import script_context as sc

# Notice codes registered at import; see CLAUDE.md section "Notices vs. news".
NOTICE_WP_SMELL = sc.registry.register("wp-smell", description="wp-cli wrote to stderr")
NOTICE_DRUSH_SMELL = sc.registry.register("drush-smell", description="drush wrote to stderr")
NOTICE_COMPOSER_SMELL = sc.registry.register(
    "composer-smell", description="composer wrote to stderr")
```

The pasted block begins with:

```python
def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell) -> list[sc.Notice]:
```

and its docstring — which currently reads "The emission call stays in `main()` (SPEC D-i10-1
amendment 1); this is only the builder." — MUST be replaced with:

```python
    """Return the list of smell Notices (possibly empty) for one site (BLOCKMAP B48).

    Pure: the emission is check/smells/hook.py's, at site_pre_render."""
```

That docstring is prose about where the code lives, not a moved literal, so replacing it is not a
violation of the byte-verbatim rule — but it is the **only** line inside the extracted block that
may be reworded.

- [ ] **Step 10: Prove the move was byte-verbatim**

```bash
sed -n '/^def build_smell_notices/,$p' check/smells/notices.py > "$MOVEDIR/builder-after.txt"
diff "$MOVEDIR/builder-before.txt" "$MOVEDIR/builder-after.txt"
```
Expected: the diff shows **only** the docstring rewording (step 9) and the two annotation/
constructor renames — `-> list[Notice]` → `-> list[sc.Notice]`, `Notice(` → `sc.Notice(`,
`Severity.INFO` → `sc.Severity.INFO`. **Paste this diff into the task report.** Any change to a
line inside an `html=` or `text=` f-string is a defect; go back to step 8.

- [ ] **Step 11: Create `check/smells/hook.py`**

```python
"""Emit the three smell notices at site_pre_render (BLOCKMAP B48's emission).

Reads the three smell keys off the SiteContext LIVE and never caches them: wp_smell and
drush_smell are the two sanctioned mutate-during-phase contract keys (CLAUDE.md's
site_post_gather row), rebound IN PLACE during that phase by check.wordpress.ocp /
check.wordpress.favicon and check.umich.drupal_ua.  This is a straight transcription of the
call this replaced (psh/cli.py:975-979 before 2026-08-07), which already read site_context
rather than main()'s locals.  Pinned by tests/integration/test_check_smells.py::
test_reads_the_rebound_wp_smell_not_the_stuffed_one.
"""

from . import notices


def emit_smell_notices(site_context):
    site_context.add_notices(
        notices.build_smell_notices(
            site_context["site"]["name"],
            site_context["wp_smell"],
            site_context["drush_smell"],
            site_context["composer_smell"],
        )
    )
```

The three keys are read with `[...]`, **never** `.get(..., "")`: they are core-stuffed at
`site_post_gather` and guaranteed present by the time this phase fires, so a `KeyError` here would
mean the contract broke — and a loud `KeyError` is correct where a `.get` default would silently
emit nothing (PD#1).

- [ ] **Step 12: Create `check/smells/__init__.py`**

```python
"""The wp / drush / composer "PHP code problems" notices (BLOCKMAP B48), gated by
[Check.smells].enabled, default TRUE -- these three notices rendered unconditionally, inline in
main(), before the 2026-08-07 relocation
(development/2026-08-07-smell-notice-relocation/SPEC.md).

THE PHASE IS LOAD-BEARING.  site_pre_render, not site_post_gather beside the other framework
checks, and it carries three guarantees at once (SPEC section 3.2):

  1. Ordering.  wp_smell and drush_smell are rebound IN PLACE during site_post_gather by
     check.wordpress.ocp / check.wordpress.favicon / check.umich.drupal_ua, which are
     deliberately DAG-invisible (D-i9-3) -- they cannot declare produces: ['wp_smell'] without
     a duplicate-producer fatal against the core CONTRACT registry.  A LATER phase is
     unconditionally after them, so no `mutates` edge kind is needed; a same-phase hook would
     have needed one (SPEC section 3.3, and the README TO DO this change discharged).
  2. The --only-warn gate.  main() `continue`s above the site_pre_render firing, so a
     warning-only run emits no smell rows -- exactly as the inline emission did.  Moving this
     hook to an earlier phase silently changes -notices.csv output (PD#1).
  3. Notice order.  Nothing appended to site_context["notices"] between the old inline call
     site and this phase, so the rendered info bucket is unchanged.

tests/integration/test_hook_dag.py stays green if this moves to site_post_gather; the assertion
that goes red is test_check_smells_init.py::
test_the_phase_is_site_pre_render_and_that_is_load_bearing.
"""
import script_context as sc

if sc.config.get('Check', {}).get('smells', {}).get('enabled', True) is not False:
    from .hook import emit_smell_notices
    sc.add_hook('site_pre_render', {'name': 'check.smells.hook.emit_smell_notices',
                                    'func': emit_smell_notices,
                                    'consumes': ['wp_smell', 'drush_smell', 'composer_smell'],
                                    'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.smells because it is disabled in the config')
```

- [ ] **Step 13: Strip `psh/gather.py`**

Four deletions, and nothing else:

1. **Lines 65-68** — the three smell constants (`NOTICE_WP_SMELL`, `NOTICE_DRUSH_SMELL`, and the
   two-line `NOTICE_COMPOSER_SMELL`). Leave `NOTICE_COMPOSER_UPDATE` (lines 63-64) alone.
2. **Line 37** — `import json`. It has no other use in the file (verify with
   `grep -n json psh/gather.py`, which must print nothing afterwards). Leave `import html`: it has
   12 `html.escape` call sites, only 3 of which are in the moved builder.
3. **Lines 673-752** — `build_smell_notices` and its blank-line separator, to end of file.
4. **The docstring paragraph** beginning `build_smell_notices is the B48 smell-notice *builder*`
   and its trailing blank line. In the same docstring, extend the sentence listing where the
   relocated notice-emitting checks live so it reads:

```
The notice-emitting checks that used to be interleaved in this code live in
check/wordpress/, check/drupal/, check/addon_updates/, and check/umich/ (site_post_gather
hooks) and check/smells/ (a site_pre_render hook); the wp_error/drush_error notices below
describe *failed gathers*, not checks, so they stay with the fetches (D-i9-1/D-i10-1).
```

- [ ] **Step 14: Strip `psh/cli.py`**

1. Delete `    build_smell_notices,` from the `from psh.gather import (...)` block at line 80.
2. Delete the emission at lines 975-979 **and** the blank line that followed it:

```python
            site_context.add_notices(
                build_smell_notices(site["name"], site_context["wp_smell"],
                                    site_context["drush_smell"],
                                    site_context["composer_smell"])
            )
```

Leave the `sc.debug("===== Notices:\n", ...)` lines that followed it in place.

- [ ] **Step 15: Register the package with the two enumerated test lists**

In `tests/integration/test_hook_dag.py`, add to `ALL_PACKAGES` in alphabetical position — between
the `pantheon_cdn_change` and `umich` entries:

```python
    ("check", "smells", "hookdag_check_smells"),
```

In `tests/integration/test_notice_roster.py`, move the three codes out of the `# psh/gather.py`
group into a new group placed in the same alphabetical-by-path order the file already uses (after
`# check/pantheon_cdn_change/notices.py`, before `# check/umich/`). The set membership and
`len(ROSTER) == 36` are unchanged; only the comment grouping moves, because that grouping is how a
reader traces a code to its `register()` call.

```python
    # psh/gather.py
    "not-installed", "multiple-installed", "turned-off", "composer-update",
```
```python
    # check/smells/notices.py
    "wp-smell", "drush-smell", "composer-smell",
```

Also update that file's module docstring, which currently says "the six psh/gather.py codes" — it
is now four.

- [ ] **Step 16: Fix the one stale comment in `tests/integration/test_regressions.py`**

At line 154, `build_smell_notices emits nothing` describes a call that no longer exists in
`main()`. Change that clause to `the check.smells hook emits nothing`. Change nothing else in that
file — `test_each_smell_merge_stays_guarded` asserts on `main()`'s smell **merges**, which this
work does not touch.

- [ ] **Step 17: Add the config section**

In `sample-pantheon-sitehealth-emails.toml`, after the `[Check.addon_updates]` block (line 119-120)
and before `[Database]`, matching the surrounding blank-line and comment style:

```toml
[Check.smells]
enabled = true          # "PHP code problems" notices from wp/drush/composer stderr
```

- [ ] **Step 18: Run the whole gate**

Run: `source .venv/bin/activate && ./run-tests --fast`

Expected: ruff `All checks passed!`; pyright `0 errors, 0 warnings, 0 informations`;
`1849 passed, 3 skipped, 2 deselected` (baseline 1841 + 8 new: 4 in
`test_check_smells_init.py`, 4 in `test_check_smells.py`); `107 snapshots passed`.

Paste the final summary line into the task report and state the delta explicitly. A count that
went **down** means a moved test stopped being collected — that is PD#14, not a rounding error.

- [ ] **Step 19: Prove nothing observable moved**

```bash
git diff --stat tests/integration/__snapshots__/   # MUST be empty
git diff --stat tests/e2e/__snapshots__/           # MUST be empty
grep -c build_smell_notices psh/cli.py psh/gather.py   # MUST be 0 for both
grep -n json psh/gather.py                             # MUST print nothing
./run-tests --fast tests/e2e                           # MUST pass with no --update-goldens
./run-tests --fast -k smell                            # the moved + new tests
```

Paste all six outputs. If either snapshot diff is non-empty, **do not** run `--update-goldens`:
the move is wrong.

- [ ] **Step 20: Prove the four new instruments are red-capable**

For each fault below: apply it, run the named test, paste the failure, revert the fault. A test
that stays green under its fault is not an instrument (PD#14).

| # | Fault to inject | Test that MUST go red |
|---|---|---|
| 1 | In `check/smells/__init__.py`, change `'site_pre_render'` to `'site_post_gather'` | `test_check_smells_init.py::test_the_phase_is_site_pre_render_and_that_is_load_bearing` — and confirm in the same run that `tests/integration/test_hook_dag.py` stays **green**, which is the whole reason this assertion exists |
| 2 | In `check/smells/__init__.py`, change the gate default from `True` to `False` | `test_check_smells_init.py::test_registers_hook_when_config_is_silent` |
| 3 | In `check/smells/hook.py`, capture the three smells into locals at import time, or read a hardcoded `""` for `wp_smell` | `test_check_smells.py::test_reads_the_rebound_wp_smell_not_the_stuffed_one` |
| 4 | In `check/smells/notices.py`, add one leading space to the first interior line of the composer `html=` literal | `test_smell_notices.py::test_composer_literals_are_column_zero_like_siblings` **and** `test_smell_notice_render.py::test_composer_smell_notice_snapshot` — the second is the proof the `.ambr` is still load-bearing after the repoint |

- [ ] **Step 21: Commit**

```bash
git add check/smells psh/gather.py psh/cli.py sample-pantheon-sitehealth-emails.toml \
        tests/unit/test_smell_notices.py tests/integration/test_smell_notice_render.py \
        tests/integration/test_check_smells_init.py tests/integration/test_check_smells.py \
        tests/integration/test_hook_dag.py tests/integration/test_notice_roster.py \
        tests/integration/test_regressions.py
git commit -m "refactor(smells): move the B48 smell-notice emission into check/smells/

The three smell notices (wp-smell, drush-smell, composer-smell) leave main() for a
gated check/ package registered at site_pre_render.  That phase -- not site_post_gather
beside the other framework checks -- is what makes the move behavior-neutral: it is
unconditionally after the in-place wp_smell/drush_smell mutators, it sits below main()'s
--only-warn continue, and nothing appends to site_context[\"notices\"] between the old
call site and the phase firing, so the rendered info bucket and -notices.csv are
unchanged.  All four e2e goldens and test_smell_notice_render.ambr are byte-identical.

This discharges README's first post-campaign TO DO by dissolving it: the \`mutates\` DAG
edge kind it asked for is only needed for a SAME-phase consumer, and no such consumer
exists.  Spec: development/2026-08-07-smell-notice-relocation/SPEC.md

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Documentation, the CAMPAIGN.md amendment, and the README TO DO deletion

This is a separate task because a reviewer can meaningfully reject the documentation while
approving the code (and vice versa), and because the CAMPAIGN.md amendment is governed by a
protocol — that document's preamble requires editing the document **and** appending a `LEDGER.md`
entry — that is worth its own gate.

**Files:**
- Modify: `CLAUDE.md`
- Modify: `CONTEXT.md`
- Modify: `README.md`
- Modify: `development/2026-07-17-modularization-campaign/CAMPAIGN.md`
- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md`

**Interfaces:**
- Consumes from Task 1: the names in Task 1's *Produces* block — `check/smells/notices.py`,
  `check/smells/hook.py`, `check.smells.hook.emit_smell_notices`, `site_pre_render`,
  `[Check.smells].enabled`.
- Produces: nothing further.

- [ ] **Step 1: Update `CLAUDE.md` — the five places that are now false**

Grep first so none is missed: `grep -n "build_smell_notices\|smell" CLAUDE.md`. The edits:

1. **`psh/gather.py` bullet** (~line 620). The text to replace reads exactly:

   ```
   `build_smell_notices`
   (the smell-notice *builder*; **its emission stays in `main()`** because it summarizes
   end-of-phase smell state no hook position can guarantee and must stay behind the `--only-warn`
   gate). The `wp_error`/`drush_error` notices for *failed gathers* stay with the fetches (they
   describe the gather, not a check); the notice-emitting checks that once interleaved here live
   in `check/wordpress/`, `check/drupal/`, and `check/umich/`.
   ```

   Replace it with:

   ```
   The `wp_error`/`drush_error` notices for *failed gathers* stay with the fetches (they
   describe the gather, not a check); the notice-emitting checks that once interleaved here live
   in `check/wordpress/`, `check/drupal/`, `check/umich/`, and `check/smells/` — the last of
   which took `build_smell_notices` *and* its emission out of this module and out of `main()`
   on 2026-08-07 (`development/2026-08-07-smell-notice-relocation/SPEC.md`).
   ```

   Note the sentence being deleted claims "no hook position can guarantee" the end-of-phase smell
   state. That was true only within `site_post_gather`; leaving it in place would be the single
   most misleading line left in the file.
2. **`find_modules()` package list** — add `check.smells` to the enumerated list of imported
   packages (currently ends `check.umich`, `check.wordpress`).
3. **The `check/` package descriptions** — add a `check/smells/` bullet, alongside
   `check/addon_updates/`, stating the phase, the gate (`[Check.smells].enabled`, default true),
   and one sentence on why the phase is `site_pre_render`.
4. **The per-phase data-contract table, `site_pre_render` row** — it currently describes
   `check.umich.annual_billing` as the phase's only hook. Note that `check.smells` also runs here
   and *consumes* the three smell keys (it produces nothing, so the row's guaranteed-keys list is
   unchanged).
5. **The Testing section** — the `test_smell_notice_render.py` / `test_smell_notices.py`
   references now describe standalone-loaded check modules, and the two new files
   (`test_check_smells_init.py`, `test_check_smells.py`) join the list.

Also check the "Per-site report pipeline" prose and the `psh/gather.py` module description for any
remaining claim that the emission is inline in `main()`.

- [ ] **Step 2: Add the `Smell` glossary entry to `CONTEXT.md`**

Insert in the `## Language` section. Placement: after **Section** and before **Check**, keeping the
file's existing grouping of report-content terms together.

```markdown
**Smell**:
Non-fatal text a `wp`, `drush`, or `composer` command wrote to stderr while still
succeeding — reported to the site owner as "PHP code problems". Internal vocabulary:
the word itself never appears in a report.
_Avoid_: warning (that is a notice severity), error (a smell is not a failure)
```

`CONTEXT.md` is a domain glossary and nothing else — do not add the phase, the package path, or
any other implementation detail to it (`docs/agents/domain.md` states the split).

- [ ] **Step 3: Amend `CAMPAIGN.md`**

Two edits, per that document's preamble ("Any change to this document is an **amendment**: edit the
document *and* append a ledger entry").

**§3.2** — replace the paragraph beginning "The B48 smell notices are **not** a
`check/addon_updates/` hook (LEDGER I10 amendment 1)" with:

```markdown
The B48 smell notices moved to `check/smells/` (a `site_pre_render` hook) on 2026-08-07,
post-campaign — see `development/2026-08-07-smell-notice-relocation/SPEC.md`. The obstacles
recorded here at I10 (LEDGER I10 amendment 1) were real but `site_post_gather`-specific: a
later phase is unconditionally after the in-place `wp_smell`/`drush_smell` mutators, sits
below `main()`'s `--only-warn` gate, and leaves the notice order unchanged. The `mutates`
hook declaration that would have dissolved the same-phase version of the class was
consequently NOT built, and its README TODO is discharged.
```

**§3.3** — remove "the B48 smell-notice *emission* call" from the exhaustive
what-stays-in-`main()` list, with a bracketed cross-reference to the same spec.

- [ ] **Step 4: Append the `LEDGER.md` entry**

Append at end of file, modelled on the existing `## 2026-08-07 — post-campaign: six stage bodies
out of main()` entry immediately above it (same "Not `I<N>`-numbered" preamble, same structure).
It MUST record:

- what moved, with the commit hash from Task 1 step 21;
- **the finding**: the campaign's three obstacles were `site_post_gather`-specific, so the README
  TO DO's premise ("a `mutates` edge kind is what would let B48 become a hook") did not hold;
- that `mutates` was therefore **not built**, and what would make it worth reconsidering (a
  genuine same-phase consumer of an in-place mutator);
- the two CAMPAIGN.md amendments from step 3;
- the byte-identity evidence (four e2e goldens and `test_smell_notice_render.ambr` unchanged);
- the new config surface `[Check.smells].enabled`;
- Open questions: none.

- [ ] **Step 5: Delete the README TO DO item**

In `README.md`, delete the first item under `## TO DO` — the seven-line `* Add a \`mutates\` hook
declaration to the DAG **(post-campaign)** …` bullet — in its entirety, including its trailing
blank line so the remaining list spacing is unchanged. Nothing replaces it. Do **not** touch the
four other TO DO items.

- [ ] **Step 6: Verify the documentation says nothing false**

```bash
grep -rn "build_smell_notices\|smell-notice \*emission\*\|emission stays in" \
    CLAUDE.md README.md development/2026-07-17-modularization-campaign/CAMPAIGN.md \
    psh/ check/ | grep -v "check/smells/"
grep -rn "mutates" README.md CLAUDE.md
```
Expected: the first prints only the `check/addon_updates/__init__.py` docstring paragraph, which
records the I10 amendment as history — **update it too**, adding a one-clause "(superseded
2026-08-07 — the emission moved to `check/smells/`)". The second prints nothing.

Then re-run the gate: `source .venv/bin/activate && ./run-tests --fast` — expected identical to
Task 1 step 18. Documentation-only changes must not move the numbers; if they do, something in
step 6's edits touched code.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md CONTEXT.md README.md check/addon_updates/__init__.py \
        development/2026-07-17-modularization-campaign/CAMPAIGN.md \
        development/2026-07-17-modularization-campaign/LEDGER.md \
        development/2026-08-07-smell-notice-relocation/
git commit -m "docs(smells): record the relocation and discharge the mutates TODO

Amends CAMPAIGN.md sections 3.2 and 3.3 with the paired LEDGER entry its preamble
requires, adds the Smell glossary entry to CONTEXT.md, updates CLAUDE.md's package
roster / contract table / testing notes, and deletes README's first post-campaign TO DO
item -- the \`mutates\` DAG edge kind, superseded rather than deferred: its stated payoff
shipped without it, and the reasoning is preserved in the spec and the ledger.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Closing audit (answer in the final task report, per SPEC §12)

1. Did the `.ambr` and all four e2e goldens come out byte-identical, and was the diff **run**
   rather than assumed?
2. Was every new test shown red on the condition it guards, with the failing output pasted?
3. Did `psh/gather.py` lose exactly the orphaned `import json` — and nothing else still used?
   (`html` MUST remain: 12 `html.escape` call sites, only 3 in the moved builder.)
4. Is `check/smells/` present in **both** `ALL_PACKAGES` and the `ROSTER` comment grouping?
5. Does any documentation still claim the smell emission stays in `main()`?
