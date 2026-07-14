"""Shared fixtures and the safety interlock for the pantheon-sitehealth-emails harness.

See development/2026-07-04-test-harness/SPEC.md and tests/README.md for the design.

Key facts this file encodes:
  * The program under test is an extension-less file, so it is loaded via importlib +
    SourceFileLoader, once, cached in a session-scoped fixture (avoids re-registering
    the SQLAlchemy models).
  * matplotlib.pyplot is imported at the top of that module, so MPLBACKEND must be set
    to "Agg" in the environment BEFORE the load — done here at conftest import time.
  * script_context (`sc`) holds process-global mutable state; the reset_sc autouse
    fixture restores it (deep-copied) between tests.
  * run_program() is the ONLY sanctioned way to invoke the program in a subprocess; it
    raises ForbiddenFlagError before exec if --all/-a/--for-real appear (constraints C1/C2).
"""
import copy
import datetime
import importlib.util
import os
import re
import sqlite3
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

# ── Determinism: pin the matplotlib backend before the target module (which imports
# matplotlib.pyplot at its top) is ever loaded. ──────────────────────────────────────
os.environ.setdefault("MPLBACKEND", "Agg")

REPO_ROOT = Path(__file__).resolve().parent.parent
PROGRAM = REPO_ROOT / "pantheon-sitehealth-emails"
TESTS_DIR = REPO_ROOT / "tests"
SHIM_DIR = TESTS_DIR / "shims"          # on PATH: the fake `terminus`
PYSHIM_DIR = SHIM_DIR / "pyshim"        # on PYTHONPATH: the ONE sitecustomize (DNS + DB shims)
FIXTURES = TESTS_DIR / "fixtures"
CONFIG_DIR = FIXTURES / "config"
TERMINUS_FIXTURES = FIXTURES / "terminus"
REAL_TERMINUS = os.environ.get("TERMINUS_SHIM_REAL", "/usr/local/bin/terminus")

# Static assets the program reads relative to its CWD; symlinked into an isolated
# working directory so e2e runs never touch the repo's real build/, news/, database.db.
_CWD_ASSETS = (
    "email_template.html",
    "email_template.txt",
    "header-image.png",
    "inline-styles.php",  # PHP resolves vendor/ via realpath __DIR__, so no vendor symlink needed
    # find_modules() walks os.walk("check") / os.walk("plugin") -- CWD-RELATIVE
    # (pantheon-sitehealth-emails:900).  Without these, an e2e run in the isolated workdir
    # discovers NO check or plugin package at all, so no hook ever registers and the e2e tier
    # silently tests a program with every check disabled -- which is not the program we ship.
    # (Adding them leaves the three pre-existing goldens byte-identical: with the offline
    # configs, check/umich and check/cloudflare self-gate off, and check/dns emits nothing for
    # fixtures whose domain:list carries only the platform domain.)
    "check",
    "plugin",
)

# Flags that must never reach the real program (see SPEC §2, constraints C1/C2).
FORBIDDEN_FLAGS = {"--all", "-a", "--for-real"}


class ForbiddenFlagError(RuntimeError):
    """Raised by run_program() when a test tries to pass --all/-a/--for-real."""


class ForbiddenLiveDataError(RuntimeError):
    """Raised by run_program() when --create-tables/--import-older-metrics could run against a
    non-fixture config (possibly the production DB).  This is a config-PATH allowlist check,
    NOT a backend-type test: the program's production default DB is also sqlite, so an
    'is it sqlite?' test would fail open (SPEC 2026-07-04-test-suite Part C, constraint C2)."""


class FixtureNotFoundError(FileNotFoundError):
    """Raised when a required committed fixture is missing."""


# ── The program-under-test, loaded once ─────────────────────────────────────────────
_main_module = None


