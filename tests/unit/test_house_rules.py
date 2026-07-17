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
# "psh" is the program BODY (psh/_legacy.py + the modules the campaign carves out of it);
# "pantheon-sitehealth-emails" is the thin shim.  Both are feature code -- the body moved into
# psh/ at campaign I0, so the scope must name psh/ or this guard would be blind to the largest
# feature-code files in the repo (added I2).
ENVIRON_SCOPE = ("check", "plugin", "dns_classify.py", "script_context.py",
                 "pantheon-sitehealth-emails", "psh")

# CLAUDE.md § Required runtime credentials: "Credentials are never read from the environment
# by feature code: everything flows through config `<{env ...}>` / `<{secret env ...}>`
# substitutions.  The only direct os.environ touches are plugin/env/get_env.py (which IS the
# `<{env}` engine) and the AWS_PROFILE/AWS_DEFAULT_REGION boto plumbing in
# plugin/aws/__init__.py -- don't add more."
ENVIRON_ALLOWLIST = {"plugin/env/get_env.py", "plugin/aws/__init__.py"}


def _scoped_sources(scope):
    """Every feature-code source file under `scope`, resolved relative to the repo root."""
    files = []
    for entry in scope:
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

    RED DEMONSTRATION (PD#14, observed 2026-07-17, for the `psh` scope added at campaign I2):
    adding `_x = os.environ` to psh/_legacy.py fails this test naming `psh/_legacy.py` -- the
    program body, which was outside this scope until I2 and would otherwise have been an
    unguarded silent hole (PD#6).  Verified, then reverted.
    """
    sources = _scoped_sources(ENVIRON_SCOPE)
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


# CLAUDE.md § Implementation Standards / "The fresh-context trap": "Never shell out to
# terminus/wp/drush directly."  run_terminus is the ONLY terminus spawner and
# subprocess.Popen is HOW it spawns; after the I2 gateway extraction run_terminus lives in
# psh/gateway.py, so that is the one file allowed to name subprocess.Popen.  The match keys on
# `subprocess.Popen`, NOT bare `subprocess`, because the PHP CSS inliner in psh/_legacy.py
# spawns with subprocess.run (not Popen) and is correctly NOT a terminus/wp/drush call.
POPEN_SCOPE = ("check", "plugin", "dns_classify.py", "script_context.py", "psh")
POPEN_ALLOWLIST = {"psh/gateway.py"}


def test_only_the_gateway_spawns_a_subprocess():
    """CLAUDE.md's "never shell out to terminus/wp/drush directly" invariant, pinned.

    subprocess.Popen is the gateway's single spawn point (run_terminus); consolidating every
    Terminus/WP/Drush subprocess behind psh/gateway.run_terminus is the whole point of the I2
    extraction (SPEC §New tests #2).  A second Popen anywhere in feature code means a raw shell-
    out that bypasses the wrapper -- silent, since nothing else flags it.

    RED DEMONSTRATION (PD#14): the code is already in its green post-move state, so red was
    demonstrated by TEMPORARY REINTRODUCTION -- adding a throwaway `subprocess.Popen(` line to
    script_context.py made this test fail naming script_context.py.  Verified, then reverted.
    A green run here is only evidence because that red run happened.
    """
    sources = _scoped_sources(POPEN_SCOPE)
    # Nil guard (same shape as the os.environ test): an empty glob passes vacuously -- the
    # e2e-goldens-never-loaded-checks defect in miniature (PD#14).  A moved/renamed directory
    # in POPEN_SCOPE MUST fail loudly here, not slip through green having checked nothing.
    assert len(sources) > 20, (
        f"scope resolved to {len(sources)} files -- a directory in POPEN_SCOPE moved or was "
        f"renamed.  Fix the scope; do not weaken this test."
    )

    offenders = sorted(
        str(p.relative_to(REPO))
        for p in sources
        if "subprocess.Popen(" in p.read_text()
        and str(p.relative_to(REPO)) not in POPEN_ALLOWLIST
    )
    assert offenders == [], (
        f"{offenders} spawn a subprocess with subprocess.Popen.  Terminus/WP/Drush commands "
        f"MUST route through the run_terminus wrapper in psh/gateway.py -- never shell out "
        f"directly (CLAUDE.md § Implementation Standards).  The only sanctioned Popen is "
        f"{sorted(POPEN_ALLOWLIST)}."
    )


# CLAUDE.md § Plugin / check module system: "the helpers they need are exposed as sc
# attributes near the cloudflare_enabled() def (sc.escape_url, sc.check_wordpress_plugin,
# sc.check_drupal_module, sc.umich_enabled, sc.cloudflare_enabled, sc.terminus, sc.fqdn_re) --
# extend that block for new ones (tests monkeypatch these when loading check modules
# standalone)."  sc.db_engine_args is exposed in the same block (CLAUDE.md § Database).
SC_FACADE_NAMES = ("escape_url", "check_wordpress_plugin", "check_drupal_module",
                   "umich_enabled", "cloudflare_enabled", "terminus", "fqdn_re",
                   "db_engine_args", "Notice", "Severity")


def test_documented_sc_facade_names_exist(reset_sc):
    """CAMPAIGN.md Invariant 9 / §3.5: sc names are never removed mid-campaign.

    check/ and plugin/ packages import nothing from the dash-named program; the helpers they
    need reach them only as sc attributes.  Dropping one silently breaks every standalone
    check-module test that monkeypatches it (reset_sc escape_url leak, MEMORY.md) and the check
    modules themselves in production -- so this pins the documented facade surface (SPEC §New
    tests #3).  reset_sc yields the loaded script_context, so the sc-exposure block in
    psh/_legacy.py has already run.

    RED DEMONSTRATION (PD#14): this is a PINNING test (green when written, like the two rules
    above).  Red was demonstrated by temporarily commenting out `sc.db_engine_args =
    db_engine_args` in psh/_legacy.py, which made this test fail naming db_engine_args.
    Verified, then reverted.

    (campaign-I3) A second RED demonstration for "Notice"/"Severity": temporarily removed
    `Severity` from the `from psh.notice import Notice, Severity` line in script_context.py
    (Notice/Severity reach sc via that module-level import, not a `sc.Notice = ...`
    assignment); the test failed with `AssertionError: sc is missing documented facade names
    ['Severity']`.  Verified, then reverted.
    """
    sc = reset_sc
    missing = [name for name in SC_FACADE_NAMES if not hasattr(sc, name)]
    assert missing == [], (
        f"sc is missing documented facade names {missing}.  check/ and plugin/ packages reach "
        f"these helpers only through sc; removing one silently breaks them and their standalone "
        f"tests.  sc names are never removed mid-campaign (CAMPAIGN.md Invariant 9 / §3.5)."
    )
