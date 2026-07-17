# I3 — Configuration module + Notice class — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement
> this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch every
> code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via `mattpocock-skills:tdd`
> (NOT superpowers TDD). The authoritative design is `SPEC.md` in this folder — read it in full; this
> plan is the step sequence, the SPEC is the rationale/invariants.

**Goal:** Move the config-substitution / section-gating / news-loading / feature-flag functions into a
new gated `psh/configuration.py`, and introduce the typed `Notice` model in a new `psh/notice.py`
(adopting it for one PoC notice), with the four e2e goldens byte-identical throughout.

**Architecture:** Import-back move (mirrors I2's gateway): the six functions move to a new file that
`psh/_legacy.py` re-imports, so call sites resolve unchanged. `psh/notice.py` is a pure stdlib-only
module (no `sc` dependency, gated from birth); `script_context.py` imports it so `SiteContext.add_notice`
accepts a `Notice` and `sc.Notice`/`sc.Severity` exist. The `no-domains` notice is converted to a
`Notice` end-to-end as a golden-verified proof of concept.

**Tech Stack:** Python 3.12+, ruff (`ruff-broad.toml` `select=ALL`), pyright (standard), pytest, syrupy.

## Global Constraints

- **Four e2e goldens byte-identical** (CAMPAIGN Invariant 1). `--update-goldens` is FORBIDDEN. Verify
  `git diff 45b8a88 HEAD -- tests/e2e/__snapshots__/` is empty at each task end.
- **New files pass the full gate**: `psh/configuration.py` and `psh/notice.py` MUST pass
  `ruff check --config ruff-broad.toml <file>` → "All checks passed!" and pyright standard → 0 errors.
- **Run pyright via `./run-tests`, NOT `uv run pyright`** — the latter re-resolves and churns `uv.lock`.
  If `uv.lock` shows as modified, `git checkout -- uv.lock` before committing.
- **No `sc` name removed**, only `Notice`/`Severity` added (Invariant 9). No phase/lifecycle/DB code
  moves. Interior bytes of notice `f"""` literals never shift (Invariant 8).
- **Safety interlock**: no `--all`/`--for-real`/live `--create-tables` in tests.
- Clear any stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 process note).
- Baseline commit (I3 start) = `45b8a88`.
- Every task report cites the Spine directives applied by number with a verbatim quote (agent config).

---

### Task 1: `psh/configuration.py` (the config-machinery move)

**Files:**
- Create: `psh/configuration.py`
- Modify: `psh/_legacy.py` (remove the six defs + DEFER machinery; add the import-back)
- Modify: `script_context.py:9-10` (annotate `options`/`config`; add `import argparse`, `from typing import Any`)
- Test: `tests/unit/test_news.py` (add one folder-ordering pin test)

**Interfaces:**
- Produces: `psh.configuration.config_substitution(expr, path) -> str`,
  `process_config(data, path="", *, deferred_pass=False) -> Any`,
  `gate_disabled_sections(config: dict) -> dict`, `load_news_items() -> None`,
  `umich_enabled() -> bool`, `cloudflare_enabled() -> bool`. All re-imported into `psh/_legacy.py`, so
  `psh.<name>` (test `psh` fixture) and `sc.umich_enabled`/`sc.cloudflare_enabled` resolve unchanged.

- [ ] **Step 1: Write the folder-ordering pin test (guards the PTH207 conversion)**

Add to `tests/unit/test_news.py`:

```python
def test_folder_items_sorted_by_filename(psh, reset_sc, tmp_path):
    # Pin the within-folder sort order BEFORE the glob->Path.glob conversion (SPEC §New tests #4).
    # Files created in a non-lexical order; a dropped sorted() would surface OS readdir order.
    for name, msg in (("c.toml", "CCC"), ("a.toml", "AAA"), ("b.toml", "BBB")):
        (tmp_path / name).write_text(
            f'[News.item]\ntype = "info"\nmessage = "{msg}"\n'
        )
    reset_sc.config = {"News": {"folder": str(tmp_path)}}
    psh.load_news_items()
    assert [n["message"] for n in reset_sc.news] == ["AAA", "BBB", "CCC"]
```