def _load_main_module():
    global _main_module
    if _main_module is None:
        loader = SourceFileLoader("psh_main", str(PROGRAM))
        spec = importlib.util.spec_from_loader("psh_main", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _main_module = module
    return _main_module


@pytest.fixture(scope="session")
def psh():
    """The loaded program module. Import has no argv side effects after the seam refactor."""
    return _load_main_module()


# ── Global-state isolation ──────────────────────────────────────────────────────────
_SC_ATTRS = (
    "options",
    "config",
    "news",
    "hooks",
    "substitutions",
    "plugin",
    "check",
    "plugin_context",
)


@pytest.fixture(autouse=True)
def reset_sc(psh):
    """Restore script_context's mutable globals (deep-copied) around every test.

    `sc.hooks` is a dict-of-lists and add_hook/add_news_item (and SiteContext.add_notice)
    mutate the nested lists in place, so a shallow snapshot would leak between tests.
    """
    import script_context as sc

    saved = {name: copy.deepcopy(getattr(sc, name)) for name in _SC_ATTRS}
    # Start each test from a clean slate.  sc.options must expose .verbose (many helpers
    # call sc.debug() -> sc.options.verbose), so use a real parsed default namespace.
    sc.options = psh.parse_args([])
    sc.config = {}
    sc.news = []
    sc.hooks = {phase: [] for phase in sc.PHASES}
    sc.substitutions = []
    sc.plugin = {}
    sc.check = {}
    sc.plugin_context = {}
    try:
        yield sc
    finally:
        for name, value in saved.items():
            setattr(sc, name, value)


# ── In-process DB (temp sqlite) ─────────────────────────────────────────────────────
class TempDB:
    def __init__(self, psh, path):
        self.path = path
        self.engine = psh.db.create_engine(f"sqlite:///{path}")
        psh.Base.metadata.create_all(self.engine)
        self.Session = psh.db.orm.sessionmaker(bind=self.engine)
        self.PantheonTraffic = psh.PantheonTraffic
        self.PantheonOverageProtection = psh.PantheonOverageProtection

    def session(self):
        return self.Session()


@pytest.fixture
def temp_db(psh, tmp_path):
    """A temporary sqlite DB with the program's schema created; no repo DB is touched."""
    db = TempDB(psh, tmp_path / "test.db")
    yield db
    db.engine.dispose()


# ── Isolated working directory for subprocess (e2e) runs ────────────────────────────
def make_workdir(base):
    """Wire a temp CWD with the repo's static assets, an empty news/ dir, and a neutral
    fqdns.json, so a subprocess run of the program writes only under this dir."""
    work = Path(base) / "work"
    work.mkdir()
    for asset in _CWD_ASSETS:
        src = REPO_ROOT / asset
        if not src.exists():
            raise FixtureNotFoundError(f"expected repo asset missing: {src}")
        (work / asset).symlink_to(src)
    (work / "news").mkdir()
    # A neutral fqdns.json.  With the offline configs all Cloudflare-*disabled*, the cloudflare
    # plugin's fqdns setup hook never registers and the program never reads this file -- so it is
    # effectively vestigial today.  Kept as belt-and-suspenders: were a Cloudflare-enabled
    # subprocess config ever added, a fresh empty file makes decide_fqdns_update() return "skip"
    # (exists + fresh + single-site), so the run stays offline instead of hitting the real API.
    (work / "fqdns.json").write_text("{}\n")
    return work


# ── Deterministic offline e2e: the shim-backed full report run ──────────────────────
# Config/site/date chosen so the run is fully offline and reaches the render stage:
#  * its-wws-test1 = a real WordPress test site (its recorded fixtures drive the run)
#  * --date in March avoids the June contract-year-end U-M-only path
#  * seeded traffic gives the aggregation at least one in-window day (else it IndexErrors)
E2E_SITE = "its-wws-test1"
E2E_SITE_ID = "9cf2c790-c7b8-4f2f-a6f1-27385b8f958e"
E2E_DATE = "2026-03-31"
E2E_SMTP_USERNAME = "testuser"  # fixes the dev-mode To: header for a stable golden
MINIMAL_CONFIG = CONFIG_DIR / "minimal.toml"

# A real Drupal test site (drush path), recorded into its own fixture dir so the WordPress
# fixtures above are never disturbed.
E2E_SITE2 = "its-wws-test2"
E2E_SITE2_ID = "acb22aef-4f92-49c0-8559-f95f6257a358"
TERMINUS_FIXTURES_DRUPAL = FIXTURES / "terminus-drupal"

# make_msgid() produces a fresh CID per run; normalize all of them for golden stability.
_CID_RE = re.compile(r"cid:[^\"'\s>]+")


def normalize_report_html(text):
    """Replace the volatile make_msgid CIDs with a stable placeholder (SPEC §5.9)."""
    return _CID_RE.sub("cid:NORMALIZED", text)


def seed_traffic(db_path, *, site_id=E2E_SITE_ID, year=2026, month=3,
                 plan="Performance Small"):
    """Seed a deterministic month of PantheonTraffic rows into a sqlite DB."""
    con = sqlite3.connect(str(db_path))
    try:
        day = datetime.date(year, month, 1)
        while day.month == month:
            visits = 1000 + day.day * 10
            con.execute(
                "INSERT OR REPLACE INTO pantheon_traffic "
                "(site_id, traffic_date, site_plan, visits, pages_served, cache_hits) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (site_id, day.isoformat(), plan, visits, visits * 3, visits * 2),
            )
            day += datetime.timedelta(days=1)
        con.commit()
    finally:
        con.close()


def build_rendered_report(work, *, site=E2E_SITE, site_id=E2E_SITE_ID, fixtures_dir=None,
                          extra_env=None):
    """Run the full offline shim-backed pipeline in `work`; return the CompletedProcess.

    Creates the schema, seeds deterministic traffic, then renders the report.  Raises
    ForbiddenFlagError via run_program if a forbidden flag ever slips in.  `site`/`site_id`/
    `fixtures_dir` select the site to render and which recorded fixtures to replay.
    `extra_env` is forwarded to the render subprocess (the CDN-change golden uses it to put
    tests/shims/pyshim on PYTHONPATH, whose sitecustomize shims DNS in that subprocess).
    """
    # --create-tables exits non-zero by design (sys.exit("Tables created.")); just ensure
    # the schema file appears.
    run_program(
        ["--create-tables", "--config", MINIMAL_CONFIG],
        cwd=work,
        fixtures_dir=fixtures_dir,
    )
    db_path = work / "test.db"
    if not db_path.exists():
        raise FixtureNotFoundError(f"--create-tables did not create {db_path}")
    seed_traffic(db_path, site_id=site_id)
    return run_program(
        [
            site,
            "--date", E2E_DATE,
            "--smtp-username", E2E_SMTP_USERNAME,
            "--config", MINIMAL_CONFIG,
        ],
        cwd=work,
        fixtures_dir=fixtures_dir,
        extra_env=extra_env,
    )


def _rendered_artifacts(work, proc, site):
    build = work / "build"
    return {
        "work": work,
        "proc": proc,
        "build": build,
        "html": build / f"{site}.html",
        "txt": build / f"{site}.txt",
        "eml": build / f"{site}.eml",
        "inline2": build / f"{site}-inline2.html",
    }


@pytest.fixture(scope="session")
def rendered_report(tmp_path_factory):
    """Session-scoped: run the offline pipeline once for the whole suite; expose artifacts."""
    work = make_workdir(tmp_path_factory.mktemp("rendered"))
    proc = build_rendered_report(work)
    return _rendered_artifacts(work, proc, E2E_SITE)


@pytest.fixture(scope="session")
def rendered_report_drupal(tmp_path_factory):
    """Session-scoped: the Drupal (drush path) offline render for its-wws-test2."""
    work = make_workdir(tmp_path_factory.mktemp("rendered-drupal"))
    proc = build_rendered_report(
        work, site=E2E_SITE2, site_id=E2E_SITE2_ID, fixtures_dir=TERMINUS_FIXTURES_DRUPAL
    )
    return _rendered_artifacts(work, proc, E2E_SITE2)


# ── The one sanctioned way to run the program ───────────────────────────────────────
# The dangerous long options whose argparse abbreviations must also be blocked.
_FORBIDDEN_LONG = ("--all", "--for-real")

# Flags that create/modify the traffic database.  They must only ever run offline against a
# throwaway fixture DB — never the production config/DB (constraint C2).
OFFLINE_ONLY_DATA_FLAGS = ("--create-tables", "--import-older-metrics")
# A --config is treated as a safe test fixture only if it resolves under one of these roots
# (plus the run's own cwd).  Path allowlist, never a backend-type test.
_CONFIG_ALLOWLIST_ROOTS = (CONFIG_DIR,)


def _forbidden_msg(token):
    return (
        f"refusing to run the program with {token!r}: it maps to a forbidden option "
        "(constraints C1/C2: never --all/-a/--for-real, incl. abbreviations and short bundles)"
    )


def _assert_flags_allowed(args):
    """Fail closed if any arg could activate --all/-a/--for-real.

    Exact-token matching is not enough: the program's argparse accepts abbreviations
    (--fo -> --for-real, --al -> --all) and short-flag bundles (-av -> -a -v). This checks
    all three forms. It is deliberately conservative (fail-closed) on ambiguous short bundles.
    """
    for arg in args:
        if arg == "--":
            break  # everything after "--" is positional, never an option
        token = arg.split("=", 1)[0]
        if token in FORBIDDEN_FLAGS:
            raise ForbiddenFlagError(_forbidden_msg(token))
        # A long-option that is a prefix of a forbidden long flag (argparse abbreviation).
        if token.startswith("--") and len(token) > 2 and any(
            forbidden.startswith(token) for forbidden in _FORBIDDEN_LONG
        ):
            raise ForbiddenFlagError(_forbidden_msg(token))
        # A bundled short flag that includes -a, e.g. "-av" == "-a -v".
        if len(token) > 1 and token[0] == "-" and token[1] != "-" and "a" in token[1:]:
            raise ForbiddenFlagError(_forbidden_msg(token))


def _resolve_config_arg(args, cwd):
    """Return the realpath of the effective --config/-c value, or None if not supplied.

    Must mirror argparse's option parsing exactly, including stopping at ``--`` (everything
    after it is positional): otherwise the guard could validate a config the program ignores
    and fall open (a post-``--`` --config satisfying the allowlist while argparse uses the
    default production config)."""
    value = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            break  # everything after "--" is positional, not an option — argparse ignores it
        if arg in ("--config", "-c"):
            value = args[i + 1] if i + 1 < len(args) else None
            i += 2
            continue
        if arg.startswith("--config="):
            value = arg.split("=", 1)[1]
        elif arg.startswith("-c="):
            value = arg.split("=", 1)[1]
        i += 1
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = Path(cwd) / path
    return os.path.realpath(path)


def _assert_offline_data_flags(args, mode, cwd):
    """Fail closed if --create-tables/--import-older-metrics could touch the production DB.

    Refused whenever the run is live, or the effective --config does not resolve under the
    fixture allowlist (or the run's cwd).  Deliberately a config-PATH check, not a
    backend-type test — the production default DB is also sqlite (constraint C2).
    """
    dangerous = None
    for arg in args:
        if arg == "--":
            break
        token = arg.split("=", 1)[0]
        for flag in OFFLINE_ONLY_DATA_FLAGS:
            if token == flag or (
                token.startswith("--") and len(token) > 2 and flag.startswith(token)
            ):
                dangerous = token
                break
        if dangerous:
            break
    if not dangerous:
        return
    if mode == "live":
        raise ForbiddenLiveDataError(
            f"refusing to run {dangerous!r} in live mode: it may create/modify the "
            "production database (constraint C2)."
        )
    config_path = _resolve_config_arg(args, cwd)
    allowed_roots = [os.path.realpath(root) for root in _CONFIG_ALLOWLIST_ROOTS]
    allowed_roots.append(os.path.realpath(cwd))
    if config_path is None or not any(
        config_path == root or config_path.startswith(root + os.sep)
        for root in allowed_roots
    ):
        raise ForbiddenLiveDataError(
            f"refusing to run {dangerous!r} with config {config_path!r}: not under a test "
            "fixture allowlist (a config-path check, not a backend-type test; the production "
            "default DB is also sqlite) (constraint C2)."
        )


def run_program(args, *, cwd, mode="replay", extra_env=None, timeout=300, fixtures_dir=None):
    """Run ./pantheon-sitehealth-emails as a subprocess through the terminus shim.

    Raises ForbiddenFlagError (before exec) if args contain --all/-a/--for-real, or
    ForbiddenLiveDataError if --create-tables/--import-older-metrics could hit the
    production DB (live mode or a non-fixture config).  `fixtures_dir` selects the shim's
    record/replay directory (defaults to the WordPress fixtures).
    Returns a subprocess.CompletedProcess.
    """
    args = [str(a) for a in args]
    _assert_flags_allowed(args)
    _assert_offline_data_flags(args, mode, cwd)

    env = dict(os.environ)
    env["PATH"] = f"{SHIM_DIR}{os.pathsep}{env.get('PATH', '')}"
    env["TERMINUS_SHIM_DIR"] = str(
        fixtures_dir if fixtures_dir is not None else TERMINUS_FIXTURES
    )
    env["TERMINUS_SHIM_MODE"] = mode
    env["TERMINUS_SHIM_REAL"] = REAL_TERMINUS
    env["MPLBACKEND"] = "Agg"
    if extra_env:
        # PYTHONPATH is PREPENDED, not replaced: a plain dict.update would silently drop an
        # inherited PYTHONPATH and the imports it provided would vanish with no error.  PATH above
        # is prepended for the same reason.  Note this is NOT how you add a shim: there is exactly
        # ONE shim dir (PYSHIM_DIR) because site.py imports exactly one `sitecustomize` module --
        # a second shim dir with a second sitecustomize.py would be silently ignored.  Add a new
        # shim as a module inside pyshim/, imported by its sitecustomize and gated on its own env
        # var (see tests/shims/pyshim/sitecustomize.py).
        extra_pythonpath = extra_env.get("PYTHONPATH")
        env.update(extra_env)
        if extra_pythonpath and os.environ.get("PYTHONPATH"):
            env["PYTHONPATH"] = f"{extra_pythonpath}{os.pathsep}{os.environ['PYTHONPATH']}"

    return subprocess.run(
        [str(PROGRAM), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture
def program_runner():
    """Expose run_program to tests as a fixture (keeps the interlock the single entry point)."""
    return run_program


@pytest.fixture
def forbidden_flag_error():
    """The exception class run_program raises — exposed as a fixture so tests match the
    exact class object pytest loaded (avoids the conftest double-import identity trap)."""
    return ForbiddenFlagError


@pytest.fixture
def forbidden_live_data_error():
    """The exception run_program raises for live/non-fixture --create-tables/--import-older-
    metrics (exposed as a fixture for the same identity reason as forbidden_flag_error)."""
    return ForbiddenLiveDataError


@pytest.fixture
def normalize_html():
    """The golden HTML normalizer (SPEC §5.9)."""
    return normalize_report_html


# ── --llm reporting: terse, machine-parseable summary ──────────────────────────────
def pytest_addoption(parser):
    parser.addoption(
        "--llm",
        action="store_true",
        default=False,
        help="emit a terse, machine-parseable summary line for LLM consumption",
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not config.getoption("--llm"):
        return
    stats = terminalreporter.stats

    def count(key):
        return len(stats.get(key, []))

    terminalreporter.write_line(
        "LLM_SUMMARY "
        f"passed={count('passed')} failed={count('failed')} error={count('error')} "
        f"skipped={count('skipped')} xfailed={count('xfailed')} xpassed={count('xpassed')}"
    )
    for rep in stats.get("failed", []) + stats.get("error", []):
        terminalreporter.write_line(f"FAILED {rep.nodeid}")
