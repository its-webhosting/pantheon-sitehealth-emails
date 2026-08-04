# `apply-platform-domains-cloudflare` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Every code-touching subagent MUST be dispatched as
> `psh-implementer` and every reviewer as `psh-reviewer` (CLAUDE.md § Dispatching subagents); the
> `general-purpose` fallback is forbidden — a dispatch that cannot use them must stop and say so.

**Goal:** Build a standalone, temporary CLI that reads one plan-or-revert file produced by
`find-platform-domains-cloudflare`, validates it against live Cloudflare state, reports exactly
what it would change, and — only with `--for-real` — performs the batch calls.

**Architecture:** One extension-less executable file plus a committed `.py` symlink, importing
nothing from `psh/`, `check/`, `plugin/` or `script_context`. Three passes: validate (read-only,
one filtered record list per FQDN), report (identical in both modes), apply (only with
`--for-real`, stopping at the first failure). Every exit path prints a summary and writes a run
record.

**Tech Stack:** Python 3.12+, `cloudflare` SDK 5.4.0 (`dns.records.list`, `dns.records.batch`),
`tomllib`, `argparse`, pytest with `SourceFileLoader`.

**The spec is `development/2026-08-03-platform-domain-util4/SPEC.md`** (referred to below as
**SPEC**). Where this plan and the SPEC disagree, the SPEC wins and the disagreement is a defect
in this plan — report it rather than resolving it silently.

> ## ⚠️ SUPERSEDED IN THREE PLACES — read the SPEC, not this plan, on these
>
> This document is **frozen at its pre-implementation state** (one commit, `a039384`); the SPEC was
> amended nineteen times during implementation. The precedence rule above did its job — a Task 8
> implementer escalated the first item below rather than coding it — but the plan's own text still
> says the superseded thing, so it is named here explicitly:
>
> 1. **There are SEVEN outcomes, not six.** This plan's `OUTCOMES` omits **`unverified`**
>    (the batch returned, so Cloudflare committed, but the result could not be confirmed).
>    See SPEC §8.1's four-state table.
> 2. **`changed` is `applied + unverified + unknown`.** This plan's
>    `changed = counts["applied"] + counts["unknown"]` is the formula SPEC §8.1 records as having
>    produced **exit 2 — "nothing in Cloudflare was changed" — for a batch that returned 200 and
>    therefore committed.** Use `changed_count(counts)`, the one shared definition.
> 3. **No failure arm returns a literal `2`.** This plan shows `return 2` in each of `main()`'s
>    handlers; SPEC §8.3 and §9.1 require `failure_code(state)`, which yields **3** when
>    `changed_count > 0`. An earlier revision of §8.3's own snippet showed the bare `2` and is what
>    led an implementer to read the two sections as contradictory.
>
> Everything else in this plan held up. The task decomposition, the seams, and the mandatory
> mutation tests are the record of how the work was actually sequenced.

---

## Global Constraints

Every task's requirements implicitly include all of these.

1. **Standalone.** The script MUST import nothing from `psh/`, `check/`, `plugin/` or
   `script_context`. Code from the main program or the siblings is **copied into the script**.
   (SPEC §2.1)
2. **No new source module.** Everything lives in the one script file. Deletion must stay `git rm`
   of two files plus four textual edits. (SPEC §19)
3. **No performance work.** (SPEC §2.3)
4. **Test-first**, using `mattpocock-skills:tdd` — **not**
   `superpowers:test-driven-development`, which `subagent-driven-development` would otherwise
   default to. `prompts/implementation-standards.md` carries the override and MUST be injected
   into every implementer brief.
5. **Refactoring is not part of the red→green loop.** It belongs to review.
6. **Every new test MUST be observed failing for the right reason** before its implementation is
   written, and the red output pasted into the task report. (PD#14)
7. **Never touch** `find-platform-domains-cloudflare`, `find-platform-domains-dns`, or either of
   their test files. `git diff --stat` on all four MUST be empty at every commit.
8. **`./run-tests --fast` MUST be green** — including ruff (`select = ALL` minus the ignore list)
   and pyright — before every commit. The ruff gate runs `uvx ruff@0.15.22`; pyright is
   `uvx pyright@1.1.411`.
9. **No credential is ever read from the environment by feature code.** Credentials come from
   `[Cloudflare]` in the TOML via the copied `<{env …}` / `<{secret env …}` resolver.
10. **Exact constants** (copy verbatim, do not retype from memory):
    - `DEFAULT_CONFIG = "pantheon-sitehealth-emails.toml"`
    - `API_BASE_URL = "https://api.cloudflare.com/client/v4"`
    - `GOVERNED_TYPES = ("CNAME", "A", "AAAA")`
    - `VERIFY_RETRY_SLEEP = 2.0`
    - `ERROR_MESSAGE_LIMIT = 200`
    - `MARKER_RE = re.compile(r"<\{(.*?)(?<!\\)}")`
11. **Every task report MUST cite the Prime Directives it applied by number and with a verbatim
    quote**, grep-checkable against `prompts/directives.md`.

---

## File Structure

| File | Created/Modified | Responsibility |
|---|---|---|
| `apply-platform-domains-cloudflare` | **Create** (Task 1) | The entire program. Executable, `#!/usr/bin/env python` shebang, `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))` guard |
| `apply-platform-domains-cloudflare.py` | **Create** (Task 1) | A committed **symlink** to the above. Without it ruff, pyright and CodeGraph are blind to the file |
| `tests/unit/test_apply_platform_domains_cloudflare.py` | **Create** (Task 1), extended by every later task | All 15 test groups |
| `pyproject.toml` | **Modify** (Task 1) | Two `[tool.ruff.lint.per-file-ignores]` entries + one `[tool.pyright].include` entry |
| `.claude/hooks/ruff-check.sh` | **Modify** (Task 1) | One `case` arm for the extension-less file |
| `CLAUDE.md` | **Modify** (Task 10) | New subsection; the "two places to check" → "three"; the sibling's "not-yet-written applier" sentence |
| `development/2026-07-31-platform-domain-util3/SPEC.md` | **Modify** (Task 10) | Pointer at §5.4 recording it was superseded |
| `development/2026-07-30-platform-domain-util2/SPEC.md` | **Modify** (Task 10) | Deletion checklist gains this script's share |

**Why one file and not a package:** SPEC §2 Global Constraint 1. This is deliberate and is not a
code smell to fix. The sibling reached 1593 lines under the same rule.

---

## Task Order and Why

Tasks 1–3 build the shell (CLI, file contract, credentials). Task 4 is the pure verdict engine.
Task 5 wires it to Cloudflare. Task 6 is the pure exit-code/summary logic — deliberately **before**
the report, because the dry run's exit code depends on it. Tasks 7–8 are the two modes. Task 9 is
the run record. Task 10 is documentation.

Each task ends with a commit and is independently reviewable.

---

### Task 1: Skeleton — file, CLI, stream guards, exit taxonomy

**Files:**
- Create: `apply-platform-domains-cloudflare`
- Create: `apply-platform-domains-cloudflare.py` (symlink)
- Create: `tests/unit/test_apply_platform_domains_cloudflare.py`
- Modify: `pyproject.toml`
- Modify: `.claude/hooks/ruff-check.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `StartupError`, `PlanFileError(StartupError)`, `InvariantError(StartupError)`,
  `OutputWriteError(StartupError)`, `CloudflareReadError(StartupError)`, `ApplyError(Exception)`;
  `point_at_devnull(stream) -> None`; `report_line(text) -> None`;
  `require_usable_streams() -> None`; `normalize(name) -> str`;
  `dump_json(data, stream) -> None`; `write_json_atomic(path, data) -> None`;
  `now_utc() -> str`; `sleep` (module attribute, `= time.sleep`);
  `build_arg_parser() -> argparse.ArgumentParser`; `main(argv) -> int`; and the constants in
  Global Constraint 10.

- [ ] **Step 1: Create the script skeleton**

Create `apply-platform-domains-cloudflare` (no extension), mode `755`. Start from this exact
content; later tasks add to it.

```python
#!/usr/bin/env python
"""Apply a plan or revert file produced by find-platform-domains-cloudflare.

TEMPORARY.  Delete after Pantheon's CDN migration -- checklist in
development/2026-07-30-platform-domain-util2/SPEC.md section 11, this script's share in
development/2026-08-03-platform-domain-util4/SPEC.md section 19.

Reads ONE file, in three passes:

    parse + file contract  ->  PASS 1 validate (read-only)  ->  PASS 2 report  ->  PASS 3 apply

Pass 3 runs only with --for-real.  If ANY selected entry fails validation, the run reports every
failure and exits 2 having written nothing.  Pass 3 never re-decides anything pass 1 decided, so
the dry run is a rehearsal of the real run rather than a parallel implementation of it.

Standalone by design: it imports nothing from psh/, check/, plugin/ or script_context, so
deletion stays `git rm` of this file and its .py symlink.  Code copied rather than imported is
inventoried in development/2026-08-03-platform-domain-util4/SPEC.md section 17.

Exit codes: 0 = everything applied (or a dry run that validated clean), 1 = completed with
already-applied skips, 2 = could not complete and NOTHING was changed, 3 = failed mid-apply and
Cloudflare was left PARTIALLY CHANGED, 130 = interrupted.
"""
import argparse
import contextlib
import datetime
import io
import json
import os
import re
import shlex
import signal
import sys
import tempfile
import time
import tomllib
from pathlib import Path

import cloudflare  # for cloudflare.CloudflareError
from cloudflare import Cloudflare

DEFAULT_CONFIG = "pantheon-sitehealth-emails.toml"
API_BASE_URL = "https://api.cloudflare.com/client/v4"   # pinned; see build_client
GOVERNED_TYPES = ("CNAME", "A", "AAAA")   # SPEC R1.1: every other type at the name is ignored
VERIFY_RETRY_SLEEP = 2.0                  # SPEC R6.2
ERROR_MESSAGE_LIMIT = 200                 # SPEC 9.1 rule 3

# Copied verbatim from find-platform-domains-cloudflare.  A marker is "<{ ... }" -- the trailing
# ">" that appears in the sample config is decorative and NOT part of the syntax.
MARKER_RE = re.compile(r"<\{(.*?)(?<!\\)}")

sleep = time.sleep   # the one sleep seam (SPEC section 13); tests monkeypatch it
```

- [ ] **Step 2: Copy the exception spine and the stream guards**

Copy these **verbatim** from `find-platform-domains-cloudflare`, by symbol name, adjusting only
the docstrings where they name the sibling's own sections:

| Copy | From | Adaptation |
|---|---|---|
| `class StartupError` | sibling | docstring: "(exit 2)" stays |
| `class InvariantError(StartupError)` | sibling | docstring rewritten for SPEC §9.1's trigger list |
| `class OutputWriteError(StartupError)` | sibling | docstring rewritten: it is the **run record** that failed, not four output files |
| `point_at_devnull(stream)` | sibling | **verbatim, no change** |
| `report_line(text)` | sibling | **verbatim, no change** |
| `normalize(name)` | sibling | **verbatim, no change** |
| `dump_json(data, stream)` | sibling | **verbatim, no change** |
| `write_json_atomic(path, data)` | sibling | change the temp-file `prefix=` to `".apply-platform-domains-"` |
| `now_utc()` | sibling | **verbatim, no change** |

Then add the two new exception classes:

```python
class PlanFileError(StartupError):
    """The input file is not a plan or revert file this script knows how to apply (SPEC 6).

    A subclass of StartupError so main()'s existing handler and the exit-2 taxonomy stay
    unchanged -- this adds a NAME, not a code path (PD#2).  Every one of SPEC section 6's eight
    checks raises this, and every message names the file, the FQDN key where one applies, and
    the offending field.  Fatal rather than per-entry-skippable BY DESIGN: a file malformed in
    one entry is a file whose provenance is in question, and partially applying it is exactly
    what SPEC section 3's first property exists to prevent.
    """


class CloudflareReadError(StartupError):
    """A DNS-record LIST call failed during pass 1 (SPEC 9.1).

    Pass 1 is read-only, so this always means nothing was changed -- hence exit 2 and a
    StartupError subclass.  A list failure during POST-APPLY VERIFICATION is NOT this: by then
    Cloudflare has been written to, so it is an ApplyError and the run exits 3.
    """


class ApplyError(Exception):
    """A batch call failed, a post-apply verification did not match after one retry, or a
    verification list call failed (SPEC 9.1).

    Deliberately NOT a StartupError subclass: those all mean exit 2 ("nothing was changed"), and
    this one usually means exit 3.  main() computes the code from the outcome tally
    (exit_code_for), never from the exception class.
    """
```

Now write `require_usable_streams`, which is **simpler than the sibling's** — it takes no
argument:

```python
def require_usable_streams() -> None:
    """Refuse to run when either standard stream is closed.

    Adapted from find-platform-domains-cloudflare's function of the same name, with its `output`
    parameter REMOVED: that script writes its result to stdout only when -o is absent, so a
    closed stdout is survivable there.  This script always writes the report to stdout and always
    writes ATTENTION/ERROR lines to stderr, so both are unconditionally required.

    The stderr case is the dangerous one, and it is measured: CPython's print(msg, file=None)
    falls back to sys.stdout, so with `2>&-` every ATTENTION line -- the ONLY signal that a
    destructive run was refused or narrowed -- would be interleaved into the report on stdout.

    Raised as a StartupError so main()'s handler reports it at exit 2.
    """
    if sys.stdout is None:
        raise StartupError(
            "standard output is closed; there is nowhere to write the report of what this run "
            "would change")
    if sys.stderr is None:
        raise StartupError(
            "standard error is closed; every ATTENTION and ERROR line would fall back to stdout "
            "and be mixed into the report there")
```

- [ ] **Step 3: Write the argument parser**

```python
def build_arg_parser():
    """The CLI (SPEC R2).

    --only is action="append", NOT nargs="+", and that is load-bearing: with one positional FILE,
    `--only a b file.json` under nargs="+" would silently swallow the filename into the option.
    The sibling documents the same argparse limitation in its own --help ("Give ZONE names AFTER
    the options").  A repeatable single-value option has no such ambiguity.

    allow_abbrev=False is the house rule: without it `--for` abbreviates to `--for-real` and a
    dry run becomes a production rewrite.
    """
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Apply a plan or revert file produced by find-platform-domains-cloudflare.  "
                    "Validates every selected entry against live Cloudflare state first and "
                    "refuses to change anything if any entry fails.  WITHOUT --for-real this is "
                    "a dry run: it reports what it would do and changes nothing.",
        epilog="Exit codes: 0 = everything applied (or a dry run that validated clean), "
               "1 = completed with already-applied entries skipped, 2 = could not complete and "
               "NOTHING was changed, 3 = FAILED MID-APPLY and Cloudflare was left partially "
               "changed, 130 = interrupted.  A run record naming every entry's outcome is "
               "written beside FILE on every one of those paths.")
    parser.add_argument("file", metavar="FILE",
                        help="the -plan.json or -revert.json file to apply")
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help=f"TOML file to read [Cloudflare] credentials from "
                             f"(default: {DEFAULT_CONFIG})")
    parser.add_argument("--only", action="append", default=None, metavar="FQDN",
                        help="apply only this FQDN; repeat the option for more than one.  An "
                             "FQDN that is not in FILE is an error")
    parser.add_argument("--for-real", action="store_true",
                        help="actually make the Cloudflare API calls.  WITHOUT THIS FLAG NOTHING "
                             "IS CHANGED")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="also print each API call's method, path and exact request body")
    return parser
