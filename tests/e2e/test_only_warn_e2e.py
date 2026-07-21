"""Offline e2e for D7 (campaign I7): --only-warn computes the plan recommendation before
dumping warnings, so warning-only runs surface its-recommends-plan rows.

At the default seed volume (median 35,960) the cost model lands in the Basic-downgrade
guardrail (no notice -- see test_recommendation_e2e.py), so this seeds 6x: median 215,760,
where Performance Large is the recommended upgrade over Performance Small.

The savings pin is 4995.00.  Since the campaign I7 final-review fix the traffic-table build
runs before the recommendation on EVERY path (it persists+commits this window's overage-
protection rows, which recommend_plan then reads back), so --only-warn computes the same
OP-aware recommendation the full report does -- verified consistent ($4,995.00 in the
rendered report) and deterministic (identical across re-runs in the same workdir).  A
missing OP-write-before-read once made --only-warn use the simulation branch (savings
2755.00), diverging from the full report; do not revert the pin to that value.
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
    # D-i7-5: fixed 5-column row, comma-free savings (4,995.00 would split the field).
    assert row.strip() == (
        f"{E2E_SITE},its-recommends-plan,Performance Small,Performance Large,4995.00"
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
