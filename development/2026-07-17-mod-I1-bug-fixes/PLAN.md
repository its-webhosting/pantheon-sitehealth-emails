# I1 Known-Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.
> **This repo overrides the skill's defaults** (`prompts/implementation-standards.md`):
> implementer subagents dispatch as `psh-implementer`, reviewers as `psh-reviewer`, and the
> TDD skill is `mattpocock-skills:tdd` — inject it by name in every implementer brief.

**Goal:** Fix the six CAMPAIGN §10 known bugs in place in `psh/_legacy.py`, each
test-first, with the four e2e goldens byte-identical.

**Architecture:** No modules move (that starts at I2). Where a fix has no seam above the
goldens, the fix's notice-building code is extracted to a pure module-level helper in
`psh/_legacy.py` (the campaign's preserved-bug-extraction pattern, SPEC glossary) and the
bug is fixed at that new unit seam. Dead code is deleted outright.

**Tech Stack:** Python 3.12, pytest (`./run-tests --fast` inner loop), syrupy snapshots.

**Spec:** `development/2026-07-17-mod-I1-bug-fixes/SPEC.md` — the fix definitions (F1–F6),
gate table, and copy decisions live there; this plan sequences them. Line numbers below are
pre-Task-1; later tasks give content anchors because Task 1's deletions shift lines.

## Global Constraints

- The four e2e goldens NEVER change: `git diff -- tests/e2e/__snapshots__/` stays empty
  (SPEC gate table; CAMPAIGN Invariant 1). Never run `--update-goldens` except Task 6's
  NEW snapshot file creation, which touches only `tests/integration/__snapshots__/test_plan_recommendation_notice_render.ambr`.
- Moved f-string literal interiors stay byte-identical; the ONLY allowed interior change
  is the interpolation expression rename (`{site["name"]}` → `{site_name}`, etc.). Never
  re-indent interior lines (CAMPAIGN Invariant 8).
- All edits in `psh/_legacy.py` keep the narrow ruff set green (`E722`,`BLE001`,`S105`,`S106`);
  the file stays in `ruff-broad.toml`'s `extend-exclude` (LEDGER I0 open questions).
- New helpers: module-level defs inserted immediately above `def main():` in
  `psh/_legacy.py`, matching surrounding house style (no new type-annotation styles).
- csv code changes allowed ONLY: `php-eol` → `php-eol-warning`/`php-eol-alert` (Task 3),
  B51 `annual-bill` → `annual-bill-in-progress` (Task 5). Nothing else.
- Commit after each task, conventional commits, `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.
- Inner loop: `./run-tests --fast --llm`. Never `--record`; never `--all`/`--for-real`
  anywhere (interlock).

---

### Task 1: F6 — delete dead code

**Files:**
- Modify: `psh/_legacy.py` (five deletion sites, exact pre-deletion line ranges below)

**Interfaces:** Produces nothing; later tasks assume these lines are gone.

- [ ] **Step 1: Delete the five dead regions** (verify each anchor before deleting; all
  are inside `main()`):
  1. Lines 3568–3634: the commented-out PHP-runtime-Gen2 notice block. Anchor: first line
     `#         # September 2025 - April 2026:`, last line `#             })`.
  2. Lines 4214–4215: `extra_message = ""` / `extra_text = ""` (dead stores — grep shows
     exactly 4 occurrences of these names file-wide, all assignments).
  3. Lines 4236–4250: the `extra_message = f"""…"""` and `extra_text = f"""…"""`
     assignments inside `if alt != site_current_plan:`. KEEP the lines that follow them in
     the same branch (`savings = abs(…)`, `site_recommended_plan = alt`) and the whole
     `else:` (`site_recommended_plan = site_current_plan`, `savings = 0`).
  4. Lines 4124–4133: the commented-out overage-protection debug query (`# if
     sc.options.verbose > 1:` … `#     sc.debug('-----')`). KEEP the live comment line
     above it (`# Load the overage protection data …`).
  5. Line 4107: `# plt.show()`; and line 4717: `plt.close(fig)  # needed to free up
     memory when sc.options.all is True` (stale claim — `fig` is closed at 4113; nothing
     creates a figure in between).

- [ ] **Step 2: Verify** — run:
  - `grep -n "extra_message\|extra_text\|plt.show" psh/_legacy.py` → no hits.
  - `grep -c "plt.close(fig)" psh/_legacy.py` → `1`.
  - `./run-tests --fast --llm` → all green (727 passed baseline / 1 skipped), 25 snapshots
    passed, goldens untouched.

- [ ] **Step 3: Commit**

```bash
git add psh/_legacy.py
git commit -m "fix(campaign-I1): delete dead code (Gen2 notice block, dead stores, stale plt calls)"
```

*No tests — SPEC F6 states the deletion-only carve-out and why.*

---

### Task 2: F1 — composer-smell nesting + wrong variable

**Files:**
- Modify: `psh/_legacy.py` (extract the three smell blocks; anchor: `if wp_smell != "":`
  inside `main()`, immediately after `estimate_end_date = estimate_start_date.replace(…)`)
- Create: `tests/unit/test_smell_notices.py`

**Interfaces:**
- Produces: `psh._legacy.build_smell_notices(site_name, wp_smell, drush_smell,
  composer_smell) -> list[dict]` (tests reach it via the `psh` fixture as
  `psh.build_smell_notices`).

- [ ] **Step 1: Preserved-bug extraction.** Insert above `def main():`:

```python
def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell):
    """Return the list of smell notice dicts (possibly empty) for one site."""
    notices = []
    if wp_smell != "":
        notices.append({ … })      # MOVE-VERBATIM: the wp-smell dict from main()
    if drush_smell != "":
        notices.append({ … })      # MOVE-VERBATIM: the drush-smell dict
        if composer_smell != "":   # (bug preserved for the red step)
            notices.append({ … })  # MOVE-VERBATIM: the composer-smell dict
    return notices
```

MOVE-VERBATIM = cut the dict literal from `main()`, do not retype it; the only interior
change is `{site["name"]}` → `{site_name}` (renders identically). Do NOT touch the
composer literals' baked-in 8-space indentation (SPEC Observations 4). Replace the three
blocks in `main()` with:

```python
site_context.add_notices(
    build_smell_notices(site["name"], wp_smell, drush_smell, composer_smell)
)
```

Run `./run-tests --fast --llm` → green (behavior-preserving; goldens contain zero smell
notices — CAMPAIGN §10 grep).

- [ ] **Step 2: Write the failing tests** — `tests/unit/test_smell_notices.py`:

```python
"""build_smell_notices unit tests (campaign I1, SPEC F1)."""
import pytest

pytestmark = pytest.mark.unit


def test_no_smells_returns_empty_list(psh):
    assert psh.build_smell_notices("s", "", "", "") == []


def test_wp_smell_alone(psh):
    (n,) = psh.build_smell_notices("s", "wp broke", "", "")
    assert n["csv"].startswith("s,wp-smell,")
    assert "wp broke" in n["message"] and "wp broke" in n["text"]


def test_drush_smell_alone(psh):
    (n,) = psh.build_smell_notices("s", "", "drush broke", "")
    assert n["csv"].startswith("s,drush-smell,")
    assert "drush broke" in n["message"] and "drush broke" in n["text"]


def test_composer_smell_alone_is_reported(psh):
    # RED pre-fix: the composer block was nested inside the drush check, so a composer
    # smell without a drush smell was silently dropped.
    (n,) = psh.build_smell_notices("s", "", "", "composer broke")
    assert n["csv"].startswith("s,composer-smell,")


def test_composer_html_interpolates_composer_not_drush(psh):
    # RED pre-fix: the composer html body interpolated {drush_smell}.
    notices = psh.build_smell_notices("s", "", "drush text", "composer text")
    composer = [n for n in notices if n["csv"].startswith("s,composer-smell,")][0]
    assert "composer text" in composer["message"]
    assert "drush text" not in composer["message"]


def test_all_three_in_emission_order(psh):
    notices = psh.build_smell_notices("s", "w", "d", "c")
    codes = [n["csv"].split(",")[1] for n in notices]
    assert codes == ["wp-smell", "drush-smell", "composer-smell"]
```

- [ ] **Step 3: Run and watch the two RED tests fail for the right reason**

Run: `./run-tests --fast tests/unit/test_smell_notices.py -v`
Expected: `test_composer_smell_alone_is_reported` FAILS (ValueError unpacking empty list)
and `test_composer_html_interpolates_composer_not_drush` FAILS (`"drush text" in
message`); the other four PASS.

- [ ] **Step 4: Fix.** In `build_smell_notices`: dedent `if composer_smell != "":` to be a
sibling of the drush check (code indentation only — literal interiors untouched), and in
the composer html body change `{html.escape(drush_smell)}` → `{html.escape(composer_smell)}`.

- [ ] **Step 5: Run tests, all green; then full fast tier**

Run: `./run-tests --fast --llm` → all green, goldens untouched.

- [ ] **Step 6: Commit**

```bash
git add psh/_legacy.py tests/unit/test_smell_notices.py
git commit -m "fix(campaign-I1): report composer smells without a drush smell, with the right text"
```

---

### Task 3: F2 — distinct php-eol csv codes

**Files:**
- Modify: `psh/_legacy.py` (anchor: comment `# April 2026 - September 2026:` + the
  `if envs["live"]["php_version"] in ("7.4", "8.1"):` / `elif … < "8.2":` blocks)
- Create: `tests/unit/test_php_eol_notice.py`

**Interfaces:**
- Produces: `psh.build_php_eol_notice(site_name, php_version) -> dict | None`.

- [ ] **Step 1: Preserved-bug extraction.** Insert above `def main():`:

```python
def build_php_eol_notice(site_name, php_version):
    """Return the PHP-EOL notice dict for php_version, or None when no notice is needed."""
    if php_version in ("7.4", "8.1"):
        return { … }   # MOVE-VERBATIM: the warning dict ({site["name"]} -> {site_name},
                       #   {envs["live"]["php_version"]} -> {php_version})
    if php_version < "8.2":
        new_php = "7.4" if php_version.startswith("7") else "8.1"
        return { … }   # MOVE-VERBATIM: the alert dict, same interpolation renames
    return None
```

(Preserve as-is, on purpose: the string comparison and KeyError-on-missing-key behavior —
SPEC F2 / Observations 2.) Replace the if/elif in `main()` with (keeping the two comment
lines above it in place):

```python
php_eol_notice = build_php_eol_notice(site["name"], envs["live"]["php_version"])
if php_eol_notice is not None:
    site_context.add_notice(php_eol_notice)
```

Run `./run-tests --fast --llm` → green (golden fixtures report PHP 8.2 → None path).

- [ ] **Step 2: Write the failing test** — `tests/unit/test_php_eol_notice.py`:

```python
"""build_php_eol_notice unit tests (campaign I1, SPEC F2)."""
import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("version", ["7.4", "8.1"])
def test_deprecated_versions_warn(psh, version):
    n = psh.build_php_eol_notice("s", version)
    assert n["type"] == "warning"
    assert n["csv"] == "s,php-eol-warning"
    assert version in n["message"] and version in n["text"]


@pytest.mark.parametrize("version,fallback", [("8.0", "8.1"), ("7.0", "7.4")])
def test_older_versions_alert_with_fallback(psh, version, fallback):
    n = psh.build_php_eol_notice("s", version)
    assert n["type"] == "alert"
    assert n["csv"] == "s,php-eol-alert"
    assert f"PHP {fallback}" in n["message"] and f"PHP {fallback}" in n["text"]


@pytest.mark.parametrize("version", ["8.2", "8.3"])
def test_current_versions_need_no_notice(psh, version):
    assert psh.build_php_eol_notice("s", version) is None


def test_warning_and_alert_codes_are_distinct(psh):
    # RED pre-fix: both branches emitted the identical "s,php-eol", so the notices CSV
    # could not distinguish severity.
    warn = psh.build_php_eol_notice("s", "8.1")["csv"]
    alert = psh.build_php_eol_notice("s", "8.0")["csv"]
    assert warn != alert
```

- [ ] **Step 3: Run and watch RED** — `./run-tests --fast tests/unit/test_php_eol_notice.py -v`
Expected: the two `csv ==` assertions and `test_warning_and_alert_codes_are_distinct`
FAIL (`s,php-eol` on both branches); type/fallback/None tests PASS.

- [ ] **Step 4: Fix.** Warning branch csv → `f"{site_name},php-eol-warning"`; alert
branch csv → `f"{site_name},php-eol-alert"`. Nothing else changes.

- [ ] **Step 5: Run tests, all green; then full fast tier** — `./run-tests --fast --llm`.

- [ ] **Step 6: Commit**

```bash
git add psh/_legacy.py tests/unit/test_php_eol_notice.py
git commit -m "fix(campaign-I1): distinguish php-eol warning vs alert in the notices CSV"
```

---

### Task 4: F3 — unknown-framework site_results entry

**Files:**
- Create: `tests/fixtures/terminus-unknownfw/` (copy of `tests/fixtures/terminus/`, one
  value edited) + `tests/fixtures/terminus-unknownfw/README.md`
- Modify: `tests/conftest.py` (one constant, next to `TERMINUS_FIXTURES_DRUPAL`)
- Create: `tests/e2e/test_unknown_framework_e2e.py`
- Modify: `psh/_legacy.py` (the `else:` branch printing `ATTENTION: unknown framework`)

**Interfaces:**
- Produces: `conftest.TERMINUS_FIXTURES_UNKNOWNFW` (Path).

- [ ] **Step 1: Build the fixture dir.** `cp -r tests/fixtures/terminus
tests/fixtures/terminus-unknownfw`. Identify the `org:site:list` fixture (`grep -l
'"framework"' tests/fixtures/terminus-unknownfw/*.json`; it is the file whose recorded
argv in the JSON is the `org:site:list` invocation — confirm by reading it, do not
guess). In that file only, change `its-wws-test1`'s `framework` value (currently
`"wordpress"`) to `"mystery"`. Add `README.md`:

