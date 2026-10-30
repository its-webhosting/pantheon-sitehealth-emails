# Drupal 10 End-of-Life Notice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch implementers as `psh-implementer` and reviewers as `psh-reviewer` (CLAUDE.md § Dispatching subagents); the TDD loop is `mattpocock-skills:tdd`, per `prompts/implementation-standards.md`.

**Goal:** Every Drupal 10 site's monthly report carries a `drupal10-eol` notice telling the owner to upgrade to Drupal 11 — WARNING before 2026-12-09, ALERT on or after it, judged by the report date.

**Architecture:** One new self-registering module, `check/drupal/d10_eol.py`, hooked at `site_post_gather` after `d7_eol` inside the existing `[Check.drupal]`-gated package. It reads three contract keys (`framework`, `drupal_version`, `end_date`) and adds one `sc.Notice`. No core (`psh/`) change.

**Tech Stack:** Python 3.12, pytest + syrupy, the repo's `check/` hook system.

**Spec:** `development/2026-10-30-d10-eol/SPEC.md`

## Global Constraints

- EOL date: `datetime.date(2026, 12, 9)`; `end_date < EOL` → `sc.Severity.WARNING` + "stops getting"; `end_date >= EOL` → `sc.Severity.ALERT` + "stopped getting" (SPEC D2, D5). No `order=` (SPEC D6).
- Notice code: `drupal10-eol`. Short: `Upgrade to Drupal 11`.
- Link: `https://pantheon.io/learning-center/drupal/10-end-of-life`, link text `Drupal 10 End of Life Date, Risks and Next Steps`.
- Severity basis is `site_context["end_date"]` (a `datetime.date`), never `date.today()`.
- Not U-M-gated; only the existing `[Check.drupal].enabled` gate.
- **Commit only when the user has authorized it** (CLAUDE.md § Other / General). Subagents do not commit.
- An existing golden going red is never refreshed to green **except** the one refresh SPEC §5 pre-declares (Task 2), and only after its diff is verified.
- **Entry condition (SPEC §0):** the `98ffa40` snapshot drift has been refreshed in a separate, user-reviewed change, and `./run-tests` is fully green on the base commit. Check it before Task 1 (Task 0). Never refresh those snapshots as part of this plan.
- `monthly-report.txt` carries an unrelated uncommitted edit (`TODAY=`); stage only this plan's lines, non-interactively (Task 2 Step 6) — `git add -p` is unavailable to agents.
- Run tests with the venv active (`source .venv/bin/activate`); inner loop `python -m pytest <path> -v`, final gate `./run-tests`.

---

### Task 0: Entry check (no code)

