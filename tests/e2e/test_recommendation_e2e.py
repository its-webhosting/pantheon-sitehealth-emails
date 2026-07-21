"""Offline e2e for the two plan-recommendation states (test-suite SPEC §7.5).

The shared rendered_report fixture has only one in-window month (June/July metrics fall after
the March report date), so it renders the "not enough data yet" state.  That already
characterizes the <=4-month/new-site path (no NameError — PROBLEMS-DISCOVERED.md P1 is not a
bug).  This module adds:

  * an explicit assertion on that <=4-month state, and
  * a >4-month run (seed six in-window months) that actually exercises the extracted plan_costs
    cost model end to end — a path no other e2e reaches.
"""
import re

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

# Six consecutive in-window months ending at the March 2026 report date -> len(v) == 6 > 4.
_SIX_MONTHS = [(2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 3)]


def _render(work):
    return run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(MINIMAL_CONFIG)],
        cwd=work,
    )


def _cost_figures(html):
    return re.findall(r"\$[\d,]+\.\d{2}", html)


def test_new_site_shows_not_enough_data(rendered_report):
    # The shared fixture (one in-window month) renders the new-site state without crashing.
    assert rendered_report["proc"].returncode == 0
    html = rendered_report["html"].read_text()
    assert "months more data" in html
    assert "Cost estimates will be available once the site has five months" in html


def test_recommendation_path_exercises_plan_costs(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    for year, month in _SIX_MONTHS:
        seed_traffic(work / "test.db", year=year, month=month)

    proc = _render(work)

    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    build = work / "build"
    html = (build / f"{E2E_SITE}.html").read_text()
    txt = (build / f"{E2E_SITE}.txt").read_text()
    # We are past the 5-month threshold: the recommendation table, not the "needs data" state.
    assert "months more data" not in html
    # plan_costs produced a cost table -> the Recommended/Current plan pills are rendered.
    assert "Recommended Plan" in html
    assert "Current Plan" in html
    # Assert plan_costs OUTPUT, not just that the state rendered: the median it computes from the
    # six deterministic seeded months, and the resulting recommended plan.  (35,960 is the median
    # of the seeded monthly visit sums; the guardrails hold the recommendation at the current
    # "Performance Small" floor rather than dropping to Basic.)
    assert "35,960 per month" in html  # median_visitors returned by plan_costs
    rec_line = next(l for l in txt.splitlines() if l.strip().startswith("Recommended plan:"))
    assert "Performance Small" in rec_line


def test_recommendation_is_deterministic_across_reruns(tmp_path):
    """Regression guard (campaign I7 final review): build_traffic_table_rows persists+commits
    the pantheon_overage_protection rows, and recommend_plan reads them back, so the write
    MUST run before the read on every path.  When it didn't, the first render of a report --
    with no prior OP rows in the DB -- computed a different Performance Small "Same Traffic
    Cost" cell ($2,005.00: two overage blocks charged instead of waived) than every later
    render of the identical command ($1,925.00, once run 1's write had landed), so the same
    monthly run produced different owner emails run-to-run.  PD#14: this instrument fails RED
    on exactly that nondeterminism (first-run $2,005.00 != second-run $1,925.00)."""
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    for year, month in _SIX_MONTHS:
        seed_traffic(work / "test.db", year=year, month=month)

    proc1 = _render(work)
    html1 = (work / "build" / f"{E2E_SITE}.html").read_text()
    proc2 = _render(work)
    html2 = (work / "build" / f"{E2E_SITE}.html").read_text()

    assert proc1.returncode == 0, proc1.stderr
    assert proc2.returncode == 0, proc2.stderr
    # The OP-affected Performance Small "Same Traffic Cost" cell: present and identical on both
    # runs.  $2,005.00 was the broken first-run value (blocks charged, not waived).
    assert "$1,925.00" in html1
    assert "$1,925.00" in html2
    assert "$2,005.00" not in html1
    assert "$2,005.00" not in html2
    # The whole cost table is run-independent.
    assert _cost_figures(html1) == _cost_figures(html2)
