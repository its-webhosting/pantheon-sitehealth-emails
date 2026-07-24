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
