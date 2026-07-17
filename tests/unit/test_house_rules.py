"""House-rule invariants that CLAUDE.md states in prose, pinned mechanically.

These are the two rules whose violation is SILENT and whose check is trivial.  Other
CLAUDE.md rules are judgment, not assertions, and are deliberately left as prose.

READ THIS BEFORE CHANGING AN ASSERTION HERE.  These tests are Instruments
(prompts/directives.md PD#14): they pass the moment they are written, so a green run
proves nothing on its own.  Each one's red state has been OBSERVED -- see the docstrings.
If one goes red, the invariant broke; do not loosen the assertion to make it pass.  The
scopes below are literal on purpose: widening one to "the whole repo" makes these fail on
legitimate code and invites exactly that loosening.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parent.parent.parent

# The invariant governs FEATURE CODE ONLY -- it is the `<{secret env ...}>` substitution
# boundary (PD#6).  tests/ is NOT in scope and MUST NOT be globbed: it legitimately holds
# 19 os.environ touches across six files (conftest.py, the two pyshim shims, the env-plugin
# test, test_shim_composability.py, and the fake terminus) that set up shims and fixtures.
# An implementer who globs the repo gets red immediately and "fixes" it by loosening this
# assertion -- turning the instrument into a lie.
ENVIRON_SCOPE = ("check", "plugin", "dns_classify.py", "script_context.py",
                 "pantheon-sitehealth-emails")

# CLAUDE.md § Required runtime credentials: "Credentials are never read from the environment
# by feature code: everything flows through config `<{env ...}>` / `<{secret env ...}>`
# substitutions.  The only direct os.environ touches are plugin/env/get_env.py (which IS the
# `<{env}` engine) and the AWS_PROFILE/AWS_DEFAULT_REGION boto plumbing in
# plugin/aws/__init__.py -- don't add more."
ENVIRON_ALLOWLIST = {"plugin/env/get_env.py", "plugin/aws/__init__.py"}


def _scoped_sources():
    """Every feature-code source file, resolved relative to the repo root."""
    files = []
    for entry in ENVIRON_SCOPE:
        path = REPO / entry
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.is_file():
            files.append(path)
    return files


def test_only_two_files_read_os_environ_directly():
    """CLAUDE.md's os.environ invariant, pinned.

    RED DEMONSTRATION (PD#14, observed 2026-07-16): adding `os.environ` to a third file in
    scope -- e.g. check/dns/hook.py -- fails this test naming that file.  Verified, then
    reverted.  A green run here is only evidence because that red run happened.
    """
    sources = _scoped_sources()
    # Nil guard: an empty glob would make every assertion below vacuously true -- GREEN,
    # having checked nothing.  That is the e2e-goldens-never-loaded-checks defect in
    # miniature (PD#14), so a moved/renamed directory MUST fail loudly here.
    assert len(sources) > 20, (
        f"scope resolved to {len(sources)} files -- a directory in ENVIRON_SCOPE moved or "
        f"was renamed.  Fix the scope; do not weaken this test."
    )

    offenders = sorted(
        str(p.relative_to(REPO))
        for p in sources
        if "os.environ" in p.read_text()
        and str(p.relative_to(REPO)) not in ENVIRON_ALLOWLIST
    )
    assert offenders == [], (
        f"{offenders} read os.environ directly.  Secrets and config MUST flow through the "
        f"config `<{{env ...}}>` / `<{{secret env ...}}>` substitutions (PD#6, CLAUDE.md "
        f"§ Required runtime credentials).  The only sanctioned touches are "
        f"{sorted(ENVIRON_ALLOWLIST)}."
    )


def test_exactly_one_sitecustomize_exists():
    """CLAUDE.md: two sitecustomize.py means one silently never runs.

    site.py imports exactly ONE module by that name -- whichever directory wins on sys.path.
    A second one is not an error, not a warning: it just never runs, and an e2e test whose
    assertions are `not in`-shaped then passes green against a run that did nothing.

    test_shim_composability.py covers composability (both shims active at once); this covers
    the COUNT directly, which is the thing that silently breaks it.

    RED DEMONSTRATION (PD#14, observed 2026-07-16): adding a second sitecustomize.py under
    tests/ fails this test listing both paths.  Verified, then reverted.
    """
    found = sorted(str(p.relative_to(REPO)) for p in (REPO / "tests").rglob("sitecustomize.py"))
    assert found == ["tests/shims/pyshim/sitecustomize.py"], (
        f"expected exactly one sitecustomize.py, found {found}.  A second one means ONE OF "
        f"THEM SILENTLY NEVER RUNS -- add new shims as modules inside tests/shims/pyshim/, "
        f"never as a second shim directory (CLAUDE.md § Testing)."
    )