```markdown
# terminus-unknownfw — hand-derived fixtures (do not `--record`)

A copy of `tests/fixtures/terminus/` with exactly one edit: the `org:site:list`
fixture's `framework` for its-wws-test1 is `"mystery"`, driving `main()`'s
unknown-framework branch (campaign I1, SPEC F3).  Like `terminus-cdnchange/`, this
directory is hand-maintained: `./run-tests --record` refreshes only `terminus/` and
`terminus-drupal/`, so keep this copy in sync by hand if those are ever re-recorded.
```

- [ ] **Step 2: Add the conftest constant** after `TERMINUS_FIXTURES_DRUPAL`:

```python
TERMINUS_FIXTURES_UNKNOWNFW = FIXTURES / "terminus-unknownfw"
```

- [ ] **Step 3: Write the failing e2e test** — `tests/e2e/test_unknown_framework_e2e.py`:

```python
"""Offline e2e for the unknown-framework path (campaign I1, SPEC F3).

{ymd}-results.json is written only on --all runs (which the interlock bans), but the
non---all path of finish_run() pprints the same site_results dict to stdout -- that is
the observable this test pins.
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    TERMINUS_FIXTURES_UNKNOWNFW,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e


def test_unknown_framework_site_appears_in_site_results(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "test.db")
    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(MINIMAL_CONFIG)],
        cwd=work,
        fixtures_dir=TERMINUS_FIXTURES_UNKNOWNFW,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    # Pre-fix behavior that must survive: the operator banner.
    assert "unknown framework" in proc.stdout
    # The fix: the site's entry in the pprinted site_results.  RED pre-fix ({} printed;
    # the banner contains "mystery" but never the quoted-key fragment).
    assert "'framework': 'mystery'" in proc.stdout
    assert "'version': 'unknown'" in proc.stdout
```