- [ ] **Step 2: Run it — confirm it PASSES on the current (pre-move) code**

Run: `./run-tests --fast tests/unit/test_news.py::test_folder_items_sorted_by_filename`
Expected: PASS. (This is a *pinning* test for existing behavior — SPEC §New tests #4 — so it is green
now and must stay green after the PTH conversion; it is not a red→green cycle.)

- [ ] **Step 3: Create `psh/configuration.py` with the six defs + DEFER machinery moved**

Create `psh/configuration.py`. Move **verbatim** from `psh/_legacy.py`:
- `config_substitution` (516–600), the DEFER machinery (`_DEFER_TAG` + the two regexes, 603–608),
  `process_config` (611–634), `gate_disabled_sections` (637–656), `load_news_items` (933–976),
  `umich_enabled` (1332–1344), `cloudflare_enabled` (1347–1355).

Apply exactly these edits to the moved bodies (SPEC §Broad-ruff findings / §Pyright findings — nothing
else changes):

1. Module docstring + import block (note: **no `import glob`** — orphaned by the PTH207 fix):
   ```python
   """Configuration engine: <{ ... }> substitution (two-pass, with DEFER), section gating, news
   loading, and the umich/cloudflare feature flags.  Moved from psh/_legacy.py at campaign I3; the
   remnant re-imports these names so its call sites resolve unchanged (CAMPAIGN.md §3.1)."""
   import re
   import shlex
   import sys
   import tomllib
   from pathlib import Path
   from typing import Any

   from rich.markup import escape
   from rich.pretty import pprint

   import script_context as sc
   ```
2. `config_substitution` def line gets the complexity suppressions (inline reason required):
   ```python
   def config_substitution(expr: str, path) -> str:  # noqa: C901, PLR0912, PLR0915 -- best-match scorer moved behavior-preserving; restructuring is a review activity, not part of a move (I2 run_terminus precedent). Covered by tests/unit/test_config_substitution.py.
   ```
3. Annotate `best_match` and narrow it for pyright:
   - change `best_match = None` → `best_match: dict[str, Any] | None = None`
   - immediately inside `if best_match_score == argc:` (before the `func_args = [...]` build) add:
     `assert best_match is not None  # best_match_score > 0 implies best_match was assigned`
   - immediately before the final `sc.console.print(f"[bold red]best match: {best_match['args']}")`
     add the same `assert best_match is not None` line.
4. The two `sc.options.verbose` comparisons get inline `# noqa: PLR2004` with reason, e.g.:
   ```python
   if sc.options.verbose > 1:  # noqa: PLR2004 -- verbosity level (-v/-vv/-vvv) is a raw domain constant used identically across the remnant
   ...
   if sc.options.verbose >= 2:  # noqa: PLR2004 -- same: verbosity threshold, not a magic number to name
   ```
5. `process_config` — make `deferred_pass` keyword-only and update the two recursive calls:
   ```python
   def process_config(data: Any, path="", *, deferred_pass=False) -> Any:
   ...
       data[key] = process_config(value, new_path, deferred_pass=deferred_pass)
   ...
       data[index] = process_config(item, new_path, deferred_pass=deferred_pass)
   ```
6. `load_news_items` — the three PTH/SIM fixes:
   - `for news_item_name in n["News"].keys():` → `for news_item_name in n["News"]:`  (SIM118)
   - `for filename in sorted(glob.glob(f"{folder}/*.toml")):` → `for filename in sorted(Path(folder).glob("*.toml")):`  (PTH207)
   - `with open(filename, "rb") as f:` → `with filename.open("rb") as f:`  (PTH123)

- [ ] **Step 4: Remove the moved defs from `psh/_legacy.py` and add the import-back**

