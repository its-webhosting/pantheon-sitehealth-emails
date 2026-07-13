"""The ONLY test that proves main() actually wraps the site loop in try:, catches a database
failure, runs the epilogue, and prints a command to continue.  `git diff -w` is an eyeball check;
this is a test.

A subprocess run cannot be reached by an in-process monkeypatch, so -- exactly as the DNS tests do
with tests/shims/dnsshim -- tests/shims/dbshim goes on PYTHONPATH via run_program(extra_env=...)
and patches sqlalchemy.orm.Session.get to raise OperationalError.  Single site: the safety
interlock bans --all (CLAUDE.md).
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    SHIM_DIR,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e


def test_database_failure_aborts_the_run_and_prints_a_rerun_command(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "test.db")  # minimal.toml names the sqlite file test.db

    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(MINIMAL_CONFIG)],
        cwd=work,
        extra_env={
            "PYTHONPATH": str(SHIM_DIR / "dbshim"),
            "DB_SHIM_FAIL": "1",
        },
    )

    # The retry ran once, gave up, and the run aborted through the named path -- not a traceback.
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert "Database reconnects: 1" in proc.stdout   # db_retry retried, then raised
    assert E2E_SITE in proc.stdout
    # A single-site run gets a re-run command, never --resume-from (which requires --all).
    assert "--resume-from" not in proc.stdout
    assert "Continue this run with" in proc.stdout


def test_a_fatal_bail_out_in_the_loop_still_runs_the_epilogue(tmp_path):
    # sys.exit("Bailing out.") inside the site loop raises SystemExit -- a BaseException that the
    # DatabaseUnavailableError/OperationalError and KeyboardInterrupt handlers do NOT catch.  Until
    # main() grew an `except SystemExit:` handler, one site with an unknown plan threw away the
    # notices and results of every site already processed.  The handler must flush through
    # finish_run() and then RE-RAISE, preserving the original exit code and message.
    #
    # The trigger: a config whose [Pantheon.plan_info] has no entry for the test site's plan, so
    # the "is on an unknown plan" check bails out mid-loop.  (--all is banned in a subprocess, so
    # the flush is observed as the epilogue's console output rather than as *-results.json.)
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "test.db")

    config = tmp_path / "unknown-plan.toml"
    config.write_text(
        MINIMAL_CONFIG.read_text().replace(
            '[Pantheon.plan_info."Performance Small"]',
            '[Pantheon.plan_info."Performance Teeny"]',  # the test site's plan is now unknown
        )
    )

    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(config)],
        cwd=work,
    )

    assert proc.returncode != 0
    assert "Bailing out." in proc.stderr          # the original SystemExit message survives
    assert "Traceback" not in proc.stderr
    assert "is on an unknown plan" in proc.stdout
    assert "Database reconnects:" in proc.stdout  # the epilogue ran: finish_run() flushed