- [ ] **Step 4: Run and watch RED** — `./run-tests --fast tests/e2e/test_unknown_framework_e2e.py -v`
Expected: FAIL on `"'framework': 'mystery'" in proc.stdout`; returncode 0 and the banner
assertion PASS. **If instead returncode != 0**: the unknown-framework render path is
broken beyond the named bug — STOP, report DONE_WITH_CONCERNS with the stderr; do not
widen the fix unilaterally.

- [ ] **Step 5: Fix.** In `main()`'s `else:` branch, after the existing
`sc.console.print(f":exclamation: [bold red] ATTENTION: unknown framework …")`:

```python
                site_results[site["name"]] = {
                    "framework": site["framework"],
                    "version": "unknown",
                    "plan_name": site["plan_name"],
                }
```

- [ ] **Step 6: Run tests, all green; then full fast tier** — `./run-tests --fast --llm`.

- [ ] **Step 7: Commit**

```bash
git add psh/_legacy.py tests/conftest.py tests/e2e/test_unknown_framework_e2e.py tests/fixtures/terminus-unknownfw
git commit -m "fix(campaign-I1): record unknown-framework sites in site_results"
```

---

### Task 5: F5 — distinct annual-bill csv codes

**Files:**
- Modify: `psh/_legacy.py` (anchors: `if end_of_contract_year and umich_enabled():` and
  the `# TODO: remove this section at the beginning of August 2026:` block)