- [ ] **Step 1: Confirm the §0 prerequisite was COMMITTED, not just applied.**
Run: `git status --porcelain tests/ email_template.html check/cloudflare/ && git log --oneline -5`
Expected: the `status` part prints **nothing**, and the log shows the §0 commit above `98ffa40`. **Paste the output.** Any output from `status` → STOP and report (an uncommitted §0 refresh would ride into this feature's commit).

- [ ] **Step 2: Confirm the suite is green.**
Run: `./run-tests --fast` (≈ 1 minute)
Expected: ruff and pyright green, `0 failed`. **Paste the summary lines.** Anything red → STOP and report to the user — do not refresh any snapshot, do not start Task 1.

- [ ] **Step 3: Confirm SPEC.md and PLAN.md are committed** (`git log --oneline -- development/2026-10-30-d10-eol/` shows a commit). If not, STOP and ask the user to authorize that commit (`prompts/new-feature-standards.md`: "Commit the spec before implementation begins").

---

### Task 1: The `d10_eol` check, its registration, and its notice code

**Files:**
- Create: `check/drupal/d10_eol.py`
- Modify: `check/drupal/__init__.py` (docstring + import + one `add_hook` after d7_eol's)
- Test: `tests/integration/test_check_drupal.py` (append a `d10_eol` section)
- Test: `tests/integration/test_check_drupal_init.py` (`EXPECTED_GATHER_NAMES` + declarations)
- Test: `tests/integration/test_notice_roster.py` (roster entry, size, docstring arithmetic)
- Test: `tests/integration/test_notice_registration.py` (static-literal count 36 → 37, line 100)
- Test: `tests/integration/test_drupal_notice_render.py` (new snapshot test)

**Interfaces:**
- Consumes: contract keys `framework` (str), `drupal_version` (str, `"unknown"` on failed fetch), `end_date` (`datetime.date`); `sc.registry`, `sc.Notice`, `sc.Severity`.
- Produces: `check/drupal/d10_eol.py` with `NOTICE_DRUPAL10_EOL`, `DRUPAL10_EOL: datetime.date`, `check_d10_eol(site_context) -> None`; hook name `check.drupal.d10_eol.check_d10_eol`.

- [ ] **Step 1: Write the failing behavior tests.** Append to `tests/integration/test_check_drupal.py` (add `import datetime` to the imports at the top, alphabetically before `import json`):

```python
# ── d10_eol ───────────────────────────────────────────────────────────────────────────
@pytest.fixture
def d10_eol_mod(psh, request):
    return load_check_module(psh, "drupal", "d10_eol", "drupal_d10_eol_probe", request)


def _d10_ctx(reset_sc, *, end_date, framework="drupal8", drupal_version="10.4.3"):
    ctx = _ctx(reset_sc, framework=framework, drupal_version=drupal_version)
    ctx["end_date"] = end_date
    return ctx


@pytest.mark.parametrize(("end_date", "expected"), [
    (datetime.date(2026, 3, 31), "warning"),
    (datetime.date(2026, 12, 8), "warning"),   # last day before EOL
    (datetime.date(2026, 12, 9), "alert"),     # EOL day itself is ALERT (SPEC D2)
    (datetime.date(2026, 12, 10), "alert"),
])
def test_d10_severity_follows_the_report_date(d10_eol_mod, reset_sc, end_date, expected):
    ctx = _d10_ctx(reset_sc, end_date=end_date)
    d10_eol_mod.check_d10_eol(ctx)
    assert [n["csv"] for n in ctx["notices"]] == [f"{SITE_NAME},drupal10-eol"]
    # Both values are asserted across the cases, so flipping either branch goes red.
    assert ctx["notices"][0]["type"] == expected
    assert ctx["notices"][0]["short"] == "Upgrade to Drupal 11"
    # Tense follows severity (SPEC D5): an ALERT is first mailed after the EOL date has passed.
    verb = "stops getting" if expected == "warning" else "stopped getting"
    assert verb in ctx["notices"][0]["text"]
    assert verb in ctx["notices"][0]["message"]


@pytest.mark.parametrize("version", ["7.1", "9.5", "11.1", "unknown", "1.0", "100.1"])
def test_d10_non_10_versions_get_nothing(d10_eol_mod, reset_sc, version):
    ctx = _d10_ctx(reset_sc, end_date=datetime.date(2026, 12, 10), drupal_version=version)
    d10_eol_mod.check_d10_eol(ctx)
    assert ctx["notices"] == []


def test_d10_non_drupal_framework_does_nothing(d10_eol_mod, reset_sc):
    ctx = _d10_ctx(reset_sc, end_date=datetime.date(2026, 12, 10), framework="wordpress",
                   drupal_version="10.4.3")
    d10_eol_mod.check_d10_eol(ctx)
    assert ctx["notices"] == []
```

- [ ] **Step 2: Run to verify they fail.**
Run: `python -m pytest tests/integration/test_check_drupal.py -k test_d10_ -v`
Expected: 11 tests selected (4 severity + 6 version + 1 framework), all ERROR at fixture setup because `check/drupal/d10_eol.py` does not exist. **Paste the output.** "no tests ran" (exit 5) means the selector is wrong — fix it before going on. (`-k test_d10_` deliberately excludes d7's existing `test_drupal_10_gets_nothing`.)

- [ ] **Step 3: Write the module.** Create `check/drupal/d10_eol.py`:

```python
"""The Drupal 10 end-of-life notice (development/2026-10-30-d10-eol/SPEC.md).

Severity is judged by the REPORT date (site_context["end_date"], i.e. --date), never the wall
clock, so a re-run of an old month renders the same report (SPEC D2)."""

import datetime

import script_context as sc

# Notice code registered at import; see CLAUDE.md § Notices vs. news.
NOTICE_DRUPAL10_EOL = sc.registry.register(
    "drupal10-eol", description="Drupal 10 security support ends December 9, 2026")

# drupal.org core release schedule: "Drupal 10 will reach end of life on December 9, 2026."
DRUPAL10_EOL = datetime.date(2026, 12, 9)

EOL_URL = "https://pantheon.io/learning-center/drupal/10-end-of-life"
EOL_TITLE = "Drupal 10 End of Life Date, Risks and Next Steps"


def check_d10_eol(site_context):
    if not site_context["framework"].startswith("drupal"):
        return
    if not site_context["drupal_version"].startswith("10."):
        return
    before_eol = site_context["end_date"] < DRUPAL10_EOL
    # Tense follows severity: the first ALERT is mailed after December 9 has passed (SPEC D5).
    verb = "stops" if before_eol else "stopped"
    site_context.add_notice(
        sc.Notice(
            severity=sc.Severity.WARNING if before_eol else sc.Severity.ALERT,
            code=NOTICE_DRUPAL10_EOL,
            short="Upgrade to Drupal 11",
            html=f"""
<p><b>Drupal 10 {verb} getting security updates on December 9, 2026.</b>
All Drupal 10 sites should upgrade to Drupal 11. For details, see
Pantheon's <a href="{EOL_URL}">{EOL_TITLE}</a>.</p>
                """,
            text=f"""
Drupal 10 {verb} getting security updates on December 9, 2026.
All Drupal 10 sites should upgrade to Drupal 11. For details,
see Pantheon's {EOL_TITLE} ({EOL_URL}).
                """,
        )
    )
```

- [ ] **Step 4: Run the behavior tests to verify they pass.**
Run: `python -m pytest tests/integration/test_check_drupal.py -v`
Expected: all PASS (existing d7/papc/multisite tests unchanged).

- [ ] **Step 5: Write the failing registration tests.** In `tests/integration/test_check_drupal_init.py`, change `EXPECTED_GATHER_NAMES` to:

```python
EXPECTED_GATHER_NAMES = [
    "check.drupal.papc.check_papc",
    "check.drupal.d7_eol.check_d7_eol",
    "check.drupal.d10_eol.check_d10_eol",
]
```

and append to the end of `test_declarations_match_the_spec_table`:

```python
    d10_eol = gather_hooks["check.drupal.d10_eol.check_d10_eol"]
    assert d10_eol["consumes"] == ["framework", "drupal_version", "end_date"]
    assert d10_eol["produces"] == []
```

In `tests/integration/test_notice_registration.py` line 100, change both `36`s to `37` (`assert len(literals) == 37, f"expected 37 registered code literals, found {len(literals)}"`). This is the second roster-count pin; CLAUDE.md names both files.

In `tests/integration/test_notice_roster.py`: after the `"drupal7-eol",` line add

```python
    # check/drupal/d10_eol.py
    "drupal10-eol",
```

change `assert len(ROSTER) == 36` to `assert len(ROSTER) == 37`, and append to the module docstring's arithmetic paragraph (before the closing `"""`):

```
The 2026-10-30 Drupal 10 EOL notice (development/2026-10-30-d10-eol/) added drupal10-eol in
check/drupal/d10_eol.py: 9 + 28 = 37.
```

- [ ] **Step 6: Run to verify they fail.**
Run: `python -m pytest tests/integration/test_check_drupal_init.py tests/integration/test_notice_roster.py tests/integration/test_notice_registration.py -v`
Expected (measured 2026-10-30 on a scratch copy): `4 failed, 5 passed` — the three `test_check_drupal_init.py` tests (hook not registered) and `test_roster_is_exactly_the_registered_codes` (`roster codes that nothing registers`). `test_notice_registration.py` **passes** here: its static AST count went to 37 the moment Step 3 created the module (it was red between Step 3 and this step's edit), so its red evidence is: before the 36 → 37 edit, with `d10_eol.py` present, it fails with `expected 36 registered code literals, found 37`.

- [ ] **Step 7: Register the hook.** In `check/drupal/__init__.py`: change the import to `from . import d7_eol, d10_eol, multisite, papc`; directly after the d7_eol `sc.add_hook(...)` call add

```python
    sc.add_hook('site_post_gather', {'name': 'check.drupal.d10_eol.check_d10_eol',
                                     'func': d10_eol.check_d10_eol,
                                     'consumes': ['framework', 'drupal_version', 'end_date'],
                                     'produces': []})
```

and change the docstring's `PAPC-module + Drupal-7-EOL/tag1_d7es at\nsite_post_gather.` to `PAPC-module + Drupal-7-EOL/tag1_d7es + Drupal-10-EOL at\nsite_post_gather.` (re-wrap to ≤ 100 cols).

- [ ] **Step 8: Run to verify they pass, plus the DAG.**
Run: `python -m pytest tests/integration/test_check_drupal_init.py tests/integration/test_notice_roster.py tests/integration/test_notice_registration.py tests/integration/test_hook_dag.py -v`
Expected: all PASS (`test_hook_dag.py` proves `end_date` comes from the earlier `site_post_traffic` phase).

- [ ] **Step 9: Add the render snapshot test** (a new snapshot — test-first carve-out). In `tests/integration/test_drupal_notice_render.py` add `import datetime` at the top of the imports, and after `test_drupal7_eol_snapshot` add:

```python
# ── drupal10-eol (check/drupal/d10_eol.py) ───────────────────────────────────────────
# Both severities are pinned: the ALERT render is what every owner sees from the December report on.
@pytest.mark.parametrize(("end_date", "severity"), [
    (datetime.date(2026, 3, 31), "warning"),
    (datetime.date(2026, 12, 10), "alert"),
], ids=["warning", "alert"])
def test_drupal10_eol_snapshot(psh, reset_sc, request, snapshot, end_date, severity):  # noqa: PLR0913 -- snapshot test; args are pytest fixtures + parametrize
    mod = load_check_module(psh, "drupal", "d10_eol", "drupal_d10_eol_snap", request)
    ctx = reset_sc.SiteContext({"name": SITE, "id": SITE_ID})
    ctx["framework"] = "drupal8"
    ctx["drupal_version"] = "10.4.3"
    ctx["end_date"] = end_date
    mod.check_d10_eol(ctx)
    n = next(n for n in ctx["notices"] if n["csv"] == f"{SITE},drupal10-eol")
    assert n["type"] == severity
    assert n["message"] == snapshot
    assert n["text"] == snapshot
    assert n["short"] == snapshot
```

- [ ] **Step 10: Generate and inspect the new snapshot.**
Run: `python -m pytest tests/integration/test_drupal_notice_render.py --snapshot-update -v`
Expected: `6 snapshots generated` (2 cases × message/text/short), the existing ones passed, **0 updated, 0 deleted**. **Paste the output.** Then `git diff tests/integration/__snapshots__/test_drupal_notice_render.ambr` must show only additions under `test_drupal10_eol_snapshot[warning]` and `[alert]`; read them and confirm the warning case says "stops getting" and the alert case "stopped getting", both say "December 9, 2026", "upgrade to Drupal 11", and the exact URL and title. Any modified existing snapshot → stop and report.

- [ ] **Step 11: Lint/type gates on the touched files.**
Run: `uvx ruff@0.15.22 check check/drupal/ tests/integration/test_check_drupal.py tests/integration/test_check_drupal_init.py tests/integration/test_notice_roster.py tests/integration/test_notice_registration.py tests/integration/test_drupal_notice_render.py`
Expected: `All checks passed!` — **paste the output** (fix findings in the code, do not add `noqa` without a justification comment in house style).

- [ ] **Step 12: Commit — only if the user has authorized commits.**

```bash
git add check/drupal/d10_eol.py check/drupal/__init__.py tests/integration/test_check_drupal.py tests/integration/test_check_drupal_init.py tests/integration/test_notice_roster.py tests/integration/test_notice_registration.py tests/integration/test_drupal_notice_render.py tests/integration/__snapshots__/test_drupal_notice_render.ambr
git commit -m "Add Drupal 10 end-of-life notice (check/drupal/d10_eol.py)"
```

---

### Task 2: Pre-declared Drupal golden refresh, docs, operator stats, full gate

**Files:**
- Modify: `tests/e2e/__snapshots__/test_golden_drupal.ambr` (via `--snapshot-update`, after verification)
- Modify: `CLAUDE.md` (`check/drupal/` bullet ~line 684; roster count ~line 846)
- Modify: `monthly-report.txt` (new block below `# Drupal 7 EOL sites:`, ~line 40)

**Interfaces:**
- Consumes: Task 1's registered hook and `drupal10-eol` notice.
- Produces: nothing code-facing.

- [ ] **Step 1: Confirm the golden goes red for the expected reason.**
Run: `python -m pytest tests/e2e/test_golden_drupal.py -v`
Expected: `test_drupal_html_matches_golden` and `test_drupal_txt_matches_golden` FAIL (the site is 10.4.3, `--date 2026-03-31` → WARNING). If they PASS, the check is not reaching the e2e run — stop and investigate (CLAUDE.md § `_CWD_ASSETS`); do not proceed.

- [ ] **Step 2: Verify the diff is ONLY the new notice.** Read the syrupy failure diff from Step 1 (`-vv` if truncated). Every added line must belong to the `drupal10-eol` WARNING notice ("stops getting"; its message/text and warning icon). Measured in review round 1: it renders after the `updates-addons` table (html ~line 489, txt ~line 835 of the snapshot) — default ordering, SPEC D6. No removed lines. Anything else → stop and report; do **not** refresh.

- [ ] **Step 3: Refresh the Drupal golden only.**
Run: `python -m pytest tests/e2e/test_golden_drupal.py --snapshot-update -v`
Expected: 2 snapshots updated, 0 deleted. Then `git diff --stat tests/e2e/__snapshots__/` must list only `test_golden_drupal.ambr`.

- [ ] **Step 4: Update CLAUDE.md.** Replace the `check/drupal/` bullet (starts `` - `check/drupal/` — three generic Drupal checks``) with:

```markdown
- `check/drupal/` — four generic Drupal checks (gated on `[Check.drupal].enabled`, **default
  true**): `multisite.py` (the multisite probe via `sc.drush_php_script`, a `site_post_dns` hook
  that consumes `custom_domains`/`primary_domain` and **produces** the hook-declared keys
  `drupal_multisite`/`drupal_multisite_smell`, read by `psh.cli.resolve_site_url` with `.get()`
  after the phase to seed `drush_smell` and gate the core `no-primary-domain` notice), `papc.py` (delegating to
  `sc.check_drupal_module`), `d7_eol.py` (the `drupal7-eol` notice + the tag1_d7es module
  check) and `d10_eol.py` (the `drupal10-eol` notice: WARNING before 2026-12-09, ALERT on/after,
  judged by the **report date** `end_date`, never the wall clock — so it also consumes
  `end_date`), the latter three at `site_post_gather`, registered multisite → papc → d7_eol →
  d10_eol; each early-returns unless the framework starts with `drupal`.
```

and change `pins the 36-code` to `pins the 37-code`.

- [ ] **Step 4a: Add the operator stats block (SPEC D7).** (Mutating `monthly-report.txt`: first save the user's working copy, `cp monthly-report.txt /tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/monthly-report.user.txt`.) In `monthly-report.txt`, directly after the line `grep drupal7-eol ${TODAY}-notices.csv | sort | perl …` (and before the two blank lines that follow it), insert:

```
# Drupal 10 EOL sites:
grep ,drupal10-eol ${TODAY}-notices.csv | wc -l
grep ,drupal10-eol ${TODAY}-notices.csv | sort | perl -a -n -F, -e 'printf("%-30s %-65s\n", $F[0], $F[1]);'
```

preceded by one blank line. Verify against the **production row shape** (`site,contacts,code`; SPEC §5) in the scratchpad — never a real run:

```bash
cd /tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad && printf 'its-wws-test2,owner@example.edu,drupal10-eol\nbus-paton,x@example.edu,drupal7-eol\n' > x-notices.csv && TODAY=x && grep ,drupal10-eol ${TODAY}-notices.csv | wc -l && grep ,drupal10-eol ${TODAY}-notices.csv | sort | perl -a -n -F, -e 'printf("%-30s %-65s\n", $F[0], $F[1]);'
```

Expected: `1`, then `its-wws-test2` padded to 30 columns followed by `owner@example.edu` (the contacts column, as in the Drupal 7 block). **Paste the output.**

- [ ] **Step 5: Run the full gate.**
Run: `./run-tests`
Expected: ruff green, pyright green, all tests pass (live tier included; if the live tier cannot run in this environment, run `./run-tests --fast` and report that the live tier was not run — never claim it was).

- [ ] **Step 6: Commit — only if the user has authorized commits.**

```bash
# Run /archive-session first (scrubs and writes transcript.md/statistics.md into the folder).
git add tests/e2e/__snapshots__/test_golden_drupal.ambr CLAUDE.md development/2026-10-30-d10-eol/
# Stage ONLY the Drupal 10 block of monthly-report.txt, non-interactively (git add -p is unavailable):
git show HEAD:monthly-report.txt > /tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/mr.head
python3 - /tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/mr.head <<'PY'
import sys
from pathlib import Path
head = Path(sys.argv[1]); s = head.read_text()
anchor = next(l for l in s.splitlines(keepends=True) if l.startswith("grep drupal7-eol "))
block = ("\n# Drupal 10 EOL sites:\n"
         "grep ,drupal10-eol ${TODAY}-notices.csv | wc -l\n"
         "grep ,drupal10-eol ${TODAY}-notices.csv | sort | perl -a -n -F, -e 'printf(\"%-30s %-65s\\n\", $F[0], $F[1]);'\n")
head.with_suffix(".new").write_text(s.replace(anchor, anchor + block, 1))
PY
git diff --no-index /tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/mr.head /tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/mr.new | sed 's#a/tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/mr.head#a/monthly-report.txt#; s#b/tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/mr.new#b/monthly-report.txt#' | git apply --cached
git diff --cached monthly-report.txt   # MUST show only the D10 block; MUST NOT show a TODAY= line
git diff monthly-report.txt            # the unstaged remainder MUST be exactly the user's TODAY= edit
git commit -m "Refresh Drupal golden for the drupal10-eol notice; document d10_eol"
```

---

## Acceptance-criteria run log (pre-implementation, 2026-10-30)

Scratch copy: `/tmp/claude-501/-workspace/d2c7222f-79ec-43a0-aab5-ae74479bfd24/scratchpad/ac` (author) and `…/scratchpad/r2` (round-2 reviewer, independent rebuild). Output tails pasted verbatim:

```
=== Step 2   (python -m pytest -p no:cacheprovider tests/integration/test_check_drupal.py -k test_d10_ -q)
ERROR tests/integration/test_check_drupal.py::test_d10_non_10_versions_get_nothing[100.1]
ERROR tests/integration/test_check_drupal.py::test_d10_non_drupal_framework_does_nothing
17 deselected, 11 errors in 0.89s
=== Step 4
28 passed in 0.72s
=== Step 6
E       AssertionError: roster codes that nothing registers
FAILED tests/integration/test_check_drupal_init.py::test_registers_hooks_when_config_is_silent
FAILED tests/integration/test_check_drupal_init.py::test_registers_hooks_when_explicitly_enabled
FAILED tests/integration/test_check_drupal_init.py::test_declarations_match_the_spec_table
FAILED tests/integration/test_notice_roster.py::test_roster_is_exactly_the_registered_codes
4 failed, 5 passed in 1.41s
=== Step 8
10 passed in 0.99s
=== Step 10
15 snapshots passed. 6 snapshots generated.
7 passed in 0.70s
  <p><b>Drupal 10 stops getting security updates on December 9, 2026.</b>
  Pantheon's <a href="https://pantheon.io/learning-center/drupal/10-end-of-life">Drupal 10 End of Life Date, Risks and Next Steps</a>.</p>
  <p><b>Drupal 10 stopped getting security updates on December 9, 2026.</b>
=== Step 11
All checks passed!
=== mutations (author)
ALERT verb -> "stops"         -> 3 failed, 32 passed in 0.81s
end_date < EOL -> <=          -> 1 failed, 34 passed in 0.77s
startswith("10.") -> ("10")   -> 1 failed, 34 passed in 0.78s
```

Round-2 reviewer additionally: framework guard removed → 1 failed; severities swapped → 6 failed; date text → Dec 7 → 2 failed; hook consuming `savings` (a later phase) → `test_hook_dag.py` red; with §0 simulated, Task 2 Step 1 → `2 failed, 1 passed`, Step 3 → `2 snapshots updated`, diff exactly the WARNING block (html 489, txt 835).

Summary table (superseded by the pasted output above; Step 4a re-run below):

Task 1 was applied verbatim from this plan to a scratch copy of the repo (venv shared) and every
step's command run:

| Step | Real output |
|---|---|
| 2 (red) | `17 deselected, 11 errors` — all 11 `test_d10_*` ERROR at fixture setup (module absent) |
| 4 | `28 passed` |
| 6 (red) | `4 failed, 5 passed` (see Step 6) |
| 8 | `10 passed` |
| 10 | `15 snapshots passed. 6 snapshots generated.`; 0 existing snapshot lines changed; WARNING body "stops getting", ALERT body "stopped getting", correct URL/title |
| 11 | `All checks passed!` |
| 4a | fabricated CSV → `1` and `its-wws-test2   drupal10-eol` |

Mutations on `d10_eol.py` (each must go red): ALERT verb → "stops": `3 failed`; `<` → `<=`:
`1 failed`; `startswith("10.")` → `startswith("10")`: `1 failed`.

**Not runnable yet:** Task 0 and Task 2 Steps 1–3 and 5 depend on the SPEC §0 prerequisite (the
baseline is red: `10 failed, 29 passed` over the goldens + cachecheck render). Round-1 reviewer
measured the Drupal golden diff with/without the hook on one tree: only the new WARNING notice.

**Round-2 fixes, re-run 2026-10-30:**

```
=== Step 4a (production row shape)
1
its-wws-test2                  owner@example.edu
=== Task 2 Step 6 staging recipe (scratch clone of /workspace, working copy = user's TODAY edit + D10 block)
git diff --cached --stat  ->  monthly-report.txt | 4 ++++   (only the "# Drupal 10 EOL sites:" block)
git diff monthly-report.txt  ->  only  -TODAY="20260901" / +TODAY="20261101"
```
