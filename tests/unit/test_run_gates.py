"""Offline tests for `./run-tests`' own lint/type gates.

The harness's gates had no test at any tier: `run-tests` is an extension-less script, so it is
neither collected by pytest nor even seen by ruff (which discovers by extension), and every
verification of it up to now was a human running it once by hand.  That is the shape PD#14
warns about applied to the instrument itself -- the thing that decides "the suite is green"
was the one thing nothing could prove still worked.

Loaded with the SourceFileLoader idiom the suite already uses for the other extension-less
scripts (tests/unit/test_find_platform_domains_dns.py), fresh per test.  Importing it is safe:
its entry point is __main__-guarded, so nothing runs on import.

What is pinned here is deliberately narrow -- the properties whose violation is SILENT:

  * the type gate invokes THIS venv's pyright and resolves imports against THIS venv
    (a reintroduced `shutil.which("pyright")` or `uvx` fallback is a working gate that
    reports ~34-46 false `reportMissingImports`, i.e. loud but useless -- see
    `pyright_argv`'s docstring), and
  * pyright never runs UNVERIFIED: a version that cannot be established, or does not match
    pyproject's pin, must abort the gate rather than produce a verdict for a bar nobody chose,
    and
  * every flag the wrapper consumes is actually READ by a branch of main(): a listed-but-unread
    flag is swallowed before pytest sees it, so typing it changes nothing and reports nothing
    (`--human` shipped that way).
"""
import importlib.util
import inspect
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# EVERY import for EVERY test in this file belongs in the block above: ruff's E402 is not in the
# tests/** ignore list, so a mid-file import fails the lint gate.

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "run-tests"
PYPROJECT_TEXT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


