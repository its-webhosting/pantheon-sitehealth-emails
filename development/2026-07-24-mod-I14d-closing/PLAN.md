# I14d — Closing the Modularization Campaign: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every code-touching subagent is dispatched as **`psh-implementer`**, every reviewer as
> **`psh-reviewer`** (CLAUDE.md § Dispatching subagents). A dispatch that cannot use them MUST
> stop and say so.

**Goal:** Close the modularization campaign — make every repository document true about the
architecture that now exists, record the configuration migration (none required), fix the seven
findings LEDGER I14c ledgered here, resolve the ledger, and answer CAMPAIGN.md §17.

**Architecture:** Documentation is verified before it is rewritten. Task 1 builds an instrument
that decides the mechanizable claims in each document and marks the rest PROSE for a reviewer,
producing `CLAIMS.md`; Tasks 3–5 write from that table, so no warning can leave a document
except through an explicit `drop-with-reason` row. Task 2 is the only code in the increment.

**Tech Stack:** Python 3.12 (stdlib `ast`/`pathlib`/`subprocess` only for the instrument),
pytest, ruff 0.15.22 + pyright 1.1.411 via `./run-tests`, syrupy snapshots, git.

**Spec:** `development/2026-07-24-mod-I14d-closing/SPEC.md`, committed at **`6d405f7`** — this
is `$BASE`, the increment base for every byte-identity diff.

## Global Constraints

- **Behavior bar (SPEC §3):** the four e2e goldens and all **107** `.ambr` snapshots stay
  byte-identical. No notice body, template, chart, csv value, exit code, resume semantic, or
  artifact gate changes. `git diff $BASE -- tests/e2e/__snapshots__/` and
  `git diff $BASE -- '*.ambr'` MUST both be empty at every commit.
