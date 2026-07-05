"""Offline e2e: a site with zero traffic history renders without crashing (P10).

Recording Drupal fixtures against a fresh site once crashed here with
`IndexError: list index out of range` (empty plan_on_day -> days[0]).  The fix seeds a single
synthetic plan-day at the report date so the report still renders (in its "not enough data
yet" state, and delivering any alerts) rather than crashing or dropping the whole email.

This test runs the WordPress fixtures but, unlike build_rendered_report, does NOT seed any
traffic, so plan_on_day starts empty.
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    make_workdir,
    run_program,
)

pytestmark = pytest.mark.e2e


def test_zero_traffic_site_does_not_crash(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    # Intentionally NO seed_traffic(): the DB has zero pantheon_traffic rows.

    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(MINIMAL_CONFIG)],
        cwd=work,
    )

    assert proc.returncode == 0, proc.stderr
    assert "IndexError" not in proc.stderr
    assert "Traceback" not in proc.stderr
    assert "No traffic recorded yet" in proc.stdout
    # The report is rendered (not dropped) in the "not enough data yet" state, so any alerts
    # still reach the owner instead of being silently discarded (P10 review fix).
    html = (work / "build" / f"{E2E_SITE}.html")
    assert html.exists()
    assert "months more data" in html.read_text()