```

- [ ] **Step 4: Write `main()`'s skeleton with the full handler chain**

```python
def main(argv):
    """Exit 0/1/2/3/130 -- see the module docstring and SPEC section 8.

    THE EXIT-CODE DISCIPLINE IS THE POINT OF THE STRUCTURE BELOW, ported in reasoning from
    find-platform-domains-cloudflare's main().  CPython exits 1 on ANY uncaught traceback, and 1
    here means "completed with already-applied skips" -- so an unexpected API shape or an internal
    defect leaking out of here would be indistinguishable to an operator's `case $?` from a
    healthy run.  Every other outcome is routed AWAY from 1.  The `except BaseException` arm is
    the last line of defence; `except SystemExit: raise` sits above it so a deliberate exit keeps
    its own code.  Neither swallows: the class is always named on stderr (PD#2).

    Later tasks fill in the body between require_usable_streams() and the return.
    """
    options = build_arg_parser().parse_args(argv)
    try:
        require_usable_streams()
        return 0    # replaced in Task 7
    except StartupError as e:
        report_line(f"ERROR: {e}")
        return 2
    except KeyboardInterrupt:
        report_line("ERROR: interrupted")   # replaced in Task 9
        return 130
    except OSError as e:
        report_line(f"ERROR: {e}")
        return 2
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 -- deliberate last line of defence, see the
        # docstring: without it CPython's exit 1 on an uncaught traceback would be
        # indistinguishable from this program's own exit 1.
        report_line(f"ERROR: unexpected {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Create the symlink and wire the three tool configs**

```bash
chmod 755 apply-platform-domains-cloudflare
ln -s apply-platform-domains-cloudflare apply-platform-domains-cloudflare.py
git add apply-platform-domains-cloudflare apply-platform-domains-cloudflare.py
```

In `pyproject.toml`, **after** the two `find-platform-domains-cloudflare` entries in
`[tool.ruff.lint.per-file-ignores]`, add:

```toml
"apply-platform-domains-cloudflare.py" = ["T201"]  # a CLI tool: print IS its operator output
    # (stdout = the report of what changed, stderr = ATTENTION/ERROR).  Temporary, deleted with
    # the script after the Pantheon CDN migration -- see
    # development/2026-08-03-platform-domain-util4/SPEC.md section 19.
"apply-platform-domains-cloudflare" = ["T201"]  # the extension-less real file the .py entry
    # above symlinks to -- .claude/hooks/ruff-check.sh hands ruff THIS path (an edit lands on the
    # real file, not the symlink), and per-file-ignores is keyed on the path ruff is given, so
    # the .py entry alone leaves the hook's own invocation reporting T201.  Same justification
    # and deletion condition as the .py entry above.
```

In `pyproject.toml`, extend `[tool.pyright].include`:

```toml
include = ["psh", "find-platform-domains-dns.py", "find-platform-domains-cloudflare.py",
           "apply-platform-domains-cloudflare.py"]
```

In `.claude/hooks/ruff-check.sh`, add one arm after the existing two:

```bash
    "$REPO_ROOT/apply-platform-domains-cloudflare") ;;
```

and extend the comment above that `case` to name the third utility and its SPEC path.

- [ ] **Step 6: Write the failing tests**

Create `tests/unit/test_apply_platform_domains_cloudflare.py`:

```python
"""Offline tests for the apply-platform-domains-cloudflare utility (SPEC section 13/14).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone scripts (see tests/unit/test_find_platform_domains_cloudflare.py).
It is loaded FRESH PER TEST so no module-level state leaks between tests -- which is also what
makes monkeypatching module attributes (now_utc, sleep) safe.

Imports: each task ADDS to the block below, in the task that first needs the name.  Adding an
import further down the file is what ruff's E402 forbids, and E402 is not in the tests/** ignore
list.

TEMPORARY, deleted with the script after the Pantheon CDN migration -- see
development/2026-08-03-platform-domain-util4/SPEC.md section 19.
"""
import importlib.util
import json
import subprocess
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "apply-platform-domains-cloudflare"


@pytest.fixture
def apc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("apply_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_the_symlink_points_at_the_real_file():
    """The .py symlink is what ruff, pyright and CodeGraph resolve the script through; a plain
    copy would silently drift.  CLAUDE.md records that the main program had ZERO symbols indexed
    until one was added."""
    link = SCRIPT.parent / "apply-platform-domains-cloudflare.py"
    assert link.is_symlink()
    assert link.resolve() == SCRIPT.resolve()


def test_help_documents_the_safety_gate_and_the_exit_codes(apc):
    text = apc.build_arg_parser().format_help()
    assert "--for-real" in text
    assert "WITHOUT THIS FLAG NOTHING IS CHANGED" in text
    assert "--only" in text
    for code in ("0 =", "1 =", "2 =", "3 =", "130 ="):
        assert code in text


def test_the_parser_refuses_an_abbreviation_of_for_real(apc):
    """allow_abbrev=False: `--for` must NOT become `--for-real`.  Without it a dry run silently
    becomes a production rewrite."""
    with pytest.raises(SystemExit):
        apc.build_arg_parser().parse_args(["--for", "plan.json"])


def test_only_is_repeatable_and_never_swallows_the_filename(apc):
    """SPEC R2.2: action="append", not nargs="+".  Under nargs="+" the second FQDN and the
    filename would both land in --only and FILE would be missing."""
    options = apc.build_arg_parser().parse_args(
        ["--only", "a.umich.edu", "--only", "b.umich.edu", "plan.json"])
    assert options.only == ["a.umich.edu", "b.umich.edu"]
    assert options.file == "plan.json"


def test_for_real_defaults_to_false(apc):
    """The blast-radius gate (SPEC R2.6).  A default of True would be catastrophic and is
    exactly the kind of one-character defect a test must pin."""
    assert apc.build_arg_parser().parse_args(["plan.json"]).for_real is False


def test_require_usable_streams_refuses_a_closed_stderr(apc, monkeypatch):
    monkeypatch.setattr(apc.sys, "stderr", None)
    with pytest.raises(apc.StartupError, match="standard error is closed"):
        apc.require_usable_streams()


def test_require_usable_streams_refuses_a_closed_stdout(apc, monkeypatch):
    monkeypatch.setattr(apc.sys, "stdout", None)
    with pytest.raises(apc.StartupError, match="standard output is closed"):
        apc.require_usable_streams()


def test_the_exception_spine_keeps_startup_errors_at_exit_two(apc):
    """PlanFileError, InvariantError, OutputWriteError and CloudflareReadError are all
    StartupError subclasses so main()'s ONE handler gives them all exit 2 -- they add names,
    not code paths (PD#2).  ApplyError is deliberately NOT one: it usually means exit 3."""
    for name in ("PlanFileError", "InvariantError", "OutputWriteError", "CloudflareReadError"):
        assert issubclass(getattr(apc, name), apc.StartupError), name
    assert not issubclass(apc.ApplyError, apc.StartupError)


def test_a_doomed_stdout_is_a_named_exit_two_not_the_interpreters_120(apc):
    """CPython's shutdown flush of a doomed stream overrides the exit code with 120, which is
    outside this program's taxonomy entirely.  Measured on the sibling before its guards existed.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--only", "nope", "missing.json"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
        cwd=str(SCRIPT.parent))
    assert result.returncode != 120
```

- [ ] **Step 7: Run the tests and watch them fail for the right reason**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`

Expected before Step 1–5 are complete: collection errors (`SCRIPT` does not exist). Expected
after: all pass. **Paste the red output into the task report** — for this task the honest red is
the pre-implementation collection failure, and the report must say so rather than claiming a
per-assertion red that did not happen.

- [ ] **Step 8: Run the whole gate**

Run: `./run-tests --fast`
Expected: PASS, ruff clean, pyright clean.

Run: `git diff --stat find-platform-domains-dns find-platform-domains-cloudflare tests/unit/test_find_platform_domains_dns.py tests/unit/test_find_platform_domains_cloudflare.py`
Expected: empty output.

- [ ] **Step 9: Commit**

```bash
git add apply-platform-domains-cloudflare apply-platform-domains-cloudflare.py \
        tests/unit/test_apply_platform_domains_cloudflare.py \
        pyproject.toml .claude/hooks/ruff-check.sh
git commit -m "feat(apply-platform-domains-cloudflare): skeleton, CLI and exit taxonomy"
```

---

### Task 2: The file contract and entry selection

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: `PlanFileError`, `StartupError`, `normalize` (Task 1).
- Produces:
  - `read_apply_file(path) -> dict` — the parsed document; raises `PlanFileError`.
  - `check_file_contract(doc, path) -> str` — returns the direction (`"plan"` or `"revert"`);
    raises `PlanFileError` on any of SPEC §6's eight checks.
  - `select_entries(entries, only) -> dict` — `{fqdn: entry}`; raises `StartupError` naming
    **every** miss.

- [ ] **Step 1: Write the failing tests**

Add to the test file. Note the shared builders — later tasks reuse them, so they go in now.

```python
def plan_entry(zone_id="zone-a", fqdn="a.umich.edu",
               target="live-umich-x.pantheonsite.io",
               addresses=("23.185.0.4", "2620:12a:8000::4")):
    """One well-formed plan entry, in util3 SPEC section 5.3's shape."""
    posts = []
    for address in addresses:
        rtype = "AAAA" if ":" in address else "A"
        posts.append({"type": rtype, "name": fqdn, "content": address,
                      "proxied": True, "ttl": 1,
                      "settings": {"ipv4_only": False, "ipv6_only": False}})
    return {
        "zone_id": zone_id,
        "method": "POST",
        "path": f"/zones/{zone_id}/dns_records/batch",
        "delete_match": [{"type": "CNAME", "name": fqdn, "content": target}],
        "body": {"posts": posts},
    }


def plan_doc(entries=None, direction="plan"):
    return {"generated": {"direction": direction, "at": "2026-08-01T00:22:23Z"},
            "entries": entries if entries is not None else {"a.umich.edu": plan_entry()}}


def write_doc(tmp_path, doc, name="platform-domains-cloudflare-plan.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


def test_read_apply_file_rejects_a_missing_file(apc, tmp_path):
    with pytest.raises(apc.PlanFileError, match="nope.json"):
        apc.read_apply_file(str(tmp_path / "nope.json"))


def test_read_apply_file_rejects_invalid_json(apc, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    with pytest.raises(apc.PlanFileError, match="not valid JSON"):
        apc.read_apply_file(str(path))


def test_read_apply_file_rejects_a_json_array(apc, tmp_path):
    path = tmp_path / "array.json"
    path.write_text("[]")
    with pytest.raises(apc.PlanFileError, match="a JSON object"):
        apc.read_apply_file(str(path))


def test_check_file_contract_returns_the_direction(apc):
    assert apc.check_file_contract(plan_doc(), "p.json") == "plan"
    assert apc.check_file_contract(plan_doc(direction="revert"), "p.json") == "revert"


def test_check_file_contract_refuses_an_excluded_file_by_name(apc):
    """SPEC section 6 check 2.  An -excluded.json has the same header shape and no `body`
    anywhere, so it must be named, not merely rejected as malformed."""
    doc = plan_doc(direction="excluded")
    with pytest.raises(apc.PlanFileError, match="excluded"):
        apc.check_file_contract(doc, "p.json")


def test_check_file_contract_refuses_a_missing_direction(apc):
    doc = plan_doc()
    del doc["generated"]["direction"]
    with pytest.raises(apc.PlanFileError, match="direction"):
        apc.check_file_contract(doc, "p.json")


def test_check_file_contract_refuses_an_empty_entries_object(apc):
    with pytest.raises(apc.PlanFileError, match="no entries"):
        apc.check_file_contract(plan_doc(entries={}), "p.json")


@pytest.mark.parametrize("field", ["zone_id", "method", "path", "body", "delete_match"])
def test_check_file_contract_names_a_missing_required_field(apc, field):
    entry = plan_entry()
    del entry[field]
    with pytest.raises(apc.PlanFileError, match=f"a.umich.edu.*{field}"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_a_non_post_method(apc):
    entry = plan_entry()
    entry["method"] = "PUT"
    with pytest.raises(apc.PlanFileError, match="POST"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_a_path_that_disagrees_with_zone_id(apc):
    """SPEC section 6 check 5.  This assertion is what keeps the file's `path` field from being
    decorative: the typed SDK call builds its own path, so an unchecked one would be silently
    ignored."""
    entry = plan_entry()
    entry["path"] = "/zones/SOMEWHERE-ELSE/dns_records/batch"
    with pytest.raises(apc.PlanFileError, match="path"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_deletes_inside_body(apc):
    """util3 SPEC R5.3: ids are resolved at apply time, so a baked-in `deletes` cannot be
    correct."""
    entry = plan_entry()
    entry["body"]["deletes"] = [{"id": "stale"}]
    with pytest.raises(apc.PlanFileError, match="deletes"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_empty_posts(apc):
    entry = plan_entry()
    entry["body"]["posts"] = []
    with pytest.raises(apc.PlanFileError, match="posts"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


@pytest.mark.parametrize("bad_type", ["MX", "TXT", "cname"])
def test_check_file_contract_refuses_an_out_of_scope_post_type(apc, bad_type):
    """SPEC R1.1 -- and the check is what makes the governed-type rule total: after it, D and P
    contain only CNAME/A/AAAA by construction.  A lowercase "cname" is refused too: record_key
    upper-cases for comparison, and accepting it here would let a file smuggle a type past a
    reader's eye."""
    entry = plan_entry()
    entry["body"]["posts"][0]["type"] = bad_type
    with pytest.raises(apc.PlanFileError, match="type"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_check_file_contract_refuses_an_empty_delete_match(apc):
    entry = plan_entry()
    entry["delete_match"] = []
    with pytest.raises(apc.PlanFileError, match="delete_match"):
        apc.check_file_contract(plan_doc(entries={"a.umich.edu": entry}), "p.json")


def test_select_entries_returns_everything_without_only(apc):
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu")}
    assert apc.select_entries(entries, None) == entries


def test_select_entries_filters_and_normalizes(apc):
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu")}
    selected = apc.select_entries(entries, ["A.UMICH.EDU."])
    assert list(selected) == ["a.umich.edu"]


def test_select_entries_names_every_miss(apc):
    """SPEC R7.3: a typo that silently narrows a destructive run is the under-reporting failure
    this family refuses to have -- so EVERY miss is named, not just the first."""
    entries = {"a.umich.edu": plan_entry()}
    with pytest.raises(apc.StartupError) as excinfo:
        apc.select_entries(entries, ["nope.umich.edu", "also-nope.umich.edu"])
    message = str(excinfo.value)
    assert "nope.umich.edu" in message
    assert "also-nope.umich.edu" in message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'read_apply_file'` (and the
same for `check_file_contract`, `select_entries`). Paste the output.

- [ ] **Step 3: Implement `read_apply_file`**

```python
def read_apply_file(path):
    """Parse the input file.  Every failure is a PlanFileError naming the path (SPEC 6, 1)."""
    try:
        with Path(path).open("rb") as handle:
            doc = json.load(handle)
    except OSError as e:
        raise PlanFileError(f"cannot read {path}: {e}") from e
    except ValueError as e:
        # ValueError, not JSONDecodeError: json.load decodes the bytes itself, so a file that is
        # not valid UTF-8 raises UnicodeDecodeError -- NOT a JSONDecodeError.  Both are
        # ValueError subclasses, so one clause closes the CLASS rather than the instance.  The
        # sibling shipped this exact defect three times before closing it the same way.
        raise PlanFileError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise PlanFileError(f"{path} is not a JSON object (got {type(doc).__name__})")
    return doc
```

- [ ] **Step 4: Implement `check_file_contract`**

```python
def check_file_contract(doc, path):
    """SPEC section 6's eight checks, in order.  Returns the direction.

    Fatal rather than per-entry: a file malformed in one entry is a file whose provenance is in
    question.  After this returns, every entry is known to carry zone_id/method/path/body/
    delete_match, a POST to its own zone's batch path, a non-empty `posts` with no `deletes`
    beside it, and only CNAME/A/AAAA types -- which is what makes GOVERNED_TYPES total downstream.
    """
    generated = doc.get("generated")
    direction = generated.get("direction") if isinstance(generated, dict) else None
    if direction == "excluded":
        raise PlanFileError(
            f"{path} is an EXCLUDED file (generated.direction is 'excluded'), not a plan or a "
            "revert.  An excluded file records why FQDNs got no rewrite instructions; it carries "
            "no request body and there is nothing to apply.")
    if direction not in ("plan", "revert"):
        raise PlanFileError(
            f"{path}: generated.direction must be 'plan' or 'revert', got {direction!r}")

    entries = doc.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise PlanFileError(f"{path} has no entries to apply")

    for fqdn, entry in sorted(entries.items()):
        where = f"{path} entry {fqdn}"
        if not isinstance(entry, dict):
            raise PlanFileError(f"{where}: not an object")
        for field in ("zone_id", "method", "path", "body", "delete_match"):
            if field not in entry:
                raise PlanFileError(f"{where}: missing required field '{field}'")
        if entry["method"] != "POST":
            raise PlanFileError(
                f"{where}: method must be 'POST', got {entry['method']!r}")
        expected_path = f"/zones/{entry['zone_id']}/dns_records/batch"
        if entry["path"] != expected_path:
            raise PlanFileError(
                f"{where}: path must be {expected_path!r} (built from this entry's own "
                f"zone_id), got {entry['path']!r}")
        body = entry["body"]
        if not isinstance(body, dict):
            raise PlanFileError(f"{where}: body must be an object")
        if "deletes" in body:
            raise PlanFileError(
                f"{where}: body must not contain 'deletes' -- record ids are resolved against "
                "Cloudflare at apply time, so any ids baked into the file cannot be correct")
        check_record_list(body.get("posts"), f"{where} body.posts")
        check_record_list(entry["delete_match"], f"{where} delete_match")
    return direction


def check_record_list(items, where):
    """SPEC section 6 checks 7 and 8: a non-empty list of {type, name, content} in scope."""
    if not isinstance(items, list) or not items:
        raise PlanFileError(f"{where}: must be a non-empty list")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise PlanFileError(f"{where}[{index}]: not an object")
        for field in ("type", "name", "content"):
            if not item.get(field):
                raise PlanFileError(f"{where}[{index}]: missing '{field}'")
        if item["type"] not in GOVERNED_TYPES:
            raise PlanFileError(
                f"{where}[{index}]: type must be one of {', '.join(GOVERNED_TYPES)}, got "
                f"{item['type']!r}")
```

- [ ] **Step 5: Implement `select_entries`**

```python
def select_entries(entries, only):
    """SPEC R7.  Without --only, everything; with it, exactly the named FQDNs.

    EVERY unmatched name is named, not just the first: a typo that silently narrows a destructive
    run is the under-reporting failure this family of scripts refuses to have (R7.3).  Unselected
    entries are never validated and never counted as anything but "in the file" (R7.2a) --
    validating an entry the run will not touch would let an unrelated FQDN's drift abort a
    deliberately narrow, safe run.
    """
    if only is None:
        return dict(entries)
    wanted = [normalize(name) for name in only]
    missing = [name for name in wanted if name not in entries]
    if missing:
        raise StartupError(
            "--only named "
            + ("an FQDN that is not" if len(missing) == 1 else "FQDNs that are not")
            + " in this file: " + ", ".join(sorted(missing)))
    return {fqdn: entries[fqdn] for fqdn in entries if fqdn in set(wanted)}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): file contract and entry selection"
```

---

### Task 3: Credentials and the pinned client

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: `StartupError`, `MARKER_RE`, `API_BASE_URL`, `DEFAULT_CONFIG` (Task 1).
- Produces: `resolve_env_marker(expr, where) -> str`; `resolve_config_value(value, where)`;
  `build_client(**creds) -> Cloudflare`; `cloudflare_client(config_path) -> Cloudflare`;
  `api_error_text(e) -> str`.

**This is the security-critical task.** SPEC §16: this is the **first** of the three copies of the
environment pin that performs **writes**, which raises the `$CLOUDFLARE_BASE_URL` route from
credential disclosure to credential disclosure *plus a rewrite aimed at an attacker-chosen host*.

- [ ] **Step 1: Write the failing tests**

```python
def config_file(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body)
    return str(path)


def test_cloudflare_client_prefers_the_api_token(apc, tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_EMAIL", raising=False)
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    request = client._build_request(
        types.SimpleNamespace(method="get", url="/zones", headers={}, json_data=None,
                              files=None, params={}, extra_json=None, timeout=None,
                              follow_redirects=None, idempotency_key=None, post_parser=None))
    assert request.headers["Authorization"] == "Bearer tok-123"


def test_cloudflare_client_ignores_an_ambient_base_url(apc, tmp_path, monkeypatch):
    """The worst of the four routes: an ambient CLOUDFLARE_BASE_URL sends the CONFIGURED
    credential to an arbitrary host.  Asserted against a REAL BUILT REQUEST, not against the
    attribute assignments that implement the pin -- the sibling's set-intersection version of
    this assertion silently missed the _custom_headers route."""
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://attacker.example/")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert str(client.base_url).startswith(apc.API_BASE_URL)


def test_cloudflare_client_ignores_ambient_custom_headers(apc, tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_CUSTOM_HEADERS", "X-Auth-Email: leak@example.com")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert client._custom_headers == {}


def test_cloudflare_client_ignores_an_ambient_email(apc, tmp_path, monkeypatch):
    """auth_headers returns the FIRST of email -> key -> token, so an ambient CLOUDFLARE_EMAIL
    beats a configured api_token and the token is never sent."""
    monkeypatch.setenv("CLOUDFLARE_EMAIL", "ambient@example.com")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "ambient-key")
    path = config_file(tmp_path, '[Cloudflare]\napi_token = "tok-123"\n')
    client = apc.cloudflare_client(path)
    assert client.api_email is None
    assert client.api_key is None


def test_cloudflare_client_falls_back_to_email_and_key(apc, tmp_path):
    path = config_file(tmp_path,
                       '[Cloudflare]\nemail = "a@b.edu"\napi_key = "k"\n')
    client = apc.cloudflare_client(path)
    assert client.api_email == "a@b.edu"
    assert client.api_token is None


def test_cloudflare_client_refuses_a_non_string_credential(apc, tmp_path):
    """TOML is typed: `api_token = true` is an ordinary unquoted-value typo, and the SDK would
    stringify it into `Authorization: Bearer True` -- a baffling 401."""
    path = config_file(tmp_path, "[Cloudflare]\napi_token = true\n")
    with pytest.raises(apc.StartupError, match="must be a string"):
        apc.cloudflare_client(path)


def test_resolve_env_marker_refuses_a_form_it_cannot_resolve(apc):
    """A literal "<{secret aws ...}" handed to the API as a token surfaces as a baffling 401
    instead of a config error.  The body is withheld: an inline default can be a credential."""
    with pytest.raises(apc.StartupError) as excinfo:
        apc.resolve_env_marker("secret aws prod/key", "cfg [Cloudflare].api_token")
    assert "prod/key" not in str(excinfo.value)


def test_api_error_text_says_nothing_but_the_status_on_an_auth_failure(apc):
    """SPEC 9.1 rule 2.  The sibling's docstring: "an auth-failure body can echo the credential".
    401 and 403 report the class and status ALONE."""
    for status in (401, 403):
        error = types.SimpleNamespace(status_code=status,
                                      body={"errors": [{"code": 10000, "message": "SECRET-TOKEN"}]})
        error.__class__ = type("APIStatusError", (Exception,), {})
        text = apc.api_error_text(error)
        assert str(status) in text
        assert "SECRET-TOKEN" not in text


def test_api_error_text_admits_structured_errors_on_a_non_auth_failure(apc):
    error = types.SimpleNamespace(
        status_code=400,
        body={"errors": [{"code": 81058, "message": "An identical record already exists."}]})
    error.__class__ = type("APIStatusError", (Exception,), {})
    text = apc.api_error_text(error)
    assert "81058" in text
    assert "identical record already exists" in text


def test_api_error_text_truncates_a_long_message(apc):
    """SPEC 9.1 rule 3: an unexpectedly large or repeating error array must not become a dump of
    arbitrary server-supplied text in an operator's log."""
    error = types.SimpleNamespace(status_code=400,
                                  body={"errors": [{"code": 1, "message": "x" * 300}]})
    error.__class__ = type("APIStatusError", (Exception,), {})
    text = apc.api_error_text(error)
    assert "x" * apc.ERROR_MESSAGE_LIMIT in text
    assert "x" * (apc.ERROR_MESSAGE_LIMIT + 1) not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "client or marker or api_error" -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'cloudflare_client'`. Paste it.

- [ ] **Step 3: Copy the credential chain**

Copy **verbatim** from `find-platform-domains-cloudflare`, by symbol name:
`resolve_env_marker`, `resolve_config_value`, `build_client`, `cloudflare_client`.

**One docstring change is mandatory** in `build_client`: the sibling's says *"This is a deliberate
SECOND COPY"* and *"An SDK upgrade must re-verify BOTH"*. Change to **THIRD COPY** and **all
three**, and add:

```
    THIS copy is the only one of the three that performs WRITES.  That raises route 4
    ($CLOUDFLARE_BASE_URL) from "the credential leaves the machine" to "the credential leaves the
    machine AND a destructive rewrite is aimed at whatever host answers".  The pin is therefore
    load-bearing here in a way it is not in the two read-only siblings.
```

- [ ] **Step 4: Implement the branched `api_error_text`**

```python
def api_error_text(e):
    """A message for a Cloudflare API failure (SPEC 9.1).

    Adapted from find-platform-domains-cloudflare's function of the same name, which NEVER admits
    a response body.  Its docstring gives two reasons: "a DNS-record body echoes record contents
    and an auth-failure body can echo the credential."  The first does not apply here -- this
    script's operator already holds the file describing those exact records, and a failed WRITE is
    undiagnosable without Cloudflare's own reason for it.  The second is real, and rule 2 below is
    what keeps it closed.

    Three rules, exhaustive:
      1. Only the structured errors[].code and errors[].message.  NEVER str(e), never the raw
         body, never headers, never error_chain or any other nested member.
      2. NOTHING but the class and the status on HTTP 401/403 -- exactly the response class the
         sibling's warning is about.  An auth failure needs no per-record diagnosis anyway: the
         run is misconfigured, not drifted.
      3. Each message truncated to ERROR_MESSAGE_LIMIT characters, and the error count reported,
         so a large or repeating array cannot fill a terminal or a log.
    """
    status = getattr(e, "status_code", None)
    if status is None:
        return f"{type(e).__name__}: {e}"
    if status in (401, 403):
        return (f"{type(e).__name__}: HTTP {status} (authentication or authorization failed; "
                "the response is withheld because it can echo the credential)")
    body = getattr(e, "body", None)
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list) or not errors:
        return f"{type(e).__name__}: HTTP {status}"
    parts = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        message = str(item.get("message", ""))[:ERROR_MESSAGE_LIMIT]
        parts.append(f"{code} {message}".strip())
    if not parts:
        return f"{type(e).__name__}: HTTP {status}"
    return f"{type(e).__name__}: HTTP {status} ({len(parts)} error(s)): " + "; ".join(parts)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 6: Mutation-test each of the three pins (PD#14, MANDATORY)**

For each mutation below, apply it, run the named test, confirm **RED**, then revert:

| Mutation | Test that must go red |
|---|---|
| Remove `base_url=API_BASE_URL` from the `Cloudflare(...)` call | `test_cloudflare_client_ignores_an_ambient_base_url` |
| Remove the `client._custom_headers = {}` line | `test_cloudflare_client_ignores_ambient_custom_headers` |
| Remove the `setattr(client, field, None)` loop | `test_cloudflare_client_ignores_an_ambient_email` |
| Change `status in (401, 403)` to `status == 401` | `test_api_error_text_says_nothing_but_the_status_on_an_auth_failure` |

**Paste all four red outputs into the task report.** A green assertion that has not been shown
capable of going red is a claim, not evidence.

- [ ] **Step 7: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): pinned Cloudflare client and error text"
```

---

### Task 4: The verdict engine (pure)

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: `normalize`, `GOVERNED_TYPES` (Task 1).
- Produces:
  - `record_key(rtype, name, content) -> tuple[str, str, str]`
  - `governed_records(rows) -> list` — the rows whose type is governed
  - `verdict_for(entry, rows) -> tuple[str, str]` — `(verdict, detail)`

- [ ] **Step 1: Write the failing tests**

```python
def row(rtype="CNAME", name="a.umich.edu", content="live-umich-x.pantheonsite.io",
        identifier="rec-1"):
    """A stand-in for one SDK record object as dns.records.list returns it."""
    return types.SimpleNamespace(id=identifier, type=rtype, name=name, content=content)


def cname_rows():
    return [row()]


def address_rows():
    return [row("A", content="23.185.0.4", identifier="rec-a"),
            row("AAAA", content="2620:12a:8000::4", identifier="rec-b")]


def test_record_key_treats_two_spellings_of_one_ipv6_address_as_one_record(apc):
    """A string comparison would call these two records and invent a partially-applied verdict
    on a healthy zone."""
    assert (apc.record_key("AAAA", "a.umich.edu", "2620:12a:8000::4")
            == apc.record_key("AAAA", "a.umich.edu", "2620:12A:8000:0:0:0:0:4"))


def test_record_key_ignores_case_and_a_trailing_dot(apc):
    assert (apc.record_key("CNAME", "A.Umich.EDU.", "Live-X.PantheonSite.io.")
            == apc.record_key("cname", "a.umich.edu", "live-x.pantheonsite.io"))


def test_governed_records_drops_unrelated_types(apc):
    """SPEC R1.1: a TXT/MX/CAA at the same name is none of this script's business."""
    rows = [row(), row("TXT", content="v=spf1 -all", identifier="rec-t"),
            row("MX", content="mx.umich.edu", identifier="rec-m")]
    assert [r.id for r in apc.governed_records(rows)] == ["rec-1"]


def test_verdict_ready_when_cloudflare_holds_exactly_the_delete_match(apc):
    verdict, detail = apc.verdict_for(plan_entry(), cname_rows())
    assert verdict == "ready"
    assert detail == ""


def test_verdict_already_applied_when_cloudflare_holds_exactly_the_posts(apc):
    """SPEC R4.3: established affirmatively (R == P), NEVER inferred from the absence of D."""
    verdict, _ = apc.verdict_for(plan_entry(), address_rows())
    assert verdict == "already-applied"


def test_verdict_record_ambiguous_when_a_key_occurs_twice(apc):
    rows = [row(), row(identifier="rec-2")]
    verdict, detail = apc.verdict_for(plan_entry(), rows)
    assert verdict == "record-ambiguous"
    assert "rec-1" in detail or "CNAME" in detail


def test_verdict_partially_applied_on_a_mix_of_both_sides(apc):
    rows = [*cname_rows(), row("A", content="23.185.0.4", identifier="rec-a")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "partially-applied"


def test_verdict_unexpected_records_on_a_proper_superset(apc):
    """SPEC 7.3 row 5 -- this is util3 SPEC 5.4's "known and accepted" hazard (an unrelated
    fourth A record at the name), caught at validation time instead of as a rollback."""
    rows = [*address_rows(), row("A", content="23.185.0.99", identifier="rec-extra")]
    verdict, detail = apc.verdict_for(plan_entry(), rows)
    assert verdict == "unexpected-records"
    assert "23.185.0.99" in detail


def test_verdict_records_missing_when_nothing_governed_is_there(apc):
    """SPEC 7.4's empty shadow: NOT silently treated as already-applied."""
    verdict, _ = apc.verdict_for(plan_entry(), [])
    assert verdict == "records-missing"


def test_verdict_records_missing_on_a_strict_subset(apc):
    rows = [row("A", content="23.185.0.4", identifier="rec-a")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "records-missing"


def test_verdict_ambiguity_is_evaluated_before_the_set_comparisons(apc):
    """SPEC 7.3: row 1 first, so a duplicated key can never make a set comparison accidentally
    succeed -- a set() of [X, X] equals a set() of [X]."""
    rows = [*cname_rows(), row(identifier="rec-dup")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "record-ambiguous"


def test_verdict_ignores_an_unrelated_txt_record_at_the_same_name(apc):
    rows = [*cname_rows(), row("TXT", content="v=spf1 -all", identifier="rec-t")]
    verdict, _ = apc.verdict_for(plan_entry(), rows)
    assert verdict == "ready"


def test_a_revert_entry_is_ready_when_the_addresses_are_present(apc):
    """The same engine, both directions: a revert's D is the A/AAAA set and its P is the CNAME."""
    entry = plan_entry()
    entry["delete_match"], entry["body"]["posts"] = (
        [{"type": "A", "name": "a.umich.edu", "content": "23.185.0.4"},
         {"type": "AAAA", "name": "a.umich.edu", "content": "2620:12a:8000::4"}],
        [{"type": "CNAME", "name": "a.umich.edu",
          "content": "live-umich-x.pantheonsite.io", "proxied": True, "ttl": 1}])
    verdict, _ = apc.verdict_for(entry, address_rows())
    assert verdict == "ready"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "verdict or record_key or governed" -v`
Expected: FAIL with `AttributeError: ... 'record_key'`. Paste it.

- [ ] **Step 3: Implement the engine**

```python
def record_key(rtype, name, content):
    """The comparison key for one DNS record (SPEC 7.1).

    Addresses are compared as ipaddress VALUES, not strings: 2620:12a:8000::4 and
    2620:12A:8000:0:0:0:0:4 are one address written two ways, and a string comparison would call
    them two records -- inventing a partially-applied verdict on a healthy zone.  Names and CNAME
    targets go through normalize(), so case and a trailing dot never split a key.  Cloudflare's
    own name/content list filters are documented CASE-INSENSITIVE, so what the filter returns is
    re-checked here regardless of what it matched.
    """
    rtype = str(rtype).upper()
    if rtype in ("A", "AAAA"):
        try:
            canonical = str(ipaddress.ip_address(str(content).strip()))
        except ValueError:
            # Not an address at all.  Keep it as text rather than raising: this is a comparison
            # key, and a record Cloudflare returned with unparseable content must still be
            # comparable (it will simply not equal anything the file describes, which is the
            # correct outcome -- an invalid verdict naming it).
            canonical = normalize(content)
    else:
        canonical = normalize(content)
    return (rtype, normalize(name), canonical)


def governed_records(rows):
    """The records at a name that this script reasons about (SPEC R1.1).

    Everything else -- TXT, MX, CAA -- is ignored entirely: never read as state, never deleted,
    never counted.  A site's SPF record must not be able to make a rewrite look drifted.
    """
    return [r for r in rows if str(getattr(r, "type", "")).upper() in GOVERNED_TYPES]


def verdict_for(entry, rows):
    """Classify one entry against Cloudflare's current state (SPEC 7.3).  Returns (verdict,
    detail); detail is "" only for the two valid verdicts.

    The whole decision is WHICH SET R equals.  Evaluation order is the table's order and row 1 is
    first for a reason: set() collapses duplicates, so a duplicated key would let R == D succeed
    on a name that actually holds the record twice.
    """
    present = governed_records(rows)
    keys = [record_key(r.type, r.name, r.content) for r in present]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        return ("record-ambiguous",
                f"more than one record at this name with the same type and content: "
                f"{describe_keys(duplicates)}")

    have = set(keys)
    want_delete = {record_key(item["type"], item["name"], item["content"])
                   for item in entry["delete_match"]}
    want_post = {record_key(item["type"], item["name"], item["content"])
                 for item in entry["body"]["posts"]}

    if have == want_delete:
        return ("ready", "")
    if have == want_post:
        return ("already-applied", "")
    if have & want_delete and have & want_post:
        return ("partially-applied",
                f"Cloudflare holds a MIX of the records to delete and the records to create: "
                f"{describe_keys(sorted(have))}")
    for expected, side in ((want_delete, "to delete"), (want_post, "to create")):
        if have > expected:
            return ("unexpected-records",
                    f"Cloudflare holds every record {side} plus "
                    f"{describe_keys(sorted(have - expected))}, which this entry does not "
                    "describe")
    return ("records-missing",
            f"Cloudflare holds {describe_keys(sorted(have)) or 'no CNAME/A/AAAA record'} at this "
            f"name; expected either {describe_keys(sorted(want_delete))} (not yet applied) or "
            f"{describe_keys(sorted(want_post))} (already applied)")


def describe_keys(keys):
    """Render record keys for an operator message."""
    return ", ".join(f"{rtype} {content}" for rtype, _name, content in keys)
```

Add `import ipaddress` to the import block (alphabetical, before `io`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): the verdict engine"
```

---

### Task 5: Pass 1 — validate against Cloudflare

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: `verdict_for`, `governed_records`, `record_key` (Task 4); `CloudflareReadError`,
  `api_error_text` (Tasks 1, 3).
- Produces:
  - `class Validation(NamedTuple)` — `verdict: str`, `detail: str`, `delete_ids: list[str]`
  - `records_at_name(client, zone_id, fqdn) -> list`
  - `validate_entries(client, entries, *, verbose) -> dict[str, Validation]`

- [ ] **Step 1: Write the failing tests, including the shared fake client**

```python
class FakeCloudflareClient:
    """The two calls this script makes: dns.records.list and dns.records.batch.

    `rows_by_name` maps a normalized FQDN to the SEQUENCE of row-lists returned by successive
    list() calls for that name (the last repeats), so a post-apply verification can be made to
    agree or disagree with what pass 1 saw.  Every call is recorded, which is what lets a test
    assert that a dry run made ZERO batch calls rather than inferring it.
    """

    def __init__(self, rows_by_name=None, list_error=None, batch_error=None):
        self.rows_by_name = rows_by_name or {}
        self.list_error = list_error
        self.batch_error = batch_error
        self.list_calls = []
        self.batch_calls = []
        self._served = {}
        self.dns = types.SimpleNamespace(
            records=types.SimpleNamespace(list=self._list, batch=self._batch))

    def _list(self, *, zone_id, name=None, **kwargs):
        self.list_calls.append({"zone_id": zone_id, "name": name, **kwargs})
        if self.list_error is not None:
            raise self.list_error
        key = (name or {}).get("exact", "")
        sequence = self.rows_by_name.get(key, [[]])
        index = min(self._served.get(key, 0), len(sequence) - 1)
        self._served[key] = index + 1
        return sequence[index]

    def _batch(self, *, zone_id, deletes=None, posts=None, **kwargs):
        self.batch_calls.append({"zone_id": zone_id, "deletes": deletes, "posts": posts})
        if self.batch_error is not None:
            raise self.batch_error
        return types.SimpleNamespace(deletes=deletes, posts=posts)


def test_records_at_name_asks_cloudflare_for_exactly_that_name(apc):
    """One filtered list per FQDN, NOT a whole-zone walk: util3 measured 2 duplicates and 2
    misses in one walk of an 18,848-record zone, and a miss would be a FALSE validation
    failure."""
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    rows = apc.records_at_name(client, "zone-a", "a.umich.edu")
    assert [r.id for r in rows] == ["rec-1"]
    assert client.list_calls[0]["zone_id"] == "zone-a"
    assert client.list_calls[0]["name"] == {"exact": "a.umich.edu"}


def test_records_at_name_names_a_cloudflare_read_failure(apc):
    error = cloudflare_error(500)
    client = FakeCloudflareClient(list_error=error)
    with pytest.raises(apc.CloudflareReadError):
        apc.records_at_name(client, "zone-a", "a.umich.edu")


def cloudflare_error(status, code=1000, message="boom"):
    error = types.SimpleNamespace(status_code=status,
                                  body={"errors": [{"code": code, "message": message}]})
    error.__class__ = type("APIStatusError", (Exception,), {})
    return error


def test_validate_entries_resolves_the_delete_ids_for_a_ready_entry(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    result = apc.validate_entries(client, {"a.umich.edu": plan_entry()}, verbose=False)
    assert result["a.umich.edu"].verdict == "ready"
    assert result["a.umich.edu"].delete_ids == ["rec-1"]


def test_validate_entries_resolves_no_ids_for_an_already_applied_entry(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    result = apc.validate_entries(client, {"a.umich.edu": plan_entry()}, verbose=False)
    assert result["a.umich.edu"].verdict == "already-applied"
    assert result["a.umich.edu"].delete_ids == []


def test_validate_entries_classifies_every_entry_not_just_the_first(apc):
    """A first-failure-wins loop would hide the second problem and force a second full run."""
    client = FakeCloudflareClient(rows_by_name={
        "a.umich.edu": [cname_rows()],
        "b.umich.edu": [[]],
    })
    entries = {"a.umich.edu": plan_entry(), "b.umich.edu": plan_entry(fqdn="b.umich.edu")}
    result = apc.validate_entries(client, entries, verbose=False)
    assert result["a.umich.edu"].verdict == "ready"
    assert result["b.umich.edu"].verdict == "records-missing"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "records_at_name or validate_entries" -v`
Expected: FAIL with `AttributeError: ... 'records_at_name'`. Paste it.

- [ ] **Step 3: Implement pass 1**

```python
class Validation(NamedTuple):
    """One entry's pass-1 result.  `delete_ids` is non-empty only for a `ready` verdict."""

    verdict: str
    detail: str
    delete_ids: list


def records_at_name(client, zone_id, fqdn):
    """Every DNS record Cloudflare holds at one name (SPEC 7.1).

    ONE filtered list call, not a walk of the zone: util3 measured 2 duplicates and 2 misses in a
    single paginated walk of an 18,848-record zone, and a miss here would be a FALSE validation
    failure on a healthy entry.  Filtering by name also keeps the response small enough that
    pagination never arises, which is why none of the sibling's read_all/ListTally machinery is
    copied into this script.
    """
    try:
        page = client.dns.records.list(zone_id=zone_id, name={"exact": fqdn})
        return list(page)
    except cloudflare.CloudflareError as e:
        raise CloudflareReadError(
            f"cannot list DNS records for {fqdn} in zone {zone_id}: {api_error_text(e)}") from e


def validate_entries(client, entries, *, verbose):
    """Pass 1: classify EVERY selected entry before anything is written (SPEC R3.1).

    Every entry is classified even after the first invalid one: a first-failure-wins loop would
    hide the second problem and cost the operator another full run to find it.
    """
    result = {}
    for fqdn, entry in sorted(entries.items()):
        rows = records_at_name(client, entry["zone_id"], fqdn)
        verdict, detail = verdict_for(entry, rows)
        delete_ids = []
        if verdict == "ready":
            wanted = {record_key(item["type"], item["name"], item["content"])
                      for item in entry["delete_match"]}
            delete_ids = [r.id for r in governed_records(rows)
                          if record_key(r.type, r.name, r.content) in wanted]
        if verbose:
            print(f"{fqdn}: {verdict}"
                  + (f" -- {detail}" if detail else ""), flush=True)
        result[fqdn] = Validation(verdict, detail, delete_ids)
    return result
```

Add `from typing import NamedTuple` to the import block.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): pass 1, validate against Cloudflare"
```

---

### Task 6: The outcome tally, exit codes and the summary (pure)

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: nothing beyond Task 1's constants.
- Produces:
  - `OUTCOMES` — the exhaustive tuple
    `("applied", "already-applied", "planned", "failed", "unknown", "not-attempted")`
  - `tally(outcomes) -> dict[str, int]` — every key present, zero-filled
  - `exit_code_for(counts) -> int`
  - `summary_lines(*, direction, source, source_generated_at, for_real, entries_in_file, selected, counts, record_path) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
def test_tally_zero_fills_every_outcome(apc):
    counts = apc.tally({"a": "applied"})
    assert counts == {"applied": 1, "already-applied": 0, "planned": 0,
                      "failed": 0, "unknown": 0, "not-attempted": 0}


def test_exit_code_zero_when_everything_applied(apc):
    assert apc.exit_code_for(apc.tally({"a": "applied", "b": "applied"})) == 0


def test_exit_code_zero_for_a_clean_dry_run(apc):
    assert apc.exit_code_for(apc.tally({"a": "planned", "b": "planned"})) == 0


def test_exit_code_one_when_anything_was_already_applied(apc):
    assert apc.exit_code_for(apc.tally({"a": "applied", "b": "already-applied"})) == 1


def test_exit_code_two_when_a_failure_changed_nothing(apc):
    """The first entry failed, so its batch never committed -- Cloudflare is untouched."""
    assert apc.exit_code_for(apc.tally({"a": "failed", "b": "not-attempted"})) == 2


def test_exit_code_three_when_a_failure_followed_a_successful_apply(apc):
    assert apc.exit_code_for(
        apc.tally({"a": "applied", "b": "failed", "c": "not-attempted"})) == 3


def test_exit_code_three_when_the_only_outcome_is_unknown(apc):
    """SPEC 8.1: an entry whose call raised a timeout did not tell us whether Cloudflare
    committed it.  Counting that as unchanged would let the process claim "nothing was changed"
    about a production DNS rewrite it cannot account for."""
    assert apc.exit_code_for(apc.tally({"a": "unknown", "b": "not-attempted"})) == 3


def test_exit_code_one_beats_zero_but_never_masks_a_failure(apc):
    assert apc.exit_code_for(
        apc.tally({"a": "already-applied", "b": "failed"})) == 2


def test_summary_says_entries_are_fqdns_not_sites(apc):
    """SPEC R8.2: the plan file carries no site information, and several FQDNs can belong to one
    Pantheon site.  Printing an FQDN count under the word "sites" would be a wrong number in an
    operator's incident notes."""
    lines = apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="2026-08-01T00:22:23Z",
        for_real=False, entries_in_file=217, selected=217,
        counts=apc.tally({"a": "planned"}), record_path="p-run-X.json")
    text = "\n".join(lines)
    assert "entries are FQDNs, not Pantheon sites" in text
    assert "217" in text


def test_summary_names_the_mode_unmistakably(apc):
    dry = "\n".join(apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=False,
        entries_in_file=1, selected=1, counts=apc.tally({"a": "planned"}),
        record_path="r.json"))
    real = "\n".join(apc.summary_lines(
        direction="plan", source="p.json", source_generated_at="x", for_real=True,
        entries_in_file=1, selected=1, counts=apc.tally({"a": "applied"}),
        record_path="r.json"))
    assert "DRY RUN -- no changes were made" in dry
    assert "FOR REAL" in real
    assert "DRY RUN" not in real


def test_summary_prints_the_source_files_own_timestamp(apc):
    """SPEC 11.3: this spec deliberately does not re-resolve targets, so the age of the file is
    the operator's only staleness signal -- and mtime survives neither a copy nor `git add`."""
    lines = apc.summary_lines(
        direction="revert", source="r.json", source_generated_at="2026-08-01T00:22:23Z",
        for_real=True, entries_in_file=1, selected=1,
        counts=apc.tally({"a": "applied"}), record_path="x.json")
    assert any("2026-08-01T00:22:23Z" in line for line in lines)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "tally or exit_code or summary" -v`
Expected: FAIL with `AttributeError: ... 'tally'`. Paste it.

- [ ] **Step 3: Implement**

```python
OUTCOMES = ("applied", "already-applied", "planned", "failed", "unknown", "not-attempted")


def tally(outcomes):
    """Count outcomes, zero-filling every key so no consumer has to .get() (SPEC 12.2)."""
    counts = dict.fromkeys(OUTCOMES, 0)
    for outcome in outcomes.values():
        if outcome not in counts:
            raise InvariantError(f"unknown outcome {outcome!r}")
        counts[outcome] += 1
    return counts


def exit_code_for(counts):
    """SPEC section 8, as a PURE function of the tally.

    Extracted deliberately: it is the most consequential logic in this script and would otherwise
    be reachable only through a full end-to-end run.  It covers the dry-run and post-apply paths;
    a validation failure returns 2 and an interrupt returns 130 directly from main(), before any
    outcome exists.

    `changed` counts applied PLUS unknown.  An entry whose batch call raised a timeout did not
    tell us whether Cloudflare committed it, and reporting "nothing was changed" about a
    production rewrite we cannot account for is exactly the silent failure PD#1 forbids.
    """
    if counts["failed"] or counts["unknown"]:
        changed = counts["applied"] + counts["unknown"]
        return 3 if changed else 2
    if counts["already-applied"]:
        return 1
    return 0


def summary_lines(*, direction, source, source_generated_at, for_real, entries_in_file,
                  selected, counts, record_path):
    """The block printed on EVERY exit path (SPEC R8.1, 11.3)."""
    mode = ("FOR REAL -- changes were made" if for_real
            else "DRY RUN -- no changes were made")
    return [
        f"apply-platform-domains-cloudflare: direction={direction}",
        f"  source: {source} (generated {source_generated_at})",
        f"  mode:   {mode}",
        f"  entries in file: {entries_in_file}   selected: {selected}   "
        "(entries are FQDNs, not Pantheon sites)",
        "  " + "   ".join(f"{name.replace('-', ' ')} {counts[name]}" for name in OUTCOMES),
        f"  record: {record_path}",
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): outcome tally, exit codes and summary"
```

---

### Task 7: Pass 2 — the report, and the dry run end to end

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces:
  - `merge_body(entry, delete_ids) -> dict`
  - `describe_change(fqdn, entry) -> str`
  - `report_entries(entries, validations, *, verbose) -> None`
  - a `main()` that runs parse → contract → select → validate → report → summary, and returns
    0/1/2. `--for-real` is accepted but still does nothing (Task 8 wires it).

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_body_puts_deletes_beside_the_files_posts_unchanged(apc):
    entry = plan_entry()
    body = apc.merge_body(entry, ["rec-1"])
    assert body["deletes"] == [{"id": "rec-1"}]
    assert body["posts"] == entry["body"]["posts"]
    assert set(body) == {"deletes", "posts"}


def test_merge_body_never_mutates_the_entry(apc):
    """The entry is written to the run record afterwards; a mutated body would misreport what
    the file said."""
    entry = plan_entry()
    apc.merge_body(entry, ["rec-1"])
    assert "deletes" not in entry["body"]


def test_describe_change_shows_both_sides_and_the_zone_id(apc):
    """SPEC 11.4: the zone ID, not a zone name -- the plan entry carries zone_id and nothing
    else about the zone, and looking up a name would be a second API read for cosmetics."""
    line = apc.describe_change("a.umich.edu", plan_entry())
    assert "a.umich.edu" in line
    assert "zone-a" in line
    assert "live-umich-x.pantheonsite.io" in line
    assert "23.185.0.4" in line
    assert "2620:12a:8000::4" in line


def run_main(apc, argv, tmp_path, client, monkeypatch):
    """Drive main() with a fake client and a frozen clock."""
    monkeypatch.setattr(apc, "cloudflare_client", lambda path: client)
    monkeypatch.setattr(apc, "now_utc", lambda: "2026-08-03T14:22:11Z")
    monkeypatch.chdir(tmp_path)
    return apc.main(argv)


def test_a_dry_run_makes_zero_batch_calls(apc, tmp_path, monkeypatch, capsys):
    """SPEC R2.6, the primary blast-radius control.  Asserted against the fake client's RECORDED
    calls, never inferred from the absence of an error."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert client.batch_calls == []
    assert code == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_a_dry_run_reports_the_change_it_would_make(apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert "a.umich.edu" in out
    assert "23.185.0.4" in out


def test_verbose_prints_the_exact_request_body(apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, ["-v", path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert "/zones/zone-a/dns_records/batch" in out
    assert '"deletes"' in out
    assert '"rec-1"' in out


def test_an_invalid_entry_aborts_the_run_at_exit_two_with_nothing_applied(
        apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 2
    assert client.batch_calls == []
    assert "ATTENTION" in capsys.readouterr().err


def test_every_invalid_entry_is_named_on_stderr_never_v_gated(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC R7.3 / 11.2: these are the only signal that a destructive run was refused."""
    doc = plan_doc(entries={"a.umich.edu": plan_entry(),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]], "b.umich.edu": [[]]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    err = capsys.readouterr().err
    assert "a.umich.edu" in err
    assert "b.umich.edu" in err
    assert "records-missing" in err


def test_an_already_applied_run_exits_one_and_calls_nothing(
        apc, tmp_path, monkeypatch, capsys):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 1
    assert client.batch_calls == []


def test_a_subset_run_warns_how_much_of_the_file_it_covers(
        apc, tmp_path, monkeypatch, capsys):
    doc = plan_doc(entries={"a.umich.edu": plan_entry(),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, ["--only", "a.umich.edu", path], tmp_path, client, monkeypatch)
    assert "ATTENTION: applying 1 of 2 entries" in capsys.readouterr().err


def test_an_unselected_entry_is_never_validated(apc, tmp_path, monkeypatch):
    """SPEC R7.2a: validating an entry the run will not touch would let an unrelated FQDN's
    drift abort a deliberately narrow, safe run."""
    doc = plan_doc(entries={"a.umich.edu": plan_entry(),
                            "b.umich.edu": plan_entry(fqdn="b.umich.edu")})
    path = write_doc(tmp_path, doc)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--only", "a.umich.edu", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert [call["name"]["exact"] for call in client.list_calls] == ["a.umich.edu"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "merge_body or describe_change or dry_run or invalid_entry or subset or unselected or already_applied_run" -v`
Expected: FAIL. Paste it.

- [ ] **Step 3: Implement `merge_body` and `describe_change`**

```python
def merge_body(entry, delete_ids):
    """The postable batch body (SPEC R5.1).

    `posts` is the file's own list, passed through UNMODIFIED -- the whole value of the plan file
    is that its body is "the exact JSON body to be used for the API call".  A shallow copy of the
    envelope keeps this from mutating the entry, which is written to the run record afterwards.

    Cloudflare executes Deletes before Posts inside one database transaction, which is what lets
    a CNAME and its replacement A records -- which cannot coexist -- be swapped in one step.
    """
    return {"deletes": [{"id": identifier} for identifier in delete_ids],
            "posts": entry["body"]["posts"]}


def describe_change(fqdn, entry):
    """One human line for one entry (SPEC 11.4), derived ENTIRELY from the entry.

    It shows the zone ID rather than a zone name because a plan/revert entry carries zone_id and
    nothing else about the zone (zone_name lives only in the inventory, which this script never
    reads).  Looking a name up would be a second Cloudflare read per entry, for cosmetics.
    """
    before = ", ".join(f"{item['type']} {item['content']}" for item in entry["delete_match"])
    after = ", ".join(f"{item['type']} {item['content']}" for item in entry["body"]["posts"])
    first = entry["body"]["posts"][0]
    flags = "proxied" if first.get("proxied") else "DNS-only"
    return (f"{fqdn}  zone {entry['zone_id']}  {before} -> {after}  "
            f"({flags}, ttl {first.get('ttl')})")


def report_entries(entries, validations, *, verbose) -> None:
    """Pass 2 (SPEC R3.3): identical in both modes, from the data pass 1 produced."""
    for fqdn, entry in sorted(entries.items()):
        validation = validations[fqdn]
        if validation.verdict == "already-applied":
            print(f"{fqdn}  already applied -- nothing to do", flush=True)
            continue
        print(describe_change(fqdn, entry), flush=True)
        if verbose:
            body = merge_body(entry, validation.delete_ids)
            print(f"    POST {entry['path']}", flush=True)
            print("    " + json.dumps(body, indent=4, sort_keys=True).replace("\n", "\n    "),
                  flush=True)
```

- [ ] **Step 4: Wire `main()`'s body (dry-run path only)**

Replace the `return 0    # replaced in Task 7` line with:

```python
        doc = read_apply_file(options.file)
        direction = check_file_contract(doc, options.file)
        entries = select_entries(doc["entries"], options.only)
        if len(entries) != len(doc["entries"]):
            print(f"ATTENTION: applying {len(entries)} of {len(doc['entries'])} entries in "
                  f"this file", file=sys.stderr, flush=True)
        client = cloudflare_client(options.config)
        validations = validate_entries(client, entries, verbose=options.verbose)

        invalid = {fqdn: v for fqdn, v in validations.items()
                   if v.verdict not in ("ready", "already-applied")}
        for fqdn, validation in sorted(invalid.items()):
            # NEVER -v-gated (SPEC R7.3): the only signal that a destructive run was refused.
            print(f"ATTENTION: {fqdn} {validation.verdict}: {validation.detail}",
                  file=sys.stderr, flush=True)
        if invalid:
            report_line(
                f"ERROR: {len(invalid)} of {len(entries)} selected entries did not match "
                "Cloudflare's current state; NOTHING was changed.  Re-generate the baseline "
                "with find-platform-domains-cloudflare and try again.")
            return 2

        report_entries(entries, validations, verbose=options.verbose)
        outcomes = {fqdn: ("already-applied" if v.verdict == "already-applied" else "planned")
                    for fqdn, v in validations.items()}
        counts = tally(outcomes)
        for line in summary_lines(
                direction=direction, source=options.file,
                source_generated_at=doc["generated"].get("at", "unknown"),
                for_real=options.for_real, entries_in_file=len(doc["entries"]),
                selected=len(entries), counts=counts, record_path="(none yet)"):
            print(line, flush=True)
        return exit_code_for(counts)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 6: Mutation-test the blast-radius gate (PD#14, MANDATORY)**

Temporarily make the dry-run path call `client.dns.records.batch(...)` for a ready entry. Run
`test_a_dry_run_makes_zero_batch_calls`. Confirm **RED**. Revert. Paste the red output into the
task report. This assertion is the one most likely to be green for the wrong reason.

- [ ] **Step 7: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): pass 2 report and the dry run"
```

---

### Task 8: Pass 3 — apply, verify, and stop at the first failure

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces:
  - `verify_records(entry, rows) -> bool`
  - `apply_entry(client, fqdn, entry, delete_ids) -> list[str]` — created record ids; raises
    `ApplyError`
  - `apply_all(client, entries, validations, *, verbose) -> tuple[dict, dict]` —
    `(outcomes, details)`
  - a `main()` that runs pass 3 under `--for-real`.

- [ ] **Step 1: Write the failing tests**

```python
def test_verify_records_accepts_exactly_the_posts(apc):
    assert apc.verify_records(plan_entry(), address_rows()) is True


def test_verify_records_rejects_a_leftover_record(apc):
    rows = [*address_rows(), row(identifier="rec-leftover")]
    assert apc.verify_records(plan_entry(), rows) is False


def test_apply_entry_calls_batch_with_the_resolved_ids_and_the_files_posts(apc):
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [address_rows()]})
    entry = plan_entry()
    created = apc.apply_entry(client, "a.umich.edu", entry, ["rec-1"])
    assert client.batch_calls == [{"zone_id": "zone-a", "deletes": [{"id": "rec-1"}],
                                   "posts": entry["body"]["posts"]}]
    assert sorted(created) == ["rec-a", "rec-b"]


def test_apply_entry_retries_verification_once_before_failing(apc, monkeypatch):
    """SPEC R6.2.  Cloudflare's own batch docs warn that "the propagation of changes is not
    atomic", so an immediate re-read can legitimately lag."""
    slept = []
    monkeypatch.setattr(apc, "sleep", slept.append)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[], address_rows()]})
    created = apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])
    assert slept == [apc.VERIFY_RETRY_SLEEP]
    assert sorted(created) == ["rec-a", "rec-b"]


def test_apply_entry_fails_when_verification_never_matches(apc, monkeypatch):
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    with pytest.raises(apc.ApplyError, match="a.umich.edu"):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])


def test_apply_entry_raises_apply_error_on_a_batch_failure(apc):
    client = FakeCloudflareClient(batch_error=cloudflare_error(400, 81058, "already exists"))
    with pytest.raises(apc.ApplyError, match="81058"):
        apc.apply_entry(client, "a.umich.edu", plan_entry(), ["rec-1"])


def three_entry_doc():
    return plan_doc(entries={
        "a.umich.edu": plan_entry(fqdn="a.umich.edu"),
        "b.umich.edu": plan_entry(fqdn="b.umich.edu"),
        "c.umich.edu": plan_entry(fqdn="c.umich.edu"),
    })


def three_entry_rows(applied=()):
    """Pass-1 rows for three FQDNs; those in `applied` are already swapped."""
    rows = {}
    for name in ("a.umich.edu", "b.umich.edu", "c.umich.edu"):
        base = address_rows() if name in applied else cname_rows()
        rows[name] = [[row(r.type, name, r.content, r.id) for r in base]]
    return rows


def test_a_failure_on_the_second_entry_leaves_the_third_not_attempted(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC R3.4 and 8.1: stop immediately, revert nothing, attempt nothing further -- and exit 3
    because the FIRST entry did commit."""
    path = write_doc(tmp_path, three_entry_doc())

    class FailOnSecond(FakeCloudflareClient):
        def _batch(self, **kwargs):
            if len(self.batch_calls) == 1:
                self.batch_calls.append(kwargs)
                raise cloudflare_error(400, 81058, "already exists")
            return super()._batch(**kwargs)

    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FailOnSecond(rows_by_name=rows)
    monkeypatch.setattr(apc, "sleep", lambda seconds: None)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    out = capsys.readouterr().out
    assert code == 3
    assert "applied 1" in out
    assert "failed 1" in out
    assert "not attempted 1" in out


def test_a_failure_on_the_first_entry_exits_two_because_nothing_committed(
        apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, three_entry_doc())
    client = FakeCloudflareClient(rows_by_name=three_entry_rows(),
                                  batch_error=cloudflare_error(400, 81058, "already exists"))
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 2


def test_a_connection_error_makes_the_outcome_unknown_and_exits_three(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC 8.1: the call did not tell us whether Cloudflare committed it, so "nothing was
    changed" is a claim this run cannot make."""
    path = write_doc(tmp_path, plan_doc())

    class Dropped(FakeCloudflareClient):
        def _batch(self, **kwargs):
            self.batch_calls.append(kwargs)
            raise cloudflare.APIConnectionError(request=None)

    client = Dropped(rows_by_name={"a.umich.edu": [cname_rows()]})
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 3
    assert "unknown 1" in capsys.readouterr().out


def test_a_clean_for_real_run_applies_every_entry_and_exits_zero(
        apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, three_entry_doc())
    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = FakeCloudflareClient(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert len(client.batch_calls) == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "verify_records or apply_entry or failure_on or connection_error or clean_for_real" -v`
Expected: FAIL. Paste it.

- [ ] **Step 3: Implement**

```python
def verify_records(entry, rows):
    """True when Cloudflare now holds exactly this entry's posts (SPEC R6.1)."""
    have = {record_key(r.type, r.name, r.content) for r in governed_records(rows)}
    want = {record_key(item["type"], item["name"], item["content"])
            for item in entry["body"]["posts"]}
    return have == want


def apply_entry(client, fqdn, entry, delete_ids):
    """One batch call, then the evidence (SPEC R5, R6).  Returns the created record ids.

    A 200 from the batch endpoint is Cloudflare's CLAIM that the swap happened; the record list
    is the EVIDENCE (PD#14).  The single retry exists because Cloudflare's own batch documentation
    warns that "the propagation of changes is not atomic", so a read served before the change
    lands would be a false mismatch on a healthy run.

    The typed client.dns.records.batch() is used rather than a raw POST of the file's body:
    measured on cloudflare 5.4.0, its maybe_transform returns the body byte-identical (including a
    key its schema does not define), so the file's exact body survives it, and check_file_contract
    has already asserted that the file's method and path are the ones this call produces.
    """
    body = merge_body(entry, delete_ids)
    try:
        client.dns.records.batch(zone_id=entry["zone_id"],
                                 deletes=body["deletes"], posts=body["posts"])
    except cloudflare.CloudflareError as e:
        raise ApplyError(f"{fqdn}: batch call failed: {api_error_text(e)}") from e

    for attempt in (1, 2):
        try:
            rows = list(client.dns.records.list(zone_id=entry["zone_id"],
                                                name={"exact": fqdn}))
        except cloudflare.CloudflareError as e:
            raise ApplyError(
                f"{fqdn}: the batch call succeeded but the verification read failed, so the "
                f"result is unconfirmed: {api_error_text(e)}") from e
        if verify_records(entry, rows):
            return [r.id for r in governed_records(rows)]
        if attempt == 1:
            sleep(VERIFY_RETRY_SLEEP)
    raise ApplyError(
        f"{fqdn}: the batch call succeeded but Cloudflare does not hold the expected records "
        f"afterwards, twice {VERIFY_RETRY_SLEEP}s apart; it now holds "
        f"{describe_keys(sorted({record_key(r.type, r.name, r.content) for r in governed_records(rows)}))}")


def apply_all(client, entries, validations, *, verbose):
    """Pass 3 (SPEC R3.4): in key order, one entry at a time, stopping at the first failure.

    Nothing already applied is reverted and nothing further is attempted -- PROMPT.md is explicit
    on both.  An entry whose call raised an unknown-outcome error (a dropped connection) is
    recorded as `unknown`, never `failed`: we do not know which it was, and exit_code_for treats
    unknown as changed for exactly that reason.
    """
    outcomes = {fqdn: "not-attempted" for fqdn in entries}
    details = {}
    for fqdn, entry in sorted(entries.items()):
        validation = validations[fqdn]
        if validation.verdict == "already-applied":
            outcomes[fqdn] = "already-applied"
            continue
        if validation.verdict != "ready":
            raise InvariantError(
                f"{fqdn} reached the apply pass with verdict {validation.verdict!r}; pass 1 "
                "should have aborted the run")
        if verbose:
            print(f"    POST {entry['path']}", flush=True)
        try:
            created = apply_entry(client, fqdn, entry, validation.delete_ids)
        except ApplyError as e:
            outcomes[fqdn] = "failed"
            details[fqdn] = {"error": str(e), "deleted_ids": validation.delete_ids}
            print(f"{fqdn}  FAILED", flush=True)
            report_line(f"ERROR: {e}")
            return outcomes, details
        except (cloudflare.APIConnectionError, TimeoutError, OSError) as e:
            outcomes[fqdn] = "unknown"
            details[fqdn] = {"error": f"{type(e).__name__}: {e}",
                             "deleted_ids": validation.delete_ids}
            print(f"{fqdn}  UNKNOWN -- the call did not complete", flush=True)
            report_line(
                f"ERROR: {fqdn}: the batch call did not complete ({type(e).__name__}), so "
                "whether Cloudflare applied it is UNKNOWN.  Check this FQDN by hand before "
                "re-running.")
            return outcomes, details
        outcomes[fqdn] = "applied"
        details[fqdn] = {"deleted_ids": validation.delete_ids, "created_ids": created}
        print(f"{fqdn}  applied", flush=True)
    return outcomes, details
```

**Measured against cloudflare 5.4.0, and load-bearing:**

```
cloudflare.APIConnectionError.__mro__
  -> (APIConnectionError, APIError, CloudflareError, Exception, BaseException, object)
issubclass(cloudflare.APIConnectionError, cloudflare.CloudflareError)  -> True
issubclass(cloudflare.APITimeoutError,   cloudflare.APIConnectionError) -> True
```

So a naive `except cloudflare.CloudflareError` in `apply_entry` **would swallow a dropped
connection** and report it as `failed` where SPEC §8.1 requires `unknown` — turning an exit 3 into
an exit 2, i.e. claiming "nothing was changed" about a call whose fate is unknown. That is the
exact silent failure PD#1 forbids, produced by clause ordering alone. The second line is why one
clause suffices: `APITimeoutError` is an `APIConnectionError`, so a timeout takes the same path.

**Order matters**: put the `APIConnectionError` check *inside* `apply_entry`'s batch `except`,
distinguishing it before wrapping. Implement it as:

```python
    try:
        client.dns.records.batch(...)
    except cloudflare.APIConnectionError:
        raise                      # the caller records `unknown`; do NOT convert to ApplyError
    except cloudflare.CloudflareError as e:
        raise ApplyError(f"{fqdn}: batch call failed: {api_error_text(e)}") from e
```

and in `apply_all` list `except cloudflare.APIConnectionError` **before** `except ApplyError`.

- [ ] **Step 4: Wire `--for-real` into `main()`**

Replace the dry-run outcome computation with:

```python
        report_entries(entries, validations, verbose=options.verbose)
        if options.for_real:
            print("FOR REAL -- changes WILL be made to Cloudflare", file=sys.stderr, flush=True)
            outcomes, details = apply_all(client, entries, validations,
                                          verbose=options.verbose)
        else:
            outcomes = {fqdn: ("already-applied" if v.verdict == "already-applied"
                               else "planned")
                        for fqdn, v in validations.items()}
            details = {}
        counts = tally(outcomes)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): pass 3, apply with post-apply verification"
```

---

### Task 9: The run record and interruption

**Files:**
- Modify: `apply-platform-domains-cloudflare`
- Modify: `tests/unit/test_apply_platform_domains_cloudflare.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces:
  - `outcome_path(input_path, at) -> str`
  - `outcome_document(...) -> dict`
  - `write_run_record(path, document) -> None` — raises `OutputWriteError`
  - a `main()` that writes the record on every exit path and applies SPEC §9.2's precedence rule.

- [ ] **Step 1: Write the failing tests**

```python
def test_outcome_path_is_named_run_not_applied(apc):
    """A DRY RUN writes one too, so "-applied-" would be a lie.  The timestamp makes a run
    incapable of clobbering a previous one."""
    path = apc.outcome_path("/tmp/platform-domains-cloudflare-plan.json", "2026-08-03T14:22:11Z")
    assert path.endswith("platform-domains-cloudflare-plan-run-20260803T142211Z.json")
    assert "-applied-" not in path


def test_the_run_record_is_written_on_a_clean_dry_run(apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})
    run_main(apc, [path], tmp_path, client, monkeypatch)
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["for_real"] is False
    assert record["run"]["direction"] == "plan"
    assert record["entries"]["a.umich.edu"]["outcome"] == "planned"


def test_the_run_record_is_written_when_validation_fails(apc, tmp_path, monkeypatch):
    """SPEC R9.1: EVERY exit path, including the fatal ones -- this is the record an operator
    attaches to a change ticket."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [[]]})
    code = run_main(apc, [path], tmp_path, client, monkeypatch)
    assert code == 2
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    assert record["run"]["exit_code"] == 2
    assert record["entries"]["a.umich.edu"]["outcome"] == "not-attempted"
    assert "records-missing" in record["entries"]["a.umich.edu"]["verdict"]


def test_the_run_record_captures_created_and_deleted_ids(apc, tmp_path, monkeypatch):
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), address_rows()]})
    run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    entry = record["entries"]["a.umich.edu"]
    assert entry["outcome"] == "applied"
    assert entry["deleted_ids"] == ["rec-1"]
    assert sorted(entry["created_ids"]) == ["rec-a", "rec-b"]


def test_a_record_write_failure_never_claims_nothing_changed(apc, tmp_path, monkeypatch, capsys):
    """SPEC 9.2: exiting 2 after a for-real run that rewrote records would assert "nothing was
    changed" about production DNS.  The earned code stands; the error is still named."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows(), address_rows()]})

    def boom(record_path, document):
        raise apc.OutputWriteError(f"cannot write {record_path}: disk full")

    monkeypatch.setattr(apc, "write_run_record", boom)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 0
    assert "cannot write" in capsys.readouterr().err


def test_a_record_write_failure_on_a_dry_run_is_exit_two(apc, tmp_path, monkeypatch):
    """The other branch: a dry run whose only deliverable was the record has genuinely failed."""
    path = write_doc(tmp_path, plan_doc())
    client = FakeCloudflareClient(rows_by_name={"a.umich.edu": [cname_rows()]})

    def boom(record_path, document):
        raise apc.OutputWriteError(f"cannot write {record_path}: disk full")

    monkeypatch.setattr(apc, "write_run_record", boom)
    assert run_main(apc, [path], tmp_path, client, monkeypatch) == 2


def test_an_interrupt_during_a_batch_call_records_unknown_and_exits_130(
        apc, tmp_path, monkeypatch, capsys):
    """SPEC 9.3: the in-flight entry is `unknown` -- never `failed`, never `not-attempted`."""
    path = write_doc(tmp_path, three_entry_doc())
    monkeypatch.setattr(apc.signal, "signal", lambda *args: None)  # see SPEC 9.3's test caveat

    class InterruptOnSecond(FakeCloudflareClient):
        def _batch(self, **kwargs):
            if len(self.batch_calls) == 1:
                raise KeyboardInterrupt
            return super()._batch(**kwargs)

    rows = three_entry_rows()
    for name in rows:
        rows[name] = [rows[name][0], [row(r.type, name, r.content, r.id)
                                      for r in address_rows()]]
    client = InterruptOnSecond(rows_by_name=rows)
    code = run_main(apc, ["--for-real", path], tmp_path, client, monkeypatch)
    assert code == 130
    record = json.loads(Path(apc.outcome_path(path, "2026-08-03T14:22:11Z")).read_text())
    outcomes = {k: v["outcome"] for k, v in record["entries"].items()}
    assert outcomes["a.umich.edu"] == "applied"
    assert outcomes["b.umich.edu"] == "unknown"
    assert outcomes["c.umich.edu"] == "not-attempted"
    assert "unknown 1" in capsys.readouterr().out


def test_the_flush_ignores_a_second_ctrl_c(apc, tmp_path, monkeypatch):
    """SPEC 9.3: a second Ctrl-C must not truncate the ONE record of what a destructive run
    did.  Asserted by observing the SIG_IGN call, since the real behavior cannot be provoked
    in-process."""
    calls = []
    monkeypatch.setattr(apc.signal, "signal", lambda sig, handler: calls.append((sig, handler)))
    path = write_doc(tmp_path, plan_doc())

    class Interrupting(FakeCloudflareClient):
        def _list(self, **kwargs):
            raise KeyboardInterrupt

    run_main(apc, [path], tmp_path, Interrupting(), monkeypatch)
    assert (apc.signal.SIGINT, apc.signal.SIG_IGN) in calls
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -k "outcome_path or run_record or record_write or interrupt or second_ctrl" -v`
Expected: FAIL. Paste it.

- [ ] **Step 3: Implement the record**

```python
def outcome_path(input_path, at):
    """<input-stem>-run-<YYYYMMDDThhmmssZ>.json, beside the input file (SPEC 12.1).

    Named `-run-`, not `-applied-`, because a DRY RUN writes one too -- with for_real false and
    every ready entry recorded as `planned`, which makes it the validation report an operator can
    attach to a change ticket before the change.  The timestamp makes a run incapable of
    clobbering a previous one.

    The repository's existing .gitignore line /platform-domains-cloudflare*.json already covers
    records written beside the conventional baseline, so no new ignore entry is needed.
    """
    stamp = at.replace("-", "").replace(":", "")
    source = Path(input_path)
    return str(source.with_name(f"{source.stem}-run-{stamp}.json"))


def outcome_document(*, at, direction, source, source_generated_at, for_real, argv, exit_code,
                     entries_in_file, selected, counts, outcomes, details, validations):
    """The SPEC 12.2 document."""
    entries = {}
    for fqdn in sorted(outcomes):
        item = {"outcome": outcomes[fqdn]}
        validation = validations.get(fqdn)
        if validation is not None and validation.verdict not in ("ready", "already-applied"):
            item["verdict"] = validation.verdict
            item["detail"] = validation.detail
        item.update(details.get(fqdn, {}))
        entries[fqdn] = item
    return {
        "run": {"at": at, "tool": "apply-platform-domains-cloudflare", "direction": direction,
                "source": source, "source_generated_at": source_generated_at,
                "for_real": for_real, "argv": list(argv), "exit_code": exit_code,
                "entries_in_file": entries_in_file, "selected": selected, "counts": counts},
        "entries": entries,
    }


def write_run_record(path, document) -> None:
    """Write the run record atomically (SPEC R9.1).

    Named OutputWriteError rather than reusing OSError because the failure is not always an
    OS-level one: json.dump raises TypeError/ValueError on an unserializable value, and calling
    that an OSError would be the "handle errors" mis-naming PD#2 forbids.
    """
    try:
        write_json_atomic(path, document)
    except (OSError, TypeError, ValueError) as e:
        raise OutputWriteError(
            f"cannot write the run record {path}: {type(e).__name__}: {e}") from e
```

- [ ] **Step 4: Restructure `main()` so every path writes the record**

The structure: an inner function computes the run, an outer `finally`-shaped block writes the
record and prints the summary.

```python
def main(argv):
    """(docstring from Task 1, extended with the finish() contract below)"""
    options = build_arg_parser().parse_args(argv)
    state = {"direction": "unknown", "generated_at": "unknown", "entries_in_file": 0,
             "selected": 0, "outcomes": {}, "details": {}, "validations": {},
             "for_real": options.for_real}

    def finish(code):
        """Print the summary and write the run record, on EVERY exit path (SPEC R8.1/R9.1).

        SIGINT is ignored first, so a second Ctrl-C cannot truncate the only record of what a
        destructive run did -- the same guard abort_run() uses in the main program.
        """
        with contextlib.suppress(ValueError):
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        at = now_utc()
        counts = tally(state["outcomes"])
        record_path = outcome_path(options.file, at)
        for line in summary_lines(
                direction=state["direction"], source=options.file,
                source_generated_at=state["generated_at"], for_real=state["for_real"],
                entries_in_file=state["entries_in_file"], selected=state["selected"],
                counts=counts, record_path=record_path):
            print(line, flush=True)
        try:
            write_run_record(record_path, outcome_document(
                at=at, direction=state["direction"], source=options.file,
                source_generated_at=state["generated_at"], for_real=state["for_real"],
                argv=argv, exit_code=code, entries_in_file=state["entries_in_file"],
                selected=state["selected"], counts=counts, outcomes=state["outcomes"],
                details=state["details"], validations=state["validations"]))
        except OutputWriteError as e:
            # SPEC 9.2 precedence: a run that CHANGED something keeps its earned code, because
            # exiting 2 would assert "nothing was changed" about production DNS.  A run that
            # changed nothing had the record as its only deliverable, so it becomes 2.
            report_line(f"ERROR: {e}")
            changed = counts["applied"] + counts["unknown"]
            return code if changed else 2
        return code

    try:
        require_usable_streams()
        ...   # the Task 7/8 body, updating `state` as it goes
        return finish(exit_code_for(tally(state["outcomes"])))
    except StartupError as e:
        report_line(f"ERROR: {e}")
        return finish(2)
    except KeyboardInterrupt:
        report_line("ERROR: interrupted")
        return finish(130)
    ...
```

**Two requirements for this restructure, both testable:**

1. `state["outcomes"]` MUST be populated with `not-attempted` for every selected entry **as soon
   as selection succeeds**, so a validation failure or an interrupt still produces a complete
   per-entry record.
2. A `KeyboardInterrupt` raised inside `apply_all` MUST leave the in-flight entry as `unknown`.
   Implement by wrapping the `apply_entry` call in `apply_all` with
   `except KeyboardInterrupt: outcomes[fqdn] = "unknown"; ...; raise`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./run-tests --fast tests/unit/test_apply_platform_domains_cloudflare.py -v`
Expected: PASS.

- [ ] **Step 6: Run the whole gate and the sibling check**

Run: `./run-tests --fast`
Run: `git diff --stat find-platform-domains-dns find-platform-domains-cloudflare tests/unit/test_find_platform_domains_dns.py tests/unit/test_find_platform_domains_cloudflare.py`
Expected: PASS; empty output.

- [ ] **Step 7: Commit**

```bash
git add apply-platform-domains-cloudflare tests/unit/test_apply_platform_domains_cloudflare.py
git commit -m "feat(apply-platform-domains-cloudflare): the run record and interrupt handling"
```

---

### Task 10: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `development/2026-07-31-platform-domain-util3/SPEC.md`
- Modify: `development/2026-07-30-platform-domain-util2/SPEC.md`
- Modify: `apply-platform-domains-cloudflare` (module docstring)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the `CLAUDE.md` subsection**

After the `### find-platform-domains-cloudflare (temporary utility)` subsection, add
`### apply-platform-domains-cloudflare (temporary utility)` covering, at minimum:

- what it takes (one plan or revert file) and what it refuses (an `-excluded.json`, by name)
- the three passes and the all-or-nothing validation property
- the six verdicts, naming which two are valid
- **the exit taxonomy, including that this script adds 3** where the two siblings use 0/1/2/130,
  and why
- `--for-real` as the blast-radius gate; `--only` as repeatable, and why it is not `nargs="+"`
- the run record: written on every exit path, dry runs included
- the deletion pointer

- [ ] **Step 2: Fix the two `CLAUDE.md` statements this increment falsifies**

1. In the `find-platform-domains-cloudflare` subsection: *"so an SDK upgrade has **two** places to
   check"* → **three**, naming this script as the third and noting it is the only one that writes.
2. In the same subsection: *"a separate, not-yet-written *applier* script is meant to read a plan
   or revert file"* → name `apply-platform-domains-cloudflare` and drop "not-yet-written".

- [ ] **Step 3: Record the supersession in util3's SPEC**

At `development/2026-07-31-platform-domain-util3/SPEC.md` §5.4, add a note that the applier's
per-entry tolerance ("skip the entry and report it") was **superseded** by
`development/2026-08-03-platform-domain-util4/SPEC.md` R4, and why.

- [ ] **Step 4: Extend the deletion checklist**

At `development/2026-07-30-platform-domain-util2/SPEC.md` §11, add this script's share (SPEC §19's
six items).

- [ ] **Step 5: Verify no documentation claim is now false**

```bash
grep -n "not-yet-written" CLAUDE.md          # expected: no matches
grep -n "two.*places to check" CLAUDE.md     # expected: no matches
./run-tests --fast                            # the house-rules tests read CLAUDE.md
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md apply-platform-domains-cloudflare \
        development/2026-07-31-platform-domain-util3/SPEC.md \
        development/2026-07-30-platform-domain-util2/SPEC.md
git commit -m "docs(apply-platform-domains-cloudflare): document the applier and its taxonomy"
```

---

## After Task 10 — before submission

1. **Run SPEC §15's offline acceptance items 1–6 and paste the real output into SPEC §15's
   "Results" section.** An unrun acceptance suite is PD#14 exactly.
2. **STOP 2** — the live canary (SPEC §15 items 7–13) requires the exact phrase `RUN LIVE` **and**
   a named throwaway hostname. Do not run it otherwise.
3. **STOP 3** — dispatch a `psh-reviewer` with **fresh context**, seeing only
   `development/2026-08-03-platform-domain-util4/SPEC.md` and the branch diff, per
   `prompts/adversarial-review.md`.
4. **Answer SPEC §22's eight closing audit questions**, with evidence, in this folder.

---

## Plan self-review

**Spec coverage.** Every SPEC section maps to a task: §6 → Task 2; §7 → Tasks 4–5; §8 → Task 6;
§9.1 → Tasks 1, 3, 8; §9.2/§9.3 → Task 9; §10 → Tasks 7–8 (the "never does" list is asserted by
`test_a_dry_run_makes_zero_batch_calls`, `test_an_invalid_entry_aborts_the_run_at_exit_two_…`, and
`test_a_failure_on_the_second_entry_…`); §11 → Tasks 6–8; §12 → Task 9; §13/§14 → every task;
§16 → Task 3; §17 → Tasks 1, 3; §18/§19 → Task 10; §20 → nothing to build, by definition.

**Two gaps found and closed while reviewing:**

1. SPEC §14 group 14 requires a `--help` assertion and doomed-stream tests — Task 1 Step 6 has
   them, but the **`--bogus 2>/dev/full` exits 120** documented exception had no test. It needs
   none: it is an argparse behavior this script does not control, and SPEC §8.3 states it as an
   accepted exception rather than a requirement. Recorded here so a reviewer does not read its
   absence as an oversight.
2. `cloudflare.APIConnectionError` **is** a `CloudflareError` subclass (verified against 5.4.0,
   MRO pasted in Task 8), so a naive `except cloudflare.CloudflareError` in `apply_entry` would
   swallow it and report `failed` where SPEC §8.1 requires `unknown` — turning an exit 3 into an
   exit 2 and claiming nothing was changed. Task 8 Step 3 now calls this out explicitly with the
   required clause ordering, and `test_a_connection_error_makes_the_outcome_unknown_and_exits_three`
   is the guard. `APITimeoutError` subclasses `APIConnectionError`, so one clause covers both.

**Type consistency.** `Validation(verdict, detail, delete_ids)` is produced in Task 5 and consumed
in Tasks 7–9 under those exact names. `tally()` returns a dict keyed by `OUTCOMES` and is consumed
by `exit_code_for` and `summary_lines` under those keys. `apply_all` returns
`(outcomes, details)`, consumed by Task 9's `outcome_document` under those names.