- Create: `tests/unit/test_annual_billing_notices.py`

**Interfaces:**
- Produces: `psh.build_annual_bill_upcoming_notice(site_name, plan_name, annual_bill,
  shortcode, portal_site_id) -> dict` and
  `psh.build_annual_bill_in_progress_notice(site_name, plan_name, annual_bill, shortcode)
  -> dict`.

- [ ] **Step 1: Preserved-bug extraction.** Insert above `def main():`:

```python
def build_annual_bill_upcoming_notice(site_name, plan_name, annual_bill, shortcode, portal_site_id):
    """The contract-year-end "will be billed July 1" alert (BLOCKMAP B50)."""
    return { … }   # MOVE-VERBATIM: the B50 dict; renames {site["name"]} -> {site_name},
                   #   {site["plan_name"]} -> {plan_name}


def build_annual_bill_in_progress_notice(site_name, plan_name, annual_bill, shortcode):
    """The "ITS is in the process of billing" alert (BLOCKMAP B51; deletion is I12's call)."""
    return { … }   # MOVE-VERBATIM: the B51 dict, same renames
```

In `main()`, both blocks keep their conditions, comments (including the `TODO: remove …
August 2026` line), subject logic, and `shortcode`/`annual_bill` lookups; each
`sorted_notices.insert(0, { … })` becomes:

```python
                sorted_notices.insert(
                    0,
                    build_annual_bill_upcoming_notice(
                        site["name"], site["plan_name"], annual_bill, shortcode, portal_site_id
                    ),
                )
```

and, in the second block:

```python
                sorted_notices.insert(
                    0,
                    build_annual_bill_in_progress_notice(
                        site["name"], site["plan_name"], annual_bill, shortcode
                    ),
                )
```

Run `./run-tests --fast --llm` → green (goldens are umich-disabled; zero annual-bill
occurrences — CAMPAIGN §10).

- [ ] **Step 2: Write the failing test** — `tests/unit/test_annual_billing_notices.py`:

```python
"""Annual-billing notice builders (campaign I1, SPEC F5)."""
import pytest

pytestmark = pytest.mark.unit


def _upcoming(psh):
    return psh.build_annual_bill_upcoming_notice("s", "Performance Small", 500.0, "SC123", 42)


def _in_progress(psh):
    return psh.build_annual_bill_in_progress_notice("s", "Performance Small", 500.0, "SC123")


def test_codes_are_distinct(psh):
    # RED pre-fix: both notices emitted "annual-bill", so a June U-M run wrote two
    # indistinguishable CSV rows for the same site.
    assert _upcoming(psh)["csv"].split(",")[1] != _in_progress(psh)["csv"].split(",")[1]


def test_upcoming_notice_shape(psh):
    n = _upcoming(psh)
    assert n["type"] == "alert"
    assert n["csv"] == "s,annual-bill,500.0,SC123"
    assert "will be billed" in n["short"]
    assert "/sites/42/plan/" in n["message"] and "/sites/42/edit/" in n["message"]


def test_in_progress_notice_shape(psh):
    n = _in_progress(psh)
    assert n["type"] == "alert"
    assert n["csv"] == "s,annual-bill-in-progress,500.0,SC123"
    assert "in the process of billing" in n["message"]
    assert "in the process of billing" in n["text"]
```

