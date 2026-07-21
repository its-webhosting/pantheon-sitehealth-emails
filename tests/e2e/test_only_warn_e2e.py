"""Offline e2e for D7 (campaign I7): --only-warn computes the plan recommendation before
dumping warnings, so warning-only runs surface its-recommends-plan rows.

At the default seed volume (median 35,960) the cost model lands in the Basic-downgrade
guardrail (no notice -- see test_recommendation_e2e.py), so this seeds 6x: median 215,760,
where Performance Large's cost (best 6,920) beats current Performance Small (cost_same
4,165 is beaten as best 8,005) -> upgrade notice, savings |4165 - 6920| = 2755.00.
Derivation in the I7 PLAN.md (Task 3); verify by hand against minimal.toml before
adjusting any pinned value here.
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e

_SIX_MONTHS = [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)]


def _only_warn(work):
    return run_program(
        [E2E_SITE, "--date", E2E_DATE, "--only-warn", "--smtp-username",
         E2E_SMTP_USERNAME, "--config", str(MINIMAL_CONFIG)],
        cwd=work,
    )


def test_only_warn_includes_plan_recommendation(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    for year, month in _SIX_MONTHS:
        seed_traffic(work / "test.db", year=year, month=month, visits_scale=6)

    proc = _only_warn(work)

    assert proc.returncode == 0, proc.stderr
    row = next(l for l in proc.stdout.splitlines()
               if f"{E2E_SITE},its-recommends-plan," in l)
    # D-i7-5: fixed 5-column row, comma-free savings (2,755.00 would split the field).
    assert row.strip() == (
        f"{E2E_SITE},its-recommends-plan,Performance Small,Performance Large,2755.00"
    )
    # --only-warn still renders and sends nothing.
    assert not (work / "build" / f"{E2E_SITE}.html").exists()
    assert not (work / "build" / f"{E2E_SITE}.eml").exists()


def test_only_warn_without_enough_data_has_no_recommendation(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "test.db")  # one month -> months_until_recommendations > 0

    proc = _only_warn(work)

    assert proc.returncode == 0, proc.stderr
    assert "its-recommends-plan" not in proc.stdout
    assert not (work / "build" / f"{E2E_SITE}.html").exists()
