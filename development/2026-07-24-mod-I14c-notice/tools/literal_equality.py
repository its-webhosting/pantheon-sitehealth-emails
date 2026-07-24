#!/usr/bin/env python
"""I14c instrument I2a: prove that converting a notice dict to a Notice(...) call left every
notice literal BYTE-IDENTICAL (CAMPAIGN.md section 9, Invariant 8).

    python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py <baseline-rev> [path ...]
    python development/2026-07-24-mod-I14c-notice/tools/literal_equality.py --self-test <baseline-rev> <path>

For each file it collects the notice-body literal NODES on both sides -- baseline: the
"message"/"text"/"short" values of every dict literal carrying a "csv" key; working tree: the
same, plus the html=/text=/short= keyword arguments of every Notice(...) call -- and compares
the two multisets of `ast.dump(node)`.

Why ast.dump of the node, and not `git diff -w` or an eyeball: an f-string's Constant segments
carry the literal's interior whitespace exactly, including the column-0 continuation lines this
repo's notice bodies deliberately use.  `git diff -w` is designed to hide precisely the change
that would break them (CLAUDE.md, "git diff -w is not proof"), and a re-indent that shifts a
notice body adds leading whitespace to a rendered email.  Comparing the parsed nodes catches it
mechanically.  Field RENAMES are invisible to this check by design (message -> html is a key
change, not a literal change), which is exactly what makes it a conversion instrument.

--self-test re-indents one baseline literal IN MEMORY (never on disk) and asserts the check
reports it: PD#14 -- "a green check is a claim, not evidence, until it has been shown capable
of going red on the condition it guards".
"""
import argparse
import ast
import collections
import subprocess
import sys

BODY_KEYS = ("message", "text", "short")
BODY_KWARGS = ("html", "text", "short")


def literal_nodes(source: str) -> list[ast.expr]:
    """Every notice-body literal node in `source`, dict form and Notice form alike."""
    nodes: list[ast.expr] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            pairs = {k.value: v for k, v in zip(node.keys, node.values, strict=False)
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if "csv" in pairs:
                nodes.extend(pairs[key] for key in BODY_KEYS if key in pairs)
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Notice":
            nodes.extend(kw.value for kw in node.keywords if kw.arg in BODY_KWARGS)
    return nodes


def dumps(source: str) -> collections.Counter:
    return collections.Counter(ast.dump(n) for n in literal_nodes(source))


def baseline_source(rev: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:{path}"],  # noqa: S603, S607
                          capture_output=True, check=True, text=True).stdout


def compare(rev: str, paths: list[str]) -> int:
    failures = 0
    for path in paths:
        before, after = dumps(baseline_source(rev, path)), dumps(open(path).read())  # noqa: PTH123, SIM115
        only_before, only_after = before - after, after - before
        if only_before or only_after:
            failures += 1
            print(f"CHANGED  {path}")
            for dump in only_before:
                print(f"    only in {rev}: {dump[:160]}...")
            for dump in only_after:
                print(f"    only in working tree: {dump[:160]}...")
        else:
            print(f"identical  {path}  ({sum(before.values())} notice literals)")
    print(f"\n{len(paths) - failures}/{len(paths)} files with byte-identical notice literals")
    return 1 if failures else 0


def self_test(rev: str, path: str) -> int:
    """Show the comparison going RED on a one-space re-indent of a real literal."""
    source = baseline_source(rev, path)
    before = dumps(source)
    # CONTROL: unparse/reparse WITHOUT mutating must compare equal, or a red result below
    # would prove nothing about re-indentation (it would just be unparse noise).
    control = collections.Counter(ast.dump(n) for n in literal_nodes(ast.unparse(ast.parse(source))))
    if control != before:
        print(f"SELF-TEST INCONCLUSIVE: unparse/reparse alone changes {path}'s literals; "
              "the red result below would not be attributable to the re-indent")
        return 1
    tree = ast.parse(source)
    mutated = None
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and "\n" in str(part.value):
                    part.value = str(part.value).replace("\n", "\n ", 1)
                    mutated = node
                    break
        if mutated:
            break
    if mutated is None:
        print(f"self-test: {path} has no multi-line notice literal to mutate")
        return 1
    after = collections.Counter(ast.dump(n) for n in literal_nodes(ast.unparse(tree)))
    if before == after:
        print(f"SELF-TEST FAILED: a re-indented literal in {path} compared EQUAL -- "
              "this instrument cannot detect the thing it exists to detect")
        return 1
    print(f"SELF-TEST PASSED: re-indenting one literal in {path} makes the comparison report "
          f"{len((before - after) + (after - before))} changed literal(s) -- the check can go red")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="prove the check can go red")
    parser.add_argument("rev", help="baseline git revision (e.g. the increment's start commit)")
    parser.add_argument("paths", nargs="+", help="files to compare")
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.rev, args.paths[0])
    return compare(args.rev, args.paths)


if __name__ == "__main__":
    sys.exit(main())