Delete the seven moved items from `psh/_legacy.py` (516–656 block covering `config_substitution` +
DEFER machinery + `process_config` + `gate_disabled_sections`; 933–976 `load_news_items`; 1332–1355
`umich_enabled`/`cloudflare_enabled`). Add near the top of `psh/_legacy.py` (with the other
`from psh.<mod> import` lines, e.g. beside the `from psh.gateway import …` block):

```python
from psh.configuration import (
    cloudflare_enabled,
    config_substitution,
    gate_disabled_sections,
    load_news_items,
    process_config,
    umich_enabled,
)
```

Verify with grep that no `psh/_legacy.py` import became orphaned (expect none — `glob`/`tomllib`/`re`/
`shlex`/`sys`/`Any`/`escape`/`pprint` all have other users). Remove only what this change orphans.

- [ ] **Step 5: Fix `script_context.py` typing so `configuration.py` passes pyright**

In `script_context.py`, add the two imports (top of file, after `import sys`) and annotate the two
globals (SPEC §Pyright findings — required, or the annotations `NameError` at import):

```python
import argparse
import sys
from typing import Any
...
options: argparse.Namespace = argparse.Namespace()  # parsed CLI options; set by parse_args() caller
config: dict[str, Any] = {}                          # parsed pantheon-sitehealth-emails.toml
```

(Do NOT retype anything else in `script_context.py`.)

- [ ] **Step 6: Gate the new file — paste findings, then confirm clean**

Run: `uvx ruff check --config ruff-broad.toml psh/configuration.py`
Expected: after the edits, "All checks passed!". **Also run it once WITHOUT the `# noqa`s** (or read the
pre-suppression list) and paste the raw findings in the task report, confirming each `# noqa` code
matches a real finding (RUF100 guard, SPEC §RUF100).

- [ ] **Step 7: Run the full fast suite + goldens + pyright**

Run: `./run-tests --fast`
Expected: all three gates green (ruff narrow, ruff broad, pyright 0 errors); the ~11 existing
`test_config_substitution.py`/`test_news.py`/`test_section_gating.py` cases pass unchanged; the new
`test_folder_items_sorted_by_filename` passes; four goldens byte-identical. If `uv.lock` shows
modified: `git checkout -- uv.lock`.

Run: `git diff 45b8a88 -- tests/e2e/__snapshots__/`  → Expected: empty.

- [ ] **Step 8: Commit**

```bash
git add psh/configuration.py psh/_legacy.py script_context.py tests/unit/test_news.py
git commit -m "refactor(campaign-I3): extract the config engine into psh/configuration.py"
```

---

### Task 2: `psh/notice.py` + `add_notice` + the `no-domains` PoC

