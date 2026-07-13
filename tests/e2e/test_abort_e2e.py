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
