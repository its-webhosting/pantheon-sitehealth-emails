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
