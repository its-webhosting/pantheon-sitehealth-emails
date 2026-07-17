"""Offline e2e for the unknown-framework path (campaign I1, SPEC F3).

{ymd}-results.json is written only on --all runs (which the interlock bans), but the
non---all path of finish_run() pprints the same site_results dict to stdout -- that is
the observable this test pins.
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    TERMINUS_FIXTURES_UNKNOWNFW,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e


def test_unknown_framework_site_appears_in_site_results(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "test.db")
    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(MINIMAL_CONFIG)],
        cwd=work,
        fixtures_dir=TERMINUS_FIXTURES_UNKNOWNFW,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    # Pre-fix behavior that must survive: the operator banner.
    assert "unknown framework" in proc.stdout
    # The fix: the site's entry in the pprinted site_results.  RED pre-fix ({} printed;
    # the banner contains "mystery" but never the quoted-key fragment).
    assert "'framework': 'mystery'" in proc.stdout
    assert "'version': 'unknown'" in proc.stdout