- [ ] **Step 3: Run and watch RED** — `./run-tests --fast tests/unit/test_annual_billing_notices.py -v`
Expected: `test_codes_are_distinct` and `test_in_progress_notice_shape` FAIL (csv still
`s,annual-bill,…`); the others PASS.

- [ ] **Step 4: Fix.** In `build_annual_bill_in_progress_notice` only, csv →
`f"{site_name},annual-bill-in-progress,{annual_bill},{shortcode}"`.

- [ ] **Step 5: Run tests, all green; then full fast tier** — `./run-tests --fast --llm`.

- [ ] **Step 6: Commit**

```bash
git add psh/_legacy.py tests/unit/test_annual_billing_notices.py
git commit -m "fix(campaign-I1): give the transitional annual-billing notice its own csv code"
```

---

### Task 6: F4 — gate the U-M portal URL in the plan-recommendation notice

**Files:**
- Modify: `psh/_legacy.py` (anchor: the `else:` branch adding the `its-recommends-plan`
  notice, inside the cost-model section)
- Create: `tests/unit/test_plan_recommendation_notice.py`
- Create: `tests/integration/test_plan_recommendation_notice_render.py` (+ its new
  `.ambr` snapshot, creation carve-out)

**Interfaces:**
- Produces: `psh.build_plan_recommendation_notice(site_name, current_plan,
  recommended_plan, savings, portal_site_id, umich) -> dict`.

- [ ] **Step 1: Preserved-bug extraction.** Insert above `def main():`:

```python
def build_plan_recommendation_notice(site_name, current_plan, recommended_plan, savings,
                                     portal_site_id, umich):
    """The its-recommends-plan notice.  umich selects the U-M (portal-linked) or generic copy."""
    return {
        "type": "info",
        "icon": "&#x1F50E;",  # magnifying glass
        "csv": f"{site_name},its-recommends-plan,{current_plan},{recommended_plan},{savings:,.2f}",
        "short": "plan change recommended",
        "message": f""" … """,   # MOVE-VERBATIM: current html body; renames
                                 #   {site["name"]} -> {site_name}, {site["plan_name"]} -> {current_plan},
                                 #   {site_recommended_plan} -> {recommended_plan}
        "text": f""" … """,      # MOVE-VERBATIM: current text body, same renames
    }
```

(`umich` is accepted but unused at this step — the preserved bug.) Call site in `main()`
(the `else:` branch that added this notice):

```python
                        site_context.add_notice(
                            build_plan_recommendation_notice(
                                site["name"], site["plan_name"], site_recommended_plan,
                                savings, portal_site_id, umich_enabled(),
                            )
                        )
```

Run `./run-tests --fast --llm` → green (the recommendation e2e keeps recommended ==
current, so this notice is in no golden).

- [ ] **Step 2: Write the failing test** — `tests/unit/test_plan_recommendation_notice.py`:

```python
"""build_plan_recommendation_notice unit tests (campaign I1, SPEC F4)."""
import pytest

pytestmark = pytest.mark.unit


def _notice(psh, umich):
    return psh.build_plan_recommendation_notice(
        "s", "Performance Medium", "Performance Small", 1234.5, 42, umich
    )


def test_umich_variant_links_the_portal(psh):
    n = _notice(psh, umich=True)
    assert "admin.webservices.umich.edu/sites/42/plan/" in n["message"]
    assert "admin.webservices.umich.edu/sites/42/plan/" in n["text"]


def test_generic_variant_has_no_umich_urls(psh):
    # RED pre-fix: the portal URL rendered un-gated, with portal_site_id=0 on non-U-M runs.
    n = _notice(psh, umich=False)
    assert "admin.webservices" not in n["message"] and "admin.webservices" not in n["text"]
    # The June 16-30 downgrade window is U-M portal billing policy (SPEC F4):
    assert "June 16" not in n["message"] and "June 16" not in n["text"]
    # The recommendation itself still reads through:
    assert "Performance Small" in n["message"] and "$1,234.50" in n["text"]


def test_csv_is_variant_independent(psh):
    assert _notice(psh, True)["csv"] == _notice(psh, False)["csv"] == (
        "s,its-recommends-plan,Performance Medium,Performance Small,1,234.50"
    )
```