**Files:**
- Create: `psh/notice.py`
- Create: `tests/unit/test_notice.py`
- Create: `tests/unit/test_add_notice_from_notice.py`
- Modify: `script_context.py` (import `Notice`/`Severity`; teach `add_notice`; add `_notice_to_dict`)
- Modify: `psh/_legacy.py` (import from `psh.notice`; register `no-domains`; convert the notice at ~2551)
- Modify: `tests/unit/test_house_rules.py` (extend `SC_FACADE_NAMES`)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `psh.notice.Severity` (StrEnum ALERT/WARNING/INFO), `Notice` (frozen dataclass:
  `severity, code, html, short="", text="", icon="", order="append"`), `NoticeRegistry` (`.register(code, *, description="") -> str`,
  `.codes() -> frozenset[str]`), `DuplicateNoticeCodeError`, module-level `registry`.
  `sc.Notice`/`sc.Severity` (via `script_context.py`'s import). `SiteContext.add_notice(Notice | dict)`.

- [ ] **Step 1: Write `tests/unit/test_notice.py` (test-first for the type + registry)**

```python
import dataclasses

import pytest

from psh.notice import (
    DuplicateNoticeCodeError,
    Notice,
    NoticeRegistry,
    Severity,
    registry,
)

pytestmark = pytest.mark.unit


def test_notice_is_frozen():
    n = Notice(severity=Severity.INFO, code="c", html="<p>x</p>")
    assert dataclasses.replace(n, short="s").short == "s"       # copy works
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.short = "s"                                            # in-place assignment blocked


def test_severity_is_str_enum():
    assert Severity.ALERT == "alert"
    assert str(Severity.ALERT) == "alert"
    assert {s.value for s in Severity} == {"alert", "warning", "info"}


def test_registry_rejects_duplicate_code():
    # THE registry test (SPEC §New tests #1).  Fresh instance -> no global pollution.
    reg = NoticeRegistry()
    reg.register("x")
    with pytest.raises(DuplicateNoticeCodeError):
        reg.register("x")


def test_registry_registers_distinct_codes():
    reg = NoticeRegistry()
    reg.register("a")
    reg.register("b")
    assert reg.codes() == frozenset({"a", "b"})


def test_global_registry_has_the_poc_code(psh):
    # Importing the program (psh fixture -> psh._legacy) registered the PoC code at import.
    assert "no-domains" in registry.codes()
```

- [ ] **Step 2: Run it — confirm RED (module does not exist yet)**

Run: `./run-tests --fast tests/unit/test_notice.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'psh.notice'`.

- [ ] **Step 3: Create `psh/notice.py`**

```python
"""The Notice type and its code registry (CAMPAIGN.md §6).

A typed, frozen replacement for the ad-hoc notice dicts.  Pure: imports nothing from script_context,
so the sc facade and every psh/ module can import it without a cycle; checks/plugins reach
Notice/Severity via sc.  Adoption is per-increment (CAMPAIGN.md §6); the dict form is retired in I14.
"""
import dataclasses
from enum import StrEnum


class Severity(StrEnum):
    ALERT = "alert"
    WARNING = "warning"
    INFO = "info"


@dataclasses.dataclass(frozen=True)
class Notice:
    """One report notice.  `code` is the stable unique slug (registry-enforced) that maps to the
    notices-CSV code field; `html` is the report-body HTML, `text` its plaintext (empty -> derived by
    SiteContext.add_notice via html2text, as the dict form does); `short` is the one-line summary;
    `icon` empty -> filled from `severity`; `order` places the notice ('prepend'/'first' -> front)."""

    severity: Severity
    code: str
    html: str
    short: str = ""
    text: str = ""
    icon: str = ""
    order: str = "append"


class DuplicateNoticeCodeError(RuntimeError):
    """Raised when a notice code is registered twice.  A shared code across two notice types is the
    exact class of bug I1 fixed by hand (BLOCKMAP §Bugs 2/5); the registry makes it a loud
    import-time failure instead of a silent CSV collision."""


class NoticeRegistry:
    """Declare-once registry of notice codes.  Each notice type registers its code once at import; a
    re-used code raises DuplicateNoticeCodeError.  Registration is import-time metadata (like
    sc.substitutions/sc.hooks), not per-run/per-site state (CAMPAIGN.md §3.4)."""

    def __init__(self) -> None:
        self._codes: dict[str, str] = {}

    def register(self, code: str, *, description: str = "") -> str:
        if code in self._codes:
            raise DuplicateNoticeCodeError(
                f"notice code {code!r} is already registered "
                f"(existing: {self._codes[code]!r}); codes must be unique."
            )
        self._codes[code] = description
        return code

    def codes(self) -> frozenset[str]:
        return frozenset(self._codes)


registry = NoticeRegistry()
```

- [ ] **Step 4: Run the type/registry tests — GREEN (except the PoC-code test)**

Run: `./run-tests --fast tests/unit/test_notice.py`
Expected: `test_notice_is_frozen`, `test_severity_is_str_enum`, `test_registry_rejects_duplicate_code`,
`test_registry_registers_distinct_codes` PASS. `test_global_registry_has_the_poc_code` still FAILS
(the PoC registration lands in Step 8) — leave it red until then.

- [ ] **Step 5: Write `tests/unit/test_add_notice_from_notice.py` (round-trip seam, test-first)**

```python
import pytest

import script_context as sc
from psh.notice import Notice, Severity

pytestmark = pytest.mark.unit


def test_notice_projects_to_legacy_dict():
    html = "<p>hi</p>"
    from_notice = sc.SiteContext({"name": "s1"})
    from_notice.add_notice(
        Notice(severity=Severity.ALERT, code="no-domains",
               short="no domains connected", html=html, text="hi")
    )
    from_dict = sc.SiteContext({"name": "s1"})
    from_dict.add_notice(
        {"type": "alert", "csv": "s1,no-domains",
         "short": "no domains connected", "message": html, "text": "hi"}
    )
    assert from_notice["notices"] == from_dict["notices"]   # full dict equality (both lack 'order')


def test_notice_text_defaults_via_html2text():
    html = "<p>hello world</p>"
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.INFO, code="x", short="s", html=html))
    assert ctx["notices"][0]["text"] == sc.html_to_text(html)
```

- [ ] **Step 6: Run it — confirm RED (add_notice does not handle Notice)**

Run: `./run-tests --fast tests/unit/test_add_notice_from_notice.py`
Expected: FAIL — `TypeError: argument of type 'Notice' is not iterable` (from `'message' not in notice`).

- [ ] **Step 7: Teach `script_context.py` to accept a `Notice`**

At the top of `script_context.py` (after the existing imports), add:

```python
from psh.notice import Notice, Severity   # noqa: F401 -- Severity re-exported as sc.Severity for check/plugin packages
```

(`Notice` is used by `add_notice`; `Severity` is re-exported — importing both here is what makes
`sc.Notice`/`sc.Severity` exist, so **no `sc.Notice = …` assignment is added to `_legacy.py`**; this is
the DRY refinement over SPEC §sc re-exports — same observable façade.)

Change `add_notice` and add `_notice_to_dict`:

```python
    def add_notice(self, notice) -> None:      # notice: Notice | dict
        """Add a notice (Notice or legacy dict), filling icon (from 'type'), plaintext 'text' (via
        html2text), and honoring order ('prepend'/'first' -> front).  A Notice is projected to the
        legacy dict first (dict form retired in I14, CAMPAIGN.md §6)."""
        if isinstance(notice, Notice):
            notice = self._notice_to_dict(notice)
        if 'message' not in notice:
            console.print(f'[bold red]ERROR: Notice is missing the "message" key: {notice}')
            sys.exit(1)
        if 'icon' not in notice:
            notice['icon'] = icon[notice['type']]
        if 'text' not in notice:
            notice['text'] = html_to_text(notice['message'])
        order = notice['order'] if 'order' in notice else 'append'
        if order == 'prepend' or order == 'first':
            self['notices'].insert(0, notice)
        else:
            self['notices'].append(notice)

    def _notice_to_dict(self, notice: Notice) -> dict:
        """Project a Notice onto the legacy notice dict.  csv is built from the site name + code (the
        two-field form; extra-csv-field notices stay dicts until their adopting increment).  icon /
        text / non-default order are set only when present so the stored dict is byte-identical to the
        legacy one and add_notice's fill logic supplies icon/text identically."""
        d = {
            "type": str(notice.severity),
            "csv": f"{self['site']['name']},{notice.code}",
            "short": notice.short,
            "message": notice.html,
        }
        if notice.icon:
            d["icon"] = notice.icon
        if notice.text:
            d["text"] = notice.text
        if notice.order != "append":
            d["order"] = notice.order
        return d
```

Run: `./run-tests --fast tests/unit/test_add_notice_from_notice.py`
Expected: PASS (both).

- [ ] **Step 8: Convert the `no-domains` notice + register its code (`psh/_legacy.py`)**

Add the import near the top of `psh/_legacy.py` (beside the other `from psh.<mod> import` lines):

```python
from psh.notice import Notice, Severity, registry
```

Register the code once at module scope (e.g. right after the `fqdn_re = …` line, ~92):

```python
registry.register("no-domains", description="paid plan with no custom domains connected")
```

Replace the `no-domains` `add_notice({...})` dict at ~2551 with a `Notice`. **Copy the `message` and
`text` f-string literals VERBATIM from `_legacy` 2557–2567 — interior whitespace unchanged, and the
`text` typo "the ste" (2565) preserved byte-for-byte** (Invariant 8; the three goldens are the
tripwire):

```python
                    site_context.add_notice(
                        Notice(
                            severity=Severity.ALERT,
                            code="no-domains",
                            short="no domains connected",
                            html=f"""
                <p>{site["name"]} is on a paid plan but does not have any custom domains connected.  Either connect
                a domain through which people will access the site or downgrade the site's plan to Sandbox to save
                money.</p>
                """,
                            text=f"""
                {site["name"]} is on a paid plan but does not have
                any custom domains connected. Either connect a domain through
                which people will access the ste or downgrade the site's plan
                to Sandbox to save money.
                """,
                        )
                    )
```

(The explicit `icon` and `csv` from the old dict are dropped: `add_notice` fills `icon` from
`Severity.ALERT` → `icon["alert"] == "&#x1F6A8;"`, and `_notice_to_dict` builds
`csv = "{site['name']},no-domains"` — both byte-identical to the old dict.)

- [ ] **Step 9: Run the PoC-code test + the goldens**

Run: `./run-tests --fast tests/unit/test_notice.py::test_global_registry_has_the_poc_code`
Expected: PASS (registration now ran).

Run: `./run-tests --fast tests/e2e`
Expected: all e2e goldens PASS.

Run: `git diff 45b8a88 -- tests/e2e/__snapshots__/`
Expected: **empty** (four goldens byte-identical — the load-bearing PoC check).

- [ ] **Step 10: Extend the `sc`-façade-names house rule**

In `tests/unit/test_house_rules.py`, add `"Notice"` and `"Severity"` to `SC_FACADE_NAMES` (line ~161)
and note the RED demonstration in the docstring:

```python
SC_FACADE_NAMES = ("escape_url", "check_wordpress_plugin", "check_drupal_module",
                   "umich_enabled", "cloudflare_enabled", "terminus", "fqdn_re",
                   "db_engine_args", "Notice", "Severity")
```

RED demonstration (do it, then revert): temporarily remove `Severity` from the
`from psh.notice import Notice, Severity` line in `script_context.py`, run the test, observe it fail
naming `Severity`, revert. Paste the red output in the task report; record the demonstration in the
test docstring.

- [ ] **Step 11: Full fast suite + gates**

Run: `./run-tests --fast`
Expected: all three gates green; `psh/notice.py` passes ruff-broad + pyright 0 errors; new tests pass;
four goldens byte-identical. `git checkout -- uv.lock` if it churned.

Run: `uvx ruff check --config ruff-broad.toml psh/notice.py`  → "All checks passed!"

- [ ] **Step 12: Commit**

```bash
git add psh/notice.py script_context.py psh/_legacy.py \
        tests/unit/test_notice.py tests/unit/test_add_notice_from_notice.py \
        tests/unit/test_house_rules.py
git commit -m "feat(campaign-I3): add the Notice type + registry; adopt it for no-domains"
```

---

### Task 3: Docs, CAMPAIGN §3.1 amendment, memory, ledger

**Files:**
- Modify: `CLAUDE.md` (config functions now in `psh/configuration.py`; `Notice`/`Severity` on `sc`;
  the "Notices vs. news" bullet; the Testing façade-names note)
- Modify: `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (§3.1: add `psh/notice.py` row)
- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md` (append the I3 entry)
- Create: an auto-memory file under the memory dir + its `MEMORY.md` pointer

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `CLAUDE.md`**

- In "Single-module core + `script_context` shared state" (or the module list): note the config engine
  (`process_config`/`config_substitution`/`gate_disabled_sections`/`load_news_items`/`umich_enabled`/
  `cloudflare_enabled`) now lives in `psh/configuration.py`, re-imported by `_legacy.py`.
- In the runtime-exposed `sc` block description and the Testing "documented `sc` façade names" note:
  add `sc.Notice` / `sc.Severity`.
- In the "Notices vs. news" bullet: `SiteContext.add_notice` accepts a `Notice` (from `psh/notice.py`)
  or the legacy dict; the frozen `Notice` dataclass + `Severity` StrEnum + code registry
  (`DuplicateNoticeCodeError`) live in `psh/notice.py`; dict form retired in I14.
- **Delete** any CLAUDE.md prose that existed to explain the moved config logic if it is now in the
  package (DoD); report the CLAUDE.md line-count delta (`git diff --stat CLAUDE.md`).

- [ ] **Step 2: Amend `CAMPAIGN.md` §3.1 (Deviation 1)**

Add a row to the Tier-1 module map (§3.1 table):

```
| `psh/notice.py` | `Notice`, `Severity`, `NoticeRegistry`, `DuplicateNoticeCodeError`, `registry` (added I3; CAMPAIGN.md §6 Notice type + code registry) |
```

- [ ] **Step 3: Append the LEDGER.md I3 entry**

Use the CAMPAIGN §12 template. Record: moved blocks/functions (the six config funcs + DEFER machinery
→ `psh/configuration.py`; new `psh/notice.py`); **Deviation 1** (new module `psh/notice.py`, handled as
a §3.1 amendment — cite this commit); **Deviation 2** (PoC converted `no-domains`/B29 out-of-block,
representation-preserving, core-and-staying-core); contract/config/sc additions (`sc.Notice`,
`sc.Severity`; no contract keys); the `script_context.py` `options`/`config` annotation fix; the ruff
suppressions/fixes; discovered tasks (e.g. the extra-csv-field `Notice` modeling deferred to the first
adopting increment via a future §6 `csv_extra` amendment); open questions for I4.

- [ ] **Step 4: Write the auto-memory**

Create a memory file (e.g. `config-and-notice-modules.md`) recording: config engine now in
`psh/configuration.py` (re-imported); `psh/notice.py` holds the `Notice`/`Severity`/registry;
`add_notice` accepts a `Notice`; `sc.Notice`/`sc.Severity` are the façade names; the `no-domains` PoC.
Add the one-line pointer to `MEMORY.md`. Link `[[gateway-extraction]]` / `[[modularization-campaign]]`.

- [ ] **Step 5: Verify + commit (closing commit includes the dev folder)**

Run: `./run-tests` (full; live tier if credentialed, else `--fast` with a ledger note). Confirm goldens
byte-identical (`git diff 45b8a88 -- tests/e2e/__snapshots__/` empty).

```bash
git add CLAUDE.md development/ ~/.claude/projects/-workspace/memory/   # memory path per environment
git commit -m "docs(campaign-I3): close the config+notice increment"
```

---

## Post-tasks (controller, not a task)

After Task 3: `/code-review` (or `prompts/adversarial-review.md`) whole-branch review; fix-loop any
findings via `psh-implementer`; full `./run-tests`; `/archive-session`; the closing commit already
includes this `development/` folder. **Check in with the user at the whole-branch review before the
closing commit** (per the user's chosen flow).

## Self-Review (done)

- **Spec coverage:** Deliverable A → Task 1; Deliverable B (`psh/notice.py` + `add_notice` + PoC +
  façade) → Task 2; docs/§3.1 amendment/memory/ledger → Task 3. All SPEC §New tests mapped
  (test_notice.py, test_add_notice_from_notice.py, SC_FACADE_NAMES extension, folder-ordering pin).
- **Placeholder scan:** every code/test step shows real content; no TBD/TODO.
- **Type consistency:** `Notice(severity, code, html, short, text, icon, order)`,
  `NoticeRegistry.register(code, *, description="")`, `_notice_to_dict`, and
  `process_config(..., *, deferred_pass=False)` are used consistently across tasks and match the SPEC.