@pytest.fixture
def rt():
    """`./run-tests`, loaded fresh.  Its main() is __main__-guarded, so import runs no gate."""
    loader = SourceFileLoader("run_tests_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def echoing_argv(text):
    """An `argv` whose `--version` run prints `text` -- the seam `pyright_version_problem` takes.

    The function takes its argv as a parameter precisely so the version comparison is testable
    without a pyright install, a monkeypatch, or a subprocess fake.
    """
    return [sys.executable, "-c", f"print({text!r})"]


def test_pyright_argv_is_anchored_on_the_running_interpreter(rt):
    """Both halves of the anchor, which are separately load-bearing (see the docstring there).

    `-m pyright` decides WHICH pyright runs; `--pythonpath` decides which environment it
    resolves imports against.  Measured: dropping the second one makes
    `.venv/bin/python run-tests` (venv installed but not activated) report 46 false
    `reportMissingImports`, because pyright otherwise takes the environment from PATH.
    """
    assert rt.pyright_argv() == [sys.executable, "-m", "pyright", "--pythonpath", sys.executable]


def test_pyright_argv_never_reaches_for_a_path_or_uvx_binary(rt):
    """The regression guard for the 2026-08-07 change (README TODO, CLOSING-AUDIT.md).

    Both dropped branches -- `uvx pyright@1.1.411` and `shutil.which("pyright")` -- produce a
    gate that RUNS and reports dozens of false `reportMissingImports`, so neither shows up as
    an error, a skip, or a missing gate.  Asserting the shape of the argv is the only thing
    that goes red if one comes back.
    """
    argv = rt.pyright_argv()
    assert argv is not None
    assert "uvx" not in argv
    assert argv[0] == sys.executable, "the gate must run the venv's pyright, not a PATH one"


def test_pyright_argv_is_none_when_pyright_is_not_installed_here(rt, monkeypatch):
    """Absence must be reported to run_gates(), which fails loudly -- never silently skipped."""
    monkeypatch.setattr(rt.importlib.util, "find_spec", lambda name: None)
    assert rt.pyright_argv() is None


def test_pinned_pyright_version_reads_the_test_extra(rt):
    """The pin is DERIVED from pyproject, so this gate cannot drift from what uv installs."""
    pinned = rt.pinned_pyright_version()
    assert pinned is not None
    assert f"pyright=={pinned}" in PYPROJECT_TEXT


def test_pinned_pyright_version_is_none_when_the_extra_carries_no_pin(rt, tmp_path):
    """An unpinned (or misspelled) requirement must read as "no pin", which the caller treats
    as a problem -- not as a pass."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0"\n'
        '[project.optional-dependencies]\ntest = ["pytest", "pyright"]\n',
        encoding="utf-8",
    )
    assert rt.pinned_pyright_version(pyproject) is None


def test_pyright_version_problem_treats_a_missing_pin_as_a_problem(rt, monkeypatch):
    """The parser test above proves a pinless extra reads as None; this proves the CALLER does
    not then wave the gate through.

    Measured: without this test, replacing `pyright_version_problem`'s missing-pin branch with
    `return None` left the whole file green -- a typo in pyproject.toml would have silently
    turned the version verification off while every other test still passed.
    """
    monkeypatch.setattr(rt, "pinned_pyright_version", lambda *a: None)
    problem = rt.pyright_version_problem(echoing_argv("pyright 1.1.411"))
    assert problem is not None
    assert "pin" in problem


def test_pyright_version_problem_passes_the_pinned_version(rt):
    """The happy path: what the real venv reports today."""
    pinned = rt.pinned_pyright_version()
    assert rt.pyright_version_problem(echoing_argv(f"pyright {pinned}")) is None


def test_pyright_version_problem_names_a_mismatch(rt):
    """A stale venv is the one drift route the mandatory-venv-binary change left open."""
    pinned = rt.pinned_pyright_version()
    problem = rt.pyright_version_problem(echoing_argv("pyright 1.1.999"))
    assert problem is not None
    assert "1.1.999" in problem
    assert pinned in problem


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([sys.executable, "-c", "raise SystemExit(2)"], id="nonzero-exit"),
        pytest.param([sys.executable, "-c", "print('something else')"], id="unparseable"),
        pytest.param([sys.executable, "-c", "pass"], id="no-output"),
        pytest.param(["./no-such-binary-anywhere"], id="not-runnable"),
    ],
)
def test_pyright_version_problem_treats_every_unreadable_version_as_a_problem(rt, argv):
    """PD#1: a check that cannot run must not quietly stop checking.  Returning None on any of
    these would let an unverified pyright decide the gate's verdict."""
    assert rt.pyright_version_problem(argv) is not None


def test_run_gates_fails_when_pyright_is_missing(rt, monkeypatch, capsys):
    """A gate that cannot run must FAIL, not skip (PD#1) -- a green never earned is worse than
    a red."""
    monkeypatch.setattr(rt.subprocess, "call", lambda *a, **kw: 0)  # the ruff pass: clean
    monkeypatch.setattr(rt, "pyright_argv", lambda: None)

    assert rt.run_gates() == 1
    assert "type gate cannot run" in capsys.readouterr().err


def test_run_gates_never_runs_an_unverified_pyright(rt, monkeypatch, capsys):
    """The version check gates the RUN, not just the report.

    Asserting the exit code alone would stay green if the check were moved below the
    `subprocess.call([*pargv])` line -- pyright would have already produced a verdict at an
    unknown version, which is precisely what the check exists to prevent.  So this asserts on
    the recorded calls: exactly one (ruff), never a second.
    """
    calls = []

    def record(argv, **kwargs):
        calls.append(argv)
        return 0

    monkeypatch.setattr(rt.subprocess, "call", record)
    monkeypatch.setattr(rt, "pyright_argv", lambda: ["fake-pyright"])
    monkeypatch.setattr(rt, "pyright_version_problem", lambda argv: "pyright 9.9.9 is installed")

    assert rt.run_gates() == 1
    assert len(calls) == 1, f"pyright must not run unverified; calls were {calls}"
    assert calls[0][0] in rt.ruff_argv()
    assert "9.9.9" in capsys.readouterr().err


def test_every_wrapper_flag_is_consumed_by_a_branch(rt):
    """A wrapper flag nothing reads is a SILENT no-op -- typing it changes nothing, with no error.

    `main()` partitions argv into `ours` (WRAPPER_FLAGS) and `passthrough`, so a flag listed in
    WRAPPER_FLAGS but read by no branch is swallowed twice over: it never reaches pytest either,
    which breaks the documented "any other argument is passed straight through" contract.
    `--human` shipped in exactly that state.  Source inspection is the only seam -- consumption
    is a property of main()'s body, and main() ends in a subprocess.call this test must not make.
    """
    body = inspect.getsource(rt.main)  # the SET lives at module level, so it is not in here
    unread = [flag for flag in rt.WRAPPER_FLAGS if f'"{flag}"' not in body]
    assert unread == [], f"wrapper flags swallowed but never read by a branch: {sorted(unread)}"