- [ ] **Step 3: Run and watch RED** — `./run-tests --fast tests/unit/test_plan_recommendation_notice.py -v`
Expected: `test_generic_variant_has_no_umich_urls` FAILS (`admin.webservices` present);
the other two PASS.

- [ ] **Step 4: Fix — add the generic variant.** In the helper, build `message`/`text`
per variant; U-M strings are the MOVE-VERBATIM ones from Step 1, generic strings are
exactly (SPEC F4's copy decision):

```python
    if umich:
        message = f""" … """   # the Step-1 U-M html, unchanged
        text = f""" … """      # the Step-1 U-M text, unchanged
    else:
        message = f"""
<p>Moving <strong>{site_name}</strong>
to Pantheon's <strong>{recommended_plan}</strong> plan may save you up to <strong>${savings:,.2f}</strong>
over the coming year if the site's traffic for the next 12 months is similar to the previous 12.</p>
<p>You may want to stay on the <strong>{current_plan}</strong> plan if the site has had one-time traffic spikes
or you think site traffic will be decreasing soon.</p>
"""
        text = f"""
Moving {site_name} to Pantheon's {recommended_plan} plan
may save you up to ${savings:,.2f} over the coming year if the site's
traffic for the next 12 months is similar to the previous 12.

You may want to stay on the {current_plan} plan if the site
has had one-time traffic spikes or you think site traffic will be
decreasing soon.
"""
```

- [ ] **Step 5: Run tests, all green** — the unit file, then `./run-tests --fast --llm`.

- [ ] **Step 6: Snapshot pin (creation carve-out).** Create
`tests/integration/test_plan_recommendation_notice_render.py`:

```python
"""Syrupy pin of both its-recommends-plan variants (campaign I1, SPEC F4)."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_plan_recommendation_render(psh, snapshot, umich):
    assert psh.build_plan_recommendation_notice(
        "s", "Performance Medium", "Performance Small", 1234.5, 42, umich
    ) == snapshot
```

Run `./run-tests --fast --update-goldens tests/integration/test_plan_recommendation_notice_render.py`,
then **review the new `.ambr` byte-by-byte**: the umich snapshot must equal today's copy
(diff its strings against the pre-extraction literals in git: `git show
HEAD~1:psh/_legacy.py`), the generic snapshot must differ only by the two named edits.
Confirm no OTHER `.ambr` changed: `git status tests` shows only the new files.

- [ ] **Step 7: Full fast tier green** — `./run-tests --fast --llm`.

- [ ] **Step 8: Commit**

```bash
git add psh/_legacy.py tests/unit/test_plan_recommendation_notice.py \
  tests/integration/test_plan_recommendation_notice_render.py \
  tests/integration/__snapshots__/test_plan_recommendation_notice_render.ambr
git commit -m "fix(campaign-I1): gate the U-M portal URL out of the generic plan-recommendation notice"
```

---

### Task 7: increment close (controller, not a subagent)

- [ ] `/code-review` over the whole increment range; apply findings via `psh-implementer`
  fix-subagents.
- [ ] Full `./run-tests` (with live tier if credentials present; else `--fast` + ledger
  note). Paste outputs into SPEC.md § ACCEPTANCE RESULTS, plus
  `git diff aa8afd1 -- tests/e2e/__snapshots__/` (must be empty).
- [ ] Append the LEDGER.md I1 entry (CAMPAIGN §12 template): moved = none (helpers are
  in-file); csv additions `php-eol-warning`/`php-eol-alert`/`annual-bill-in-progress`;
  deviations; SPEC Observations 1–4 dispositioned (1 → I12/I14 note, 2 → I8, 3 → I7,
  4 → I10); new fixture dir noted for Invariant 10.
- [ ] Final commit includes `development/2026-07-17-mod-I1-bug-fixes/` + ledger.
- [ ] `/archive-session`.