- **An existing golden or snapshot going red is a defect in this increment** — never refreshed
  to green (CAMPAIGN.md Invariant 1, PD#14). `./run-tests --update-goldens` is FORBIDDEN here.
- **Test-first** per `mattpocock-skills:tdd` (`prompts/implementation-standards.md` overrides
  `superpowers:test-driven-development`). Refactoring is not part of the red→green loop.
- **Every task report cites the directives it applied by number with a verbatim quote**
  (CLAUDE.md § Dispatching subagents) and MUST verify its own report file exists after writing
  it (LEDGER I14a: a silent `Write` failure has happened twice).
- **Baseline to preserve:** 1055 passed / 1 skipped / 107 snapshots (I14c close). Expected at
  I14d close: **1060 passed / 1 skipped / 107 snapshots**. Any other number MUST be explained
  in the ledger entry, never absorbed.
- **Column-0 `f"""` notice literals are never re-indented** (Invariant 8); `git diff -w` is not
  acceptable evidence. No task here edits a notice body, so any diff touching one is a defect.
- **Increment folder:** `development/2026-07-24-mod-I14d-closing/`. The instrument lives in its
  `tools/` subdirectory, which is ruff-excluded (`extend-exclude = ["development/2*"]`).

## Task-number mapping to SPEC §6

SPEC §6 fixes T1 first and T6 last and says its T5 (the seven findings) "MAY move earlier".
This plan exercises that: the findings run second, because Task 3 rewrites CLAUDE.md and must
describe the collapsed comment blocks and the new registration test as facts, not futures.

| Plan task | SPEC §6 task | Deliverable |
|---|---|---|
| 1 | T1 | `tools/claim_check.py` + `CLAIMS.md` |
| 2 | T5 | The seven findings (the only code in the increment) |
| 3 | T2 | CLAUDE.md final-state rewrite |
| 4 | T3 | README, `docs/`, `prompts/`, `tests/README.md`, `CONTEXT.md`, memory |
| 5 | T4 | `docs/config-migration.md`, sample-toml, production instruction |
| 6 | T6 | Ledger resolution, `CLOSING-AUDIT.md`, `RETROSPECTIVE.md`, ledger entry |

## File Structure

**Created**

| Path | Responsibility |
|---|---|
| `development/2026-07-24-mod-I14d-closing/tools/claim_check.py` | Decide mechanizable claims; `--self-test` proves it can go red; `--gate` exits non-zero on FAIL/ERROR |
| `development/2026-07-24-mod-I14d-closing/CLAIMS.md` | One row per claim: claim, kind, verdict, disposition. The source Tasks 3–5 write from |
| `tests/integration/test_notice_registration.py` | Enforce, by AST, that every constructed notice code is a registered `NOTICE_*` constant |
| `docs/config-migration.md` | The migration record: no key changes required, with its audit trail |
| `development/2026-07-17-modularization-campaign/CLOSING-AUDIT.md` | The nine §17 answers, each with pasted evidence |
| `development/2026-07-17-modularization-campaign/RETROSPECTIVE.md` | Goal vs. measured outcome; the failure classes worth carrying |

**Modified**

| Path | Change |
|---|---|
| `psh/notice.py` | `__post_init__` gains strict `severity` validation (the increment's only production-code edit) |
| `tests/unit/test_notice.py` | +1 test (severity validation) |
| `tests/integration/test_gather_drupal.py` | +1 test (`Severity(level)` `ValueError`) |
| `tests/unit/test_cachecheck_consolidation.py` | `_CACHED` removed |
| 20 registering modules (19 with a block + `psh/cli.py` with none) | Registration comment collapsed to one line each |
| `tests/integration/test_check_pantheon_cdn_change.py`, `tests/integration/test_drupal_notice_render.py`, + the remainder Task 2 locates | Stale comments / the `multisite-check` banner corrected |
| `CLAUDE.md` | Rewritten (Task 3) |
| `README.md`, `tests/README.md`, `CONTEXT.md`, `docs/*.md`, `prompts/*.md` | Refreshed (Task 4) |
| `sample-pantheon-sitehealth-emails.toml` | Verified key-by-key; comments corrected (Task 5) |
| `~/.claude/projects/-workspace/memory/*.md` | 9 files de-staled (Task 4) |
| `development/2026-07-17-modularization-campaign/LEDGER.md` | I14d entry (Task 6) |
| `development/2026-07-17-modularization-campaign/CAMPAIGN.md` | Status line: campaign complete (Task 6) |

---

### Task 1: The claim instrument and the claim inventory

**Files:**
- Create: `development/2026-07-24-mod-I14d-closing/tools/claim_check.py`
- Create: `development/2026-07-24-mod-I14d-closing/CLAIMS.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `claim_check.py` CLI — `--self-test` (red demonstration, exit 1 on any missed
  expectation), `--gate FILE...` (exit 1 on any FAIL/ERROR), and bare `FILE...` (print the
  markdown table). `CLAIMS.md` rows: `| claim | kind | verdict | disposition |` with
  disposition ∈ {`keep-verified`, `fix`, `drop-with-reason`}.

- [ ] **Step 1: Write the instrument**

Create `development/2026-07-24-mod-I14d-closing/tools/claim_check.py` with exactly this content:

```python
#!/usr/bin/env python
"""Decide the mechanizable claims in a repository document (campaign I14d, SPEC §2.1).

CAMPAIGN.md §7 obligation 4 requires every claim a document moves or writes to be VERIFIED,
not assumed.  This tool decides the subset a machine can decide with confidence and marks
everything else PROSE, so an undecided claim reaches a reviewer instead of passing silently
(PD#1) -- and so a claim the tool merely cannot parse is never reported as false.

Verdicts:
  PASS   checked true
  FAIL   checked false
  PROSE  not mechanizable, or not decidable with confidence -- a human must verify
  ERROR  the check itself could not run (loud; never treated as PASS)

PD#14: --self-test runs every decision kind against a TRUE claim (expect PASS) and a FALSE
claim (expect FAIL) and exits non-zero unless both land.  A tool that has not been shown able
to go red is a claim, not evidence.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# development/<slug>/tools/claim_check.py -> repo root
REPO = Path(__file__).resolve().parents[3]

PLACEHOLDER = set("{}<>*|…$ ")
SOURCE_EXT = (".py", ".toml", ".md", ".json", ".html", ".txt", ".sh", ".php", ".ambr", ".lock")
PKG_ROOTS = ("psh", "check", "plugin", "tests", "script_context")
SKIP_DIRS = {".git", ".venv", "vendor", "node_modules", "build", "__pycache__",
             ".pytest_cache", ".ruff_cache", "logs"}


@dataclass
class Claim:
    text: str
    kind: str
    verdict: str
    detail: str


# ── the repo index ───────────────────────────────────────────────────────────────────
_PATHS: set[str] | None = None


def _relative_paths() -> set[str]:
    """Every repo-relative file path, so a claim may name a file by a partial path."""
    global _PATHS                                       # noqa: PLW0603
    if _PATHS is None:
        found: set[str] = set()
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            rel = Path(root).relative_to(REPO)
            found.update(f if str(rel) == "." else f"{rel}/{f}" for f in files)
        _PATHS = found
    return _PATHS


# ── the loaded namespaces (the authority for sc.* and the psh re-export surface) ──────
_NAMESPACES: dict[str, list[str]] | None = None


def _namespaces() -> dict[str, list[str]] | None:
    """dir() of the loaded facade and program.

    Importing psh.cli runs the sc-exposure block and the re-export block, so names bound at
    runtime are visible -- an AST of psh/__init__.py cannot see either.  Returns None when the
    import fails, and every dependent claim then reports ERROR rather than PASS.
    """
    global _NAMESPACES                                  # noqa: PLW0603
    if _NAMESPACES is None:
        code = (
            "import os; os.environ.setdefault('MPLBACKEND', 'Agg');"
            "import json, psh, psh.cli, script_context;"
            "print(json.dumps({"
            " 'script_context': sorted(n for n in dir(script_context) if not n.startswith('_')),"
            " 'psh': sorted(set(dir(psh)) | set(dir(psh.cli)))}))"
        )
        try:
            out = subprocess.run(                       # noqa: S603
                [sys.executable, "-c", code], cwd=REPO, capture_output=True,
                text=True, check=True, timeout=180,
            ).stdout
            _NAMESPACES = json.loads(out)
        except (subprocess.SubprocessError, json.JSONDecodeError):
            _NAMESPACES = {}
    return _NAMESPACES or None


# ── AST helpers ──────────────────────────────────────────────────────────────────────
def _module_level_names(path: Path) -> set[str]:
    """Every name a module binds at module level: def, class, assignment, import."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _test_names(path: Path) -> set[str]:
    return {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


# ── counters ─────────────────────────────────────────────────────────────────────────
def _count_register_calls() -> int:
    n = 0
    for root in ("psh", "check", "plugin"):
        for path in (REPO / root).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == "register":
                    n += 1
    return n


def _count_main_raw_lines() -> int:
    tree = ast.parse((REPO / "psh" / "cli.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return (node.end_lineno or node.lineno) - node.lineno + 1
    return -1


def _count_packages(root: str) -> int:
    return sum(1 for init in (REPO / root).glob("*/__init__.py")
               if init.read_text(encoding="utf-8").strip())


COUNTERS = (
    (re.compile(r"(\d+)[ -]roster codes|roster of (\d+)"), _count_register_calls,
     "registered notice codes"),
    (re.compile(r"(\d+) raw"), _count_main_raw_lines, "main() raw lines"),
    (re.compile(r"(\d+) check packages"), lambda: _count_packages("check"), "check packages"),
    (re.compile(r"(\d+) plugin packages"), lambda: _count_packages("plugin"), "plugin packages"),
)


# ── classification ───────────────────────────────────────────────────────────────────
def _tokens(doc: str):
    for line in doc.splitlines():
        yield from re.findall(r"`([^`\n]+)`", line)


def _clean(tok: str) -> str:
    tok = tok.strip().rstrip(".,;:")
    tok = re.sub(r"\(\)$", "", tok)          # sc.console.print() -> sc.console.print
    return re.sub(r":\d+(-\d+)?$", "", tok)  # psh/cli.py:369-990 -> psh/cli.py


def _is_pathish(tok: str) -> bool:
    return bool(re.fullmatch(r"[\w./@-]+", tok)) and ("/" in tok or tok.endswith(SOURCE_EXT))


def _decide_token(tok: str) -> Claim | None:
    if any(c in tok for c in PLACEHOLDER):
        return None
    tok = _clean(tok)
    if not tok:
        return None

    if tok.startswith("sc."):
        match = re.match(r"sc\.([A-Za-z_]\w*)", tok)
        if match is None:
            return None
        spaces = _namespaces()
        if spaces is None:
            return Claim(tok, "SC", "ERROR", "could not import script_context")
        name = match.group(1)
        ok = name in spaces["script_context"]
        return Claim(tok, "SC", "PASS" if ok else "FAIL", "" if ok else f"sc has no {name!r}")

    if "::" in tok:
        rel, _, node = tok.partition("::")
        path = REPO / rel
        if not path.exists():
            return Claim(tok, "NODE", "FAIL", f"{rel} does not exist")
        ok = node.split("[")[0] in _test_names(path)
        return Claim(tok, "NODE", "PASS" if ok else "FAIL",
                     "" if ok else f"{rel} defines no {node}")

    if tok.startswith(("-", ".", "/")):       # artifact fragments, slash commands, URL paths
        return None
    if re.search(r"YYYY|MMDD|NNN", tok):      # a template name, not a path
        return None

    if _is_pathish(tok):
        probe = tok.rstrip("/")
        resolved = (REPO / probe).exists() or any(
            f == probe or f.endswith("/" + probe) for f in _relative_paths())
        if resolved:
            return Claim(tok, "PATH", "PASS", "")
        # FAIL only where the shape is unambiguously a repo path: a source extension AND a
        # directory component.  An external URL fragment, an artifact template, or a file named
        # by basename alone is undecidable here -- and undecidable is never reported as false.
        if "/" in probe and probe.endswith(SOURCE_EXT):
            return Claim(tok, "PATH", "FAIL", "path does not exist")
        return Claim(tok, "PATH", "PROSE", "not resolvable as a repo path -- verify by hand")

    parts = tok.split(".")
    if len(parts) > 1 and parts[0] in PKG_ROOTS and all(p.isidentifier() for p in parts):
        for k in range(len(parts), 0, -1):
            base = REPO.joinpath(*parts[:k])
            target = base.with_suffix(".py") if base.with_suffix(".py").exists() else (
                base / "__init__.py" if (base / "__init__.py").exists() else None)
            if target is None:
                continue
            if k == len(parts):
                return Claim(tok, "SYMBOL", "PASS", "")          # the module or package itself
            attr = parts[k]
            if attr in _module_level_names(target):
                return Claim(tok, "SYMBOL", "PASS", "")
            spaces = _namespaces() or {}
            if attr in spaces.get(parts[0], []):
                return Claim(tok, "SYMBOL", "PASS", "re-export")
            return Claim(tok, "SYMBOL", "FAIL",
                         f"{target.relative_to(REPO)} defines no {attr!r}")
        return Claim(tok, "SYMBOL", "FAIL", "no module or package resolves for this dotted name")

    return None


def check_document(path: Path) -> list[Claim]:
    doc = path.read_text(encoding="utf-8")
    claims: list[Claim] = []
    seen: set[str] = set()
    for tok in _tokens(doc):
        claim = _decide_token(tok)
        if claim and claim.text not in seen:
            seen.add(claim.text)
            claims.append(claim)
    for pattern, truth, label in COUNTERS:
        for match in pattern.finditer(doc):
            stated = next((g for g in match.groups() if g), None)
            if stated is None:
                continue
            actual = truth()
            ok = int(stated) == actual
            claims.append(Claim(match.group(0), "COUNT", "PASS" if ok else "FAIL",
                                "" if ok else f"{label}: stated {stated}, actual {actual}"))
    return claims


def _print_table(path: Path, claims: list[Claim]) -> None:
    print(f"\n## {path}")
    print("| claim | kind | verdict | detail |")
    print("|---|---|---|---|")
    for c in claims:
        print(f"| `{c.text}` | {c.kind} | {c.verdict} | {c.detail} |")


# ── the tool's own red demonstration (PD#14) ─────────────────────────────────────────
SELF_TEST_DOC = """
true path `psh/notice.py` and false path `psh/no_such_file.py`
true symbol `psh.notice.Notice` and false symbol `psh.notice.NoSuchSymbol`
true node `tests/unit/test_notice.py::test_notice_is_frozen` and
false node `tests/unit/test_notice.py::test_no_such_test`
true facade `sc.console` and false facade `sc.no_such_facade_name`
"""

EXPECTED = {
    "psh/notice.py": "PASS", "psh/no_such_file.py": "FAIL",
    "psh.notice.Notice": "PASS", "psh.notice.NoSuchSymbol": "FAIL",
    "tests/unit/test_notice.py::test_notice_is_frozen": "PASS",
    "tests/unit/test_notice.py::test_no_such_test": "FAIL",
    "sc.console": "PASS", "sc.no_such_facade_name": "FAIL",
}


def self_test() -> int:
    here = Path(__file__).parent
    doc = here / ".self_test.md"
    doc.write_text(SELF_TEST_DOC, encoding="utf-8")
    try:
        got = {c.text: c.verdict for c in check_document(doc)}
    finally:
        doc.unlink()

    true_codes = _count_register_calls()
    counts = here / ".self_test_counts.md"
    counts.write_text(f"{true_codes} roster codes\n999 roster codes\n", encoding="utf-8")
    try:
        count_verdicts = sorted(c.verdict for c in check_document(counts) if c.kind == "COUNT")
    finally:
        counts.unlink()

    failures = [f"{k}: expected {v}, got {got.get(k, 'MISSING')}"
                for k, v in EXPECTED.items() if got.get(k) != v]
    if count_verdicts != ["FAIL", "PASS"]:
        failures.append(f"COUNT: expected one PASS and one FAIL, got {count_verdicts}")
    for line in failures:
        print(f"SELF-TEST FAIL  {line}")
    if failures:
        return 1
    print(f"SELF-TEST PASS  {len(EXPECTED)} verdicts + COUNT both ways "
          f"(registered codes = {true_codes})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--gate", action="store_true",
                        help="exit non-zero on any FAIL or ERROR that is not allowed")
    parser.add_argument("--allow", type=Path, default=None,
                        help="file of accepted claim texts, one per line (# comments).  Each "
                             "entry MUST carry a reason: a document may deliberately name "
                             "something that no longer exists, and an entry without a reason "
                             "is a suppressed defect")
    parser.add_argument("--self-test", action="store_true",
                        help="prove each decision kind can go red (PD#14)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.files:
        parser.error("no files given")

    allowed: set[str] = set()
    if args.allow and args.allow.exists():
        allowed = {line.split("#")[0].strip()
                   for line in args.allow.read_text(encoding="utf-8").splitlines()
                   if line.split("#")[0].strip()}

    bad = 0
    for path in args.files:
        claims = check_document(path)
        _print_table(path, claims)
        bad += sum(1 for c in claims
                   if c.verdict in ("FAIL", "ERROR") and c.text not in allowed)
    print(f"\n{bad} unallowed FAIL/ERROR verdict(s)")
    return 1 if (args.gate and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the self-test — it MUST pass, and its red half is the evidence**

Run:
```bash
cd /workspace && python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --self-test
```
Expected: `SELF-TEST PASS  8 verdicts + COUNT both ways (registered codes = 36)`, exit 0.

If it reports `SELF-TEST FAIL` for `sc.console`, the `script_context` import failed — that is
an ERROR verdict, not a PASS, and MUST be fixed (run inside the venv: `source .venv/bin/activate`).
**Paste the full output into the task report.** This is the tool's red demonstration: the four
`FAIL` expectations are false claims the tool caught.

- [ ] **Step 3: Run the tool over every document in scope**

Run:
```bash
cd /workspace && python development/2026-07-24-mod-I14d-closing/tools/claim_check.py \
    CLAUDE.md README.md CONTEXT.md tests/README.md docs/*.md prompts/*.md \
    ~/.claude/projects/-workspace/memory/*.md > /tmp/claims-raw.md; tail -1 /tmp/claims-raw.md
```

**Expected, measured 2026-07-24 at plan time: `21 unallowed FAIL/ERROR verdict(s)`.** A
materially different number means the tool or the tree changed — investigate before writing
`CLAIMS.md`; do not adjust the number to match. The 21 are:

| Claim | Where | Nature |
|---|---|---|
| `psh/_legacy.py` (×7), `psh._legacy` (×2) | CLAUDE.md, README, 4 memory files | Deleted at I14a — **fix** |
| `psh.SMTP_SSL` (×3), `sc.text_maker` (×2), `sc.add_notice` | CLAUDE.md, memory | Deliberate "this is gone" mentions — **allow** |
| `sc.db_reconnects_by_site`, `sc.db_reconnect_failures_by_site` (×2 each) | memory | Moved onto `RunState` at I13 — **fix** |
| `docs/superpowers/specs/…`, `docs/superpowers/plans/…` | `dns-modularization.md` memory | Repo convention is `development/<slug>/` — **fix** |

- [ ] **Step 4: Write the allow file and `CLAIMS.md`**

Create `development/2026-07-24-mod-I14d-closing/claims-allow.txt` — a document may deliberately
name something that no longer exists, and the entry is only legitimate with a reason:

```
# Claims a document deliberately makes ABOUT something that no longer exists.
# Each entry MUST carry its reason; an entry without one is a suppressed defect.
sc.text_maker    # CLAUDE.md states the shared HTML2Text instance is GONE; naming it is the point
sc.add_notice    # CLAUDE.md states the module-level free functions were REMOVED (I14c)
psh.SMTP_SSL     # CLAUDE.md warns that a stale patch at this old binding now fails loudly
```

Then create `development/2026-07-24-mod-I14d-closing/CLAIMS.md` with a section per document.
Copy every row from step 3 and add a **disposition** column:

- `keep-verified` — verdict PASS; the claim survives the rewrite unchanged.
- `fix` — verdict FAIL; state the corrected claim in the row, so Tasks 3–5 write the fix
  rather than re-deriving it.
- `drop-with-reason` — the claim leaves the document; the reason goes in the row.
- `allowed` — a deliberate mention, matching an entry in `claims-allow.txt`.

**PROSE rows are not optional.** The tool marks a claim PROSE when it cannot decide it with
confidence — an external URL fragment, a file named by basename alone (`ruff-broad.toml`,
deleted at I14b, lands here), or anything unparseable. Each still needs a disposition, from
step 5's review.

Head the file with the SPEC §2.2 **Keep list** (22 rows) as a checklist, each row marked with
the document section that will carry it. This is what Task 3 is audited against.

- [ ] **Step 5: Dispatch a `psh-reviewer` for the PROSE rows**

Dispatch a fresh-context `psh-reviewer` with this brief:

> Read `development/2026-07-24-mod-I14d-closing/SPEC.md` §2.1–§2.2, `CLAIMS.md`, and
> `CLAUDE.md`. For every claim in CLAUDE.md that `claim_check.py` did NOT decide (it is not in
> `CLAIMS.md`, or is marked PROSE), verify it against the code and report: claim, verdict
> (TRUE / FALSE / UNVERIFIABLE), evidence (file:line or command output), and a proposed
> disposition. Prioritize behavioral claims — "X happens before Y", "this is the only …",
> "never …", "always …" — over descriptive ones. Cite the directives you applied by number
> with a verbatim quote. Verify your report file exists after writing it.

Fold the reviewer's findings into `CLAIMS.md` as additional rows.

- [ ] **Step 6: Commit**

```bash
cd /workspace && git add development/2026-07-24-mod-I14d-closing/ && \
git commit -m "docs(campaign-I14d): the claim instrument and the claim inventory

tools/claim_check.py decides the mechanizable claims in a document (paths,
symbol homes, test nodes, sc facade names, counts) and marks the rest PROSE
so nothing passes unverified (PD#1).  --self-test proves each decision kind
can return both verdicts (PD#14).

CLAIMS.md is the disposition table Tasks 3-5 write from, so a load-bearing
warning can only leave a document through an explicit drop-with-reason row.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The seven findings (SPEC §2.5)

**Files:**
- Modify: `psh/notice.py:40-52` (`__post_init__`)
- Modify: `tests/unit/test_notice.py` (+1 test)
- Create: `tests/integration/test_notice_registration.py`
- Modify: `tests/integration/test_gather_drupal.py` (+1 test)
- Modify: `tests/unit/test_cachecheck_consolidation.py:16-32` (drop `_CACHED`)
- Modify: 20 registering modules (comment collapse)
- Modify: `tests/integration/test_check_pantheon_cdn_change.py:57`,
  `tests/integration/test_drupal_notice_render.py:63`, + the remainder located in step 10

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Notice.__post_init__` raising `TypeError` on a non-`Severity` severity;
  `tests/integration/test_notice_registration.py` with three tests
  (`test_every_notice_code_is_a_registered_constant`,
  `test_every_notice_constant_comes_from_register`,
  `test_static_codes_match_the_runtime_roster`). Task 3 documents all of these as facts.

**Measured precondition (verified 2026-07-24, SPEC D-i14d-9):** all 40 `Notice(...)` sites pass
a `Severity` member — 36 enum literals, 2 `Severity(level)` conversions in `psh/gather.py:176,193`,
2 parametrized test fakes that pass real members. Strict validation breaks nothing.

- [ ] **Step 1: Write the failing severity test**

Append to `tests/unit/test_notice.py`:

```python
def test_severity_must_be_a_severity_member():
    # A bare string reaches the projection's icon map and surfaces as an anonymous
    # KeyError: 'warn' -- naming neither the notice nor the module (PD#2).  Most producers
    # live in check/, outside pyright's scope, so the type system cannot catch it either.
    # VALIDATION, not coercion: the csv_extra posture (D-i14c-1) applied to severity.
    with pytest.raises(TypeError, match=r"Notice\('frozen'\)\.severity"):
        Notice(severity="warning", code="frozen", html="<p>x</p>")
```

- [ ] **Step 2: Run it and watch it fail for the right reason**

Run: `cd /workspace && ./run-tests tests/unit/test_notice.py::test_severity_must_be_a_severity_member -q`
Expected: FAIL — `DID NOT RAISE <class 'TypeError'>`. (Not an import error, not a match
failure: the point is that a bare string constructs fine today.)

- [ ] **Step 3: Implement the validation**

In `psh/notice.py`, replace the body of `__post_init__` (keeping its docstring, and extending
it with the severity sentence) so the severity check runs **first**:

```python
    def __post_init__(self) -> None:
        """Reject a non-Severity severity and a non-str csv_extra element AT THE PRODUCER, by name.

        VALIDATION, not coercion (SPEC I14c D-i14c-1 keeps the format spec at the producer).  Most
        producers live in check/, which pyright does not gate (pyproject [tool.pyright] includes
        only psh/), so a forgotten str() around an int csv field would otherwise surface much later
        as an anonymous `TypeError: sequence item 2: expected str instance, int found` from
        script_context's ",".join -- naming neither the notice nor the module (PD#2).  A bare
        severity string ("warn") fails the same way, as a KeyError from the projection's icon map,
        and drives sort_notices_and_subject -- so a silent demotion would reorder a real report and
        change its subject prefix (campaign I14d, LEDGER I14c whole-branch finding 1)."""
        if not isinstance(self.severity, Severity):
            raise TypeError(
                f"Notice({self.code!r}).severity must be a Severity member; "
                f"got {self.severity!r}"
            )
        bad = [x for x in self.csv_extra if not isinstance(x, str)]
        if bad:
            raise TypeError(
                f"Notice({self.code!r}).csv_extra elements must be str; got {bad!r}"
            )
```

- [ ] **Step 4: Run the test and the whole notice suite**

Run: `cd /workspace && ./run-tests tests/unit/test_notice.py tests/unit/test_add_notice_from_notice.py tests/unit/test_site_context.py -q`
Expected: all PASS (the parametrized fakes pass real `Severity` members — measured above).

- [ ] **Step 5: Write the failing registration test**

Create `tests/integration/test_notice_registration.py`:

```python
"""Every notice code the program can construct is a registered NOTICE_* constant.

CLAUDE.md states the rule as if the type enforced it; nothing did (LEDGER I14c, ledgered to
I14d).  tests/integration/test_notice_roster.py compares the REGISTRY against the roster, so a
producer writing `Notice(code="whatever")` registers nothing, enters no registry, and passes
every test -- while emitting a notices-CSV row no roster knows about.

The property is static: no runtime path can observe an unregistered code, because the string
simply flows through.  So this test reads the source (SPEC §4: the highest seam that reaches
the behavior), not a running program.
"""
import ast
import pathlib

import pytest

from psh.notice import registry

pytestmark = pytest.mark.integration

REPO = pathlib.Path(__file__).resolve().parents[2]
ROOTS = ("psh", "check", "plugin")


def _python_files():
    for root in ROOTS:
        yield from sorted((REPO / root).rglob("*.py"))


def _module_constants(tree):
    """NOTICE_* -> the call that produced it, for module-level assignments only."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id.startswith("NOTICE_"):
            out[node.targets[0].id] = node.value
    return out


def _notice_calls(tree):
    """Every Notice(...) / sc.Notice(...) call node."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if name == "Notice":
                yield node


def test_every_notice_code_is_a_registered_constant():
    """code= MUST be a module-level NOTICE_* name, never a literal or an expression."""
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for call in _notice_calls(tree):
            code = next((kw.value for kw in call.keywords if kw.arg == "code"), None)
            where = f"{path.relative_to(REPO)}:{call.lineno}"
            if code is None:
                offenders.append(f"{where}: Notice(...) with no code= keyword")
            elif not isinstance(code, ast.Name):
                offenders.append(f"{where}: code={ast.unparse(code)} is not a NOTICE_* name")
            elif code.id not in constants:
                offenders.append(f"{where}: code={code.id} is not a module-level constant here")
    assert not offenders, "notice codes not traceable to a registered constant:\n" + \
        "\n".join(offenders)


def test_every_notice_constant_comes_from_register():
    """A NOTICE_* bound to anything but registry.register(...) never enters the registry."""
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, value in _module_constants(tree).items():
            src = ast.unparse(value)
            if not (isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and value.func.attr == "register"):
                offenders.append(f"{path.relative_to(REPO)}: {name} = {src}")
    assert not offenders, "NOTICE_* constants that are not register() results:\n" + \
        "\n".join(offenders)


def test_static_codes_match_the_runtime_roster(psh):
    """The literals registered in source == the codes the loaded program registered.

    Catches a code registered in a module nothing imports (dead registration) and a module
    imported but never scanned.  `psh` (psh.cli) plus the roster test's package loads populate
    the registry; this test only asserts the static set is a SUPERSET check in the direction
    that matters -- every source literal is a real, registrable code.
    """
    literals = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for value in _module_constants(tree).values():
            if isinstance(value, ast.Call) and value.args and isinstance(value.args[0], ast.Constant):
                literals.add(value.args[0].value)
    assert len(literals) == 36, f"expected 36 registered code literals, found {len(literals)}"
    assert registry.codes() <= literals, \
        f"registry holds codes with no source literal: {sorted(registry.codes() - literals)}"
```

- [ ] **Step 6: Demonstrate it red — twice — then revert**

Red demo A (a literal code):
```bash
cd /workspace
python - <<'PY'
import pathlib
p = pathlib.Path("check/pantheon/frozen.py"); s = p.read_text()
p.write_text(s.replace("code=NOTICE_FROZEN,", 'code="frozen-literal",', 1))
PY
./run-tests tests/integration/test_notice_registration.py -q
git checkout check/pantheon/frozen.py
```
Expected: FAIL naming `check/pantheon/frozen.py:<line>: code="frozen-literal" is not a NOTICE_* name`.

Red demo B (a constant that never registers):
```bash
cd /workspace
python - <<'PY'
import pathlib
p = pathlib.Path("check/pantheon/frozen.py"); s = p.read_text()
p.write_text(s.replace('NOTICE_FROZEN = sc.registry.register(\n    "frozen"', 'NOTICE_FROZEN = "frozen"  # (\n    "frozen"', 1))
PY
./run-tests tests/integration/test_notice_registration.py -q
git checkout check/pantheon/frozen.py
```
Expected: FAIL from `test_every_notice_constant_comes_from_register`. If the edit does not
parse, hand-edit the file instead — the requirement is a **recorded red run**, not this exact
sed. **Paste both outputs into the task report**, then confirm `git status` is clean.

- [ ] **Step 7: Run the test green**

Run: `cd /workspace && ./run-tests tests/integration/test_notice_registration.py tests/integration/test_notice_roster.py -q`
Expected: 4 passed (3 new + the roster test).

- [ ] **Step 8: Write the `Severity(level)` ValueError test**

Append to `tests/integration/test_gather_drupal.py` (which owns `psh/gather.py`'s tests), after
a section banner matching the file's style:

```python
# ── check_drupal_module: an unknown level fails AT the producer ──────────────────────
def test_check_drupal_module_rejects_an_unknown_level(reset_sc, monkeypatch):
    """campaign I14c replaced a hand-rolled level->icon map (which silently shipped a warning
    triangle on an alert) with Severity(level).  That conversion is the guard; without it an
    unknown level flows into the notice and only surfaces, if ever, as wrong output."""
    recording_console(monkeypatch, reset_sc)
    with pytest.raises(ValueError, match="bogus"):
        reset_sc.check_drupal_module(
            "its-wws-test1", {}, "pantheon_advanced_page_cache", "Pantheon Advanced Page Cache",
            "https://www.drupal.org/project/pantheon_advanced_page_cache", "Necessary.",
            level="bogus",
        )
```

- [ ] **Step 9: Demonstrate it red, then run it green**

Red demo: temporarily change `severity=Severity(level)` to `severity=Severity.WARNING` at
`psh/gather.py:176`, run the test, capture the `DID NOT RAISE` failure, `git checkout psh/gather.py`.

Run: `cd /workspace && ./run-tests tests/integration/test_gather_drupal.py -q`
Expected: all PASS. Paste the red output into the task report.

- [ ] **Step 10: Fix the stale comments and the banner**

Locate the full set (SPEC §2.5 finding 5 — the ledger says three comments + one banner; two are
known, the rest MUST be found, and the count found MUST be reported):

```bash
cd /workspace
grep -rn "add_notice fills\|add_notice will fill\|filled by add_notice" tests/
grep -rn "multisite-check\|wp-error\|drush-error" tests/ | grep "#\|──"
```

Fix each in place:
- `tests/integration/test_check_pantheon_cdn_change.py:57` — the comment says `add_notice`
  fills the icon; since I14c the projection `notice_to_dict` does. Correct the attribution.
- `tests/integration/test_drupal_notice_render.py:63` — the banner reads `multisite-check`,
  which is the `operation` argument to `sc.drush_error`, not a notice code (the code is
  `drush-error`). This is the exact collision D-i14c-8 renamed the parameter to prevent.
  Rewrite as `drush-error (check/drupal/multisite.py, fatal-probe path — operation "multisite-check")`.

- [ ] **Step 11: Drop `_CACHED`**

In `tests/unit/test_cachecheck_consolidation.py`, delete the `_CACHED` dict and inline the load
(the file has 33 tests; the module is small and pure, so per-test loading is trivial — and
caching a producing module across tests satisfies the registry invariant only literally):

```python
@pytest.fixture
def notices(psh):
    """Load check/cloudflare/notices.py standalone, ONCE PER TEST.

    Never cache this across tests: the module registers its notice code at import, and
    reset_sc snapshots/restores the registry per test -- a session-cached module would hold a
    code the registry no longer has (CLAUDE.md § Notices vs. news; LEDGER I14c → I14d).
    """
    path = pathlib.Path(psh.__file__).resolve().parents[1] / "check" / "cloudflare" / "notices.py"
    loader = SourceFileLoader("cachecheck_notices_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
```

Delete the now-orphaned `_CACHED = {}` and `_load()`. Keep `Path` imported as the file already
imports it (adjust the name used above to whatever that file imports — do not add a second import).

- [ ] **Step 12: Collapse the registration comment blocks**

Measured at spec time: **19** files carry a 4-line block; `psh/cli.py` registers `no-domains`
with none. Replace each block with one line, and give `psh/cli.py` the same line so all 20 read
alike. In `check/`, `plugin/`:

```python
# Notice code registered at import; see CLAUDE.md § Notices vs. news.
```

In `psh/` (which reaches the registry directly, not through the façade):

```python
# Notice code registered at import; see CLAUDE.md § Notices vs. news.
```

Use the plural ("Notice codes") where a module registers more than one. **Do not touch any
`registry.register(...)` call, any `NOTICE_*` name, or any notice body** — comment lines only.

- [ ] **Step 13: Run the full suite and prove byte-identity**

```bash
cd /workspace && ./run-tests
git diff 6d405f7 -- tests/e2e/__snapshots__/   # MUST be empty
git diff 6d405f7 -- '*.ambr'                   # MUST be empty
```
Expected: **1060 passed / 1 skipped**, 107 snapshots, both gates, EXIT=0; both diffs empty.

- [ ] **Step 14: Commit**

```bash
cd /workspace && git add -A && git commit -m "fix(campaign-I14d): the seven findings LEDGER I14c ledgered here

- Notice.__post_init__ validates severity strictly (validate, never coerce --
  the csv_extra posture): a bare string surfaced as an anonymous KeyError from
  the projection, and severity drives sort_notices_and_subject, so a silent
  demotion reorders a report and changes its subject prefix.
- tests/integration/test_notice_registration.py enforces, by AST, what
  CLAUDE.md already claimed: every constructed code is a registered NOTICE_*
  constant.  Shown red twice (a literal code; a non-registering constant).
- Severity(level)'s named ValueError now has a test.
- _CACHED dropped: caching a producing module across tests satisfied the
  registry invariant only literally.
- 20 registration comment blocks collapsed to one line each; the stale
  add_notice-fills comment and the multisite-check banner corrected.

Goldens and all 107 snapshots byte-identical.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: CLAUDE.md — the final-state rewrite

**Files:**
- Modify: `CLAUDE.md` (1,239 lines → ~600–750)

**Interfaces:**
- Consumes: `CLAIMS.md` (Task 1) — every retained claim traces to a `keep-verified` row; every
  `fix` row's correction is applied. Task 2's outcomes are facts here, not futures.
- Produces: the document Task 4 cross-references and Task 6 audits (§17 Q8).

- [ ] **Step 1: Draft the section skeleton**

Write the new outline first, and check it against `CLAIMS.md`'s Keep-list checklist before
writing prose. Sections (this list is exhaustive; order matters — a reader meets the program
before its conventions):

1. **What this is** — one paragraph, unchanged in substance.
2. **Commands** — invocation, flags, the safety rule that `--for-real` is the blast-radius gate.
3. **Required runtime credentials / external tools** — including the PHP 8.4 warning (Keep #20)
   and the "credentials never read from the environment by feature code" rule.
4. **Architecture** — `psh/` core (one short paragraph per module, present tense, no increment
   references), the `sc` façade, the plugin/check module system, the phase list + per-phase
   data contract table (registry is authoritative), the per-site pipeline, notices vs. news,
   the gateway wrappers, email/SMTP config, Cloudflare, resume, rendering, database.
5. **Conventions & gotchas** — Keep list #1, #2, #9, #10, #11, #14, #17.
6. **Testing** — the two gates, the tiers, the seams (Keep #6, #7, #8, #12, #13, #15), the
   still-hardcoded-U-M inventory (Keep #19).
7. **Reusable prompts / Dispatching subagents / Agent skills / Issue tracker / domain docs** —
   substantively unchanged.
8. **How this architecture came to be** — a short pointer to
   `development/2026-07-17-modularization-campaign/` (CAMPAIGN.md frozen, LEDGER.md history,
   CLOSING-AUDIT.md, RETROSPECTIVE.md), stating the campaign is **complete**. This section
   replaces the "Modularization campaign (in progress)" block.
9. **Development archive / Dev container / Pantheon API / Reference material / Other** —
   substantively unchanged.

- [ ] **Step 2: Write the rewrite, obeying the four rules**

From SPEC §2.2: (1) never state a fact by its provenance — "`psh/gather.py` holds the framework
gather cores", never "new in I9, Drupal half added in I10"; (2) every Keep-list warning keeps
its **reason** — the bug it prevents is what makes a reader obey it; (3) every retained claim
traces to a `keep-verified` row; (4) one term per concept, matching `CONTEXT.md`.

Two specific corrections this rewrite MUST land (SPEC §2.5 findings 3 and 4):
- The registration rule stated correctly: **`psh/` modules use `registry` directly** (they
  cannot import the façade), **`check/` and `plugin/` use `sc.registry`**, and
  `check/pantheon_cdn_change/notices.py` is the one sanctioned module importing `psh.notice`
  directly (its purity test pins its imported-module set). The old sentence — "every producing
  module registers … through `NOTICE_* = sc.registry.register(...)`" — is wrong for five modules.
- The rationale for the registration convention lives **here** now, which is what lets Task 2
  collapse 20 comment blocks to one line each.

Also state, as new facts: `tests/integration/test_notice_registration.py` enforces the rule;
`Notice` validates both `severity` and `csv_extra` at construction; and Keep #15's invariant
reads "…nor cached across tests".

- [ ] **Step 3: Gate the result**

```bash
cd /workspace && python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --gate \
    --allow development/2026-07-24-mod-I14d-closing/claims-allow.txt CLAUDE.md
```
Expected: `0 unallowed FAIL/ERROR verdict(s)`, exit 0.

- [ ] **Step 4: Audit against the Keep list**

For each of the 22 Keep-list rows, `grep` the new CLAUDE.md for the warning and record the
section it landed in, as a table in the task report. A row with no location is a **defect**, not
a judgment call — restore it. Also record the new line count and confirm nothing was cut to hit
a range (SPEC §2.2 rule 5: the range yields, never a warning).

- [ ] **Step 5: Confirm zero behavior change**

```bash
cd /workspace && git diff --stat 6d405f7 -- CLAUDE.md && ./run-tests --fast
```
Expected: only `CLAUDE.md` in the diff for this step; suite green at 1060/1.

- [ ] **Step 6: Commit**

```bash
cd /workspace && git add CLAUDE.md && git commit -m "docs(campaign-I14d): rewrite CLAUDE.md as a final-state document

Describes the architecture as it is.  Increment-numbered narrative moves to
LEDGER.md, which is its permanent home; every load-bearing warning keeps the
bug it prevents, because the reason is what makes a reader obey it.

Written from CLAIMS.md, so a warning can only leave the document through an
explicit drop-with-reason row.  claim_check.py --gate CLAUDE.md is green.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: README, docs/, prompts/, tests/README.md, CONTEXT.md, memory

**Files:**
- Modify: `README.md` (lines 275, 281, the TO DO head, + new items)
- Modify: `tests/README.md`, `CONTEXT.md`, `docs/*.md`, `prompts/*.md` — only where `CLAIMS.md`
  says `fix`
- Modify: `~/.claude/projects/-workspace/memory/` — 9 files

**Interfaces:**
- Consumes: `CLAIMS.md`; the rewritten `CLAUDE.md` (cross-references must resolve).
- Produces: the README TO DO list Task 6's audit cites.

- [ ] **Step 1: Fix README's two falsified claims**

`README.md:275` — the bullet describes `ruff-broad.toml` in the present tense as a second
config. I14b merged it into `pyproject.toml` and deleted it; there is now ONE ruff pass.
Rewrite the bullet to describe the merged `[tool.ruff.lint]` (`select = ALL` minus a justified
ignore list, the `tests/**` idiom block, `extend-exclude = ["development/2*"]`), and mark the
campaign item **done**.

`README.md:281` — "scope `psh/` minus `_legacy.py`". `psh/_legacy.py` was deleted at I14a and
pyright now gates all of `psh/`. Correct the scope and drop the `_legacy.py` mention.

- [ ] **Step 2: Retire the campaign banner and add the three new TODOs**

Replace the TO DO head ("Modularization campaign in progress") with a completion line pointing
at `CLOSING-AUDIT.md` and `RETROSPECTIVE.md`. Add three post-campaign items, each with its
reasoning (PD#9 — a vague intention is a lie):

1. **Extract further from `main()`** — it is 622 raw / 445 logic lines against CAMPAIGN.md
   §3.3's 250–400 target. Everything left matches §3.3's exhaustive stay-list, so this is a
   deliberate deviation recorded at close (CLOSING-AUDIT Q1), not an oversight. Candidates:
   the config/arg bootstrap sequence, the per-site skip/banner preamble, the phase-firing and
   contract-stuffing spine.
2. **The `uvx pyright@1.1.411` fallback is useless in practice** — it runs in an isolated
   environment with none of the project's dependencies and reports 34 false
   `reportMissingImports`. Loud, not silent, so not a gate defect; but either give the fallback
   the dependencies or drop it and require the venv binary.
3. **A docs path-guard test was considered and declined** — it catches only deleted paths,
   while every stale claim this campaign shipped was prose about a file that still existed; it
   also needs an allowlist for illustrative paths, which rots. Recorded so it is not
   re-litigated (SPEC D-i14d-7).

- [ ] **Step 3: Apply every remaining `fix` row**

Work `CLAIMS.md` top to bottom for `tests/README.md`, `CONTEXT.md`, `docs/*.md`, `prompts/*.md`.

**Do NOT "fix" these — they were verified correct on 2026-07-24 and a well-meaning edit would
make them wrong:** `docs/pantheon-cdn-change.md:174`, `prompts/directives.md:114` and
`prompts/debugging-standards.md:34` already say `psh.dns_classify`; `docs/awscli-login.md:19`'s
`cli_legacy_plugin_path` is an AWS CLI setting, unrelated to `psh/_legacy.py`.

- [ ] **Step 4: Refresh auto-memory (CAMPAIGN.md §7 obligation 7, PD#13)**

Nine files name a deleted file or a superseded design:

```bash
grep -rln "_legacy\|ruff-broad\|dns_classify" ~/.claude/projects/-workspace/memory/
```
Expected: `MEMORY.md`, `modularization-campaign.md`, `gateway-extraction.md`,
`config-and-notice-modules.md`, `codegraph-blind-to-main-script.md`,
`hook-phase-ordering-invariant.md`, `db-idle-connection-reaped.md`, `dns-modularization.md`,
`pantheon-cdn-change-check.md`.

Update each to final state — `psh/cli.py` not `psh/_legacy.py`, one merged ruff config,
`psh/dns_classify.py`. Rewrite `modularization-campaign.md` to record the campaign as
**complete**, with what it delivered and where the record lives. Update `MEMORY.md`'s one-line
hooks to match. Delete nothing that is still true.

- [ ] **Step 5: Gate everything**

```bash
cd /workspace && python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --gate \
    --allow development/2026-07-24-mod-I14d-closing/claims-allow.txt \
    CLAUDE.md README.md CONTEXT.md tests/README.md docs/*.md prompts/*.md \
    ~/.claude/projects/-workspace/memory/*.md
```
Expected: `0 unallowed FAIL/ERROR verdict(s)`, exit 0.

- [ ] **Step 6: Commit**

```bash
cd /workspace && git add -A && git commit -m "docs(campaign-I14d): refresh README, docs, prompts, CONTEXT and memory

README's ruff-broad.toml and 'psh/ minus _legacy.py' claims were falsified by
I14b and I14a respectively; the campaign banner becomes a completion pointer.
Three post-campaign TODOs added with their reasoning: further main()
extraction, the useless uvx pyright fallback, and the declined docs
path-guard.

Nine auto-memory files de-staled.  Verified NOT stale and deliberately left
alone: the psh.dns_classify references in docs/ and prompts/, and
awscli-login.md's unrelated cli_legacy_plugin_path.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: The configuration record

**Files:**
- Create: `docs/config-migration.md`
- Modify: `sample-pantheon-sitehealth-emails.toml` (comments only, where verification says so)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the answer Task 6 cites for §17 Q7.

- [ ] **Step 1: Verify the sample config key-by-key**

For every key in `sample-pantheon-sitehealth-emails.toml`, find the code that reads it and
record `key → reader (file:line)`. Report any key nothing reads and any key read by code but
absent from the sample. Useful starting point:

```bash
cd /workspace && grep -n "^\[\|^[a-z_]* *=" sample-pantheon-sitehealth-emails.toml
grep -rn "config\[" --include="*.py" psh check plugin script_context.py | head -60
```

Correct sample **comments** that describe superseded behavior. Do NOT add, remove, or rename a
key: that would be a schema change at the exact moment the migration doc says none happened.

- [ ] **Step 2: Write `docs/config-migration.md`**

Structure (SPEC §2.4):

1. **Headline:** no key changes are required. An existing production config keeps working
   unchanged across the whole campaign.
2. **Audit trail — why that is a finding, not a hope:** CAMPAIGN.md §5 required every new key
   to land in final shape as introduced (I3 onward), so there is no interim shape to migrate
   from. List the campaign-introduced keys and the increment each landed in.
3. **The section inventory:** production carries `[Pantheon]`, `[Pantheon.plan_info*]`,
   `[Pantheon.plan_sku_to_name]`, `[Database]`, `[Cloudflare]`, `[Cloudflare.cachecheck]`,
   `[SMTP]`, `[AWS]`, `[UMich]`, `[UMich.portal]`, `[UMich.portal.db]`, `[News]` — verified
   2026-07-24. It has no `[Check.*]` and no `[Email]`, and both default correctly.
4. **What an operator MAY now add** — all optional, all defaulting to today's behavior. Show it
   as a real snippet **merged into surrounding context**, never as a fragment to paste over the
   file (the Spine's spec bar):

```toml
# Optional.  Each check package is enabled by default; set false to turn one off.
# Omitting the section entirely is identical to enabled = true.
[Check.pantheon]
enabled = true          # frozen-site, live-env, upstream-updates, PHP-EOL checks

[Check.wordpress]
enabled = true          # PAPC, native sessions, Object Cache Pro, favicon

[Check.drupal]
enabled = true          # multisite probe, PAPC module, D7 EOL

[Check.addon_updates]
enabled = true          # the pending plugin/theme/module updates table
```

5. **Production-config instruction: no edits required.** State the check that produced it —
   every key the production file carries is still read by the same code path, and every key the
   campaign introduced defaults to the pre-campaign behavior when absent. This is §17 Q7's answer.

- [ ] **Step 3: Prove the claim empirically**

The offline e2e goldens run against `tests/fixtures/config/minimal.toml` and
`minimal-nonumich.toml`, neither of which was edited by the campaign — that they still render
byte-identically IS the evidence that no config shape changed:

```bash
cd /workspace && ./run-tests -m e2e && git diff 6d405f7 -- tests/e2e/__snapshots__/
```
Expected: e2e tier green; diff empty. Paste both into the task report.

- [ ] **Step 4: Commit**

```bash
cd /workspace && git add docs/config-migration.md sample-pantheon-sitehealth-emails.toml && \
git commit -m "docs(campaign-I14d): the configuration migration record

No key changes are required -- a finding, not a hope: CAMPAIGN.md section 5
required every new key to land in final shape as introduced, so there is no
interim shape to migrate from.  The doc carries the section inventory, the
optional sections an operator MAY now add, and the production instruction
(no edits required), which is section 17 Q7's answer.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Ledger resolution, closing audit, retrospective

**Files:**
- Create: `development/2026-07-17-modularization-campaign/CLOSING-AUDIT.md`
- Create: `development/2026-07-17-modularization-campaign/RETROSPECTIVE.md`
- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md` (I14d entry)
- Modify: `development/2026-07-17-modularization-campaign/CAMPAIGN.md` (status line only)

**Interfaces:**
- Consumes: every earlier task's outcome.
- Produces: the campaign's terminal state.

- [ ] **Step 1: Build the ledger-resolution table**

Walk every "Discovered tasks" and "Open questions" item in `LEDGER.md` entries I0…I14c. Give
each exactly one terminal disposition: **done** (with the commit or artifact), **README TODO**
(with the item's text), or **declined** (with the reason). Nothing may resolve to "carried".

```bash
cd /workspace && grep -n "Discovered tasks\|Open questions" \
    development/2026-07-17-modularization-campaign/LEDGER.md
```

- [ ] **Step 2: Write `CLOSING-AUDIT.md`**

One section per CAMPAIGN.md §17 question, each with the command run and its output pasted.
Expected answers (SPEC §2.6) — an unexpected answer is a finding to report, not to smooth over:

| Q | Answer + evidence to paste |
|---|---|
| 1 | **Recorded deviation.** `main()` = 622 raw / 445 logic vs. 250–400. Paste the measurement; then walk §3.3's stay-list and confirm everything left matches it; cite the README TODO |
| 2 | Each of the five DAG fatal conditions shown red — cite the test that demonstrates each |
| 3 | Registry ↔ CLAUDE.md table agreement — cite `tests/unit/test_contract_registry.py`, run it |
| 4 | Two halves: `NoticeRegistry` is load-bearing (`test_notice_roster.py` + the new `test_notice_registration.py`); plus a dead-`sc`-name scan — for each documented façade name, grep `check/` and `plugin/` for a use. **Report, never delete** (Invariant 9) |
| 5 | Symlink KEPT (answered at I14a); state what it buys, per the rewritten CLAUDE.md |
| 6 | The step-1 table |
| 7 | No edits required — cite `docs/config-migration.md` |
| 8 | `claim_check.py --gate` green over every document; paste the run |
| 9 | The amendments: Wave-4 split, B51 early deletion, §6 `csv_extra`, §3.5 exception — each with its ledger entry |

Measurement commands:
```bash
cd /workspace
python - <<'PY'
import ast, pathlib
t = ast.parse(pathlib.Path("psh/cli.py").read_text())
m = next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "main")
raw = m.end_lineno - m.lineno + 1
body = pathlib.Path("psh/cli.py").read_text().splitlines()[m.lineno-1:m.end_lineno]
logic = sum(1 for line in body if line.strip() and not line.strip().startswith("#"))
print(f"main() raw={raw} logic={logic}")
PY
./run-tests tests/unit/test_contract_registry.py tests/integration/test_hook_dag.py -q
```

- [ ] **Step 3: Write `RETROSPECTIVE.md`**

Two halves. **Outcome:** §1's goal against measured reality — the script's before/after line
counts, the `psh/` module map, the check packages created, the test count (727 → 1060), the
ratchet's end state, and the one target missed (`main()` size) with its reason. **Failure
classes worth carrying forward** — each already ledgered, generalized here:

1. Instruments print verdicts they have not checked (three in I14c alone: the `ast.Name`-only
   matcher, the zero-literal file counting as a pass, the `--gate` excluding rather than
   requiring). A green check is a claim until shown able to go red (PD#14).
2. A test's coverage list drifts silently — `ALL_PACKAGES` blinded `test_hook_dag.py` to two
   packages for three increments (I8→I10).
3. A second config file cannot inherit `requires-python`: the broad ruff pass ran at py310 for
   the entire campaign, masking seven findings.
4. The two-binding seam: a module that does `from X import f` binds its own name, so patching
   `X.f` does not intercept it (`run_terminus`, `SMTP_SSL`, `finish_run`).
5. A subagent's report `Write` can fail silently; verify the file exists.
6. "Appears in a test file" is not "asserted by a test" — six notice severities were rewritten
   with nothing asserting them.

- [ ] **Step 4: Append the I14d ledger entry**

Use the CAMPAIGN.md §12 template: Moved / Deviations / Contract-config-sc additions / Discovered
tasks / Open questions. It MUST record:
- The correction that the registration comment block count was **19**, not the 17 LEDGER I14c
  states (measured at spec time; a ratified document does not carry a wrong number silently).
- The seven findings' dispositions and the two red demonstrations.
- The final test count with its arithmetic (1055 + 5 = 1060).
- `literal_equality.py` stays an archive artifact, with the reason and its disclosed blind spot
  (per-file multiset over `html|text|short` combined, so swapped bodies also compare equal).
- **Open questions: none.** This is the campaign's last increment; anything unresolved is a
  README TODO by then, and the entry says which.

- [ ] **Step 5: Mark the campaign complete in CAMPAIGN.md**

Add ONE status line under the existing `**Status:**` line — the document stays frozen, and this
is an amendment, so it is also recorded in the I14d ledger entry:

```markdown
**Completed:** 2026-07-24 at I14d.  Closing audit: `CLOSING-AUDIT.md`.  Retrospective:
`RETROSPECTIVE.md`.  The architecture below is the shipped architecture; `CLAUDE.md` describes
it in present tense, and `LEDGER.md` holds how it was reached.
```

- [ ] **Step 6: Full suite, byte-identity, clean tree**

```bash
cd /workspace
./run-tests                                      # live tier if credentials are present
git diff 6d405f7 -- tests/e2e/__snapshots__/     # MUST be empty
git diff 6d405f7 -- '*.ambr'                     # MUST be empty
python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --self-test
python development/2026-07-24-mod-I14d-closing/tools/claim_check.py --gate \
    --allow development/2026-07-24-mod-I14d-closing/claims-allow.txt \
    CLAUDE.md README.md CONTEXT.md tests/README.md docs/*.md \
    ~/.claude/projects/-workspace/memory/*.md
git status --porcelain
```
Expected: 1060 passed / 1 skipped, 107 snapshots, both gates, EXIT=0; both diffs empty; gate
exit 0; clean tree. **Paste all of it into SPEC.md §8** — an unrun acceptance suite is PD#14
exactly.

- [ ] **Step 7: Commit**

```bash
cd /workspace && git add -A && git commit -m "docs(campaign-I14d): close the modularization campaign

Ledger fully resolved (every I0-I14c discovered task and open question given
a terminal disposition), CAMPAIGN.md section 17's nine closing-audit questions
answered with pasted evidence, and the retrospective written.

Q1 is answered as a recorded deviation: main() is 622 raw / 445 logic lines
against the 250-400 target, everything left matches section 3.3's stay-list,
and further extraction is a post-campaign TODO.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## After the last task

1. `/code-review` over the whole increment (`prompts/adversarial-review.md`), dispatched as
   **`psh-reviewer`** with fresh context: STANDARDS + SPEC axes. Fold every finding; anything
   not folded is ledgered with its reason.
2. `/archive-session` (runs `development/finalize-session.py`) — the transcript MUST be scrubbed
   of secrets before committing, and the raw session JSONL is never committed.
3. Final commit includes the increment's `development/` folder.

## Self-review (run against SPEC.md)

**Spec coverage.** §2.1 → Task 1. §2.2 → Task 3. §2.3 → Task 4. §2.4 → Task 5. §2.5 findings
1–7 → Task 2 steps 1–12. §2.6 → Task 6. §2.7's eleven decisions: D-i14d-1 → Task 4 step 2 +
Task 6 Q1; D-i14d-2 → Task 2; D-i14d-3 → Task 2 steps 5–7; D-i14d-4 → Task 3; D-i14d-5 → the
split backstop below; D-i14d-6 → Task 6 step 4; D-i14d-7 → Task 4 step 2; D-i14d-8 → Task 1
steps 1–5; D-i14d-9 → Task 2 steps 1–4 (precondition measured, stated); D-i14d-10 → Task 6 Q4;
D-i14d-11 → Task 2 step 11. §3 → Global Constraints + every task's diff check. §4 seams → the
four tests attach exactly where §4 names. §5 test plan → Task 2 (5 tests: severity, ×3
registration, ValueError) reaching 1060. §6 task order → the mapping table, with the sanctioned
reorder stated. §8 acceptance → Task 6 step 6.

**Split backstop (D-i14d-5).** If the session runs long: commit nothing partial, ledger the
split, and the remaining tasks become **I14e**. The natural seam is after Task 4 — Tasks 5 and
6 are self-contained and depend on no uncommitted state.

**Placeholder scan.** No TBD/TODO-in-plan, no "add appropriate error handling", no "similar to
Task N". The three prose-writing tasks (3, 4, 5) give section skeletons, exhaustive rule lists,
the exact corrections to land, and a machine gate — the finished prose is written from
`CLAIMS.md`, which is the deliverable of Task 1, not a placeholder.

**Type consistency.** `claim_check.py` names — `check_document`, `self_test`, `Claim`,
verdicts `PASS`/`FAIL`/`PROSE`/`ERROR`, flags `--gate`/`--self-test` — are used identically in
Tasks 1, 3, 4, and 6. Test names in Task 2 step 5 match the Interfaces block. `$BASE` = `6d405f7`
everywhere.
