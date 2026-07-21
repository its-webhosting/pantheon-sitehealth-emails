"""Integration tier: the psh.traffic flow functions extracted from main()'s per-site loop
at campaign I6 (SPEC D-i6-1) -- update_site_traffic (B22+B23), import_older_site_metrics
(B24), load_site_traffic (B26).

Seams: psh.gateway.run_terminus (the gateway fixture -- CLAUDE.md section "Two mock
seams") and a temp sqlite DB (temp_db).  Loop control stays in main(): these functions
signal via return value; they never continue/raise for the skip paths.
"""
import datetime
import json

import pytest

import script_context as sc
from helpers.dnsfake import recording_console
from psh.traffic import (
    import_older_site_metrics,
    load_site_traffic,
    update_site_traffic,
)

pytestmark = pytest.mark.integration

SITE = {"id": "test-site-id", "name": "its-wws-test1", "plan_name": "Basic"}
START = datetime.date(2025, 8, 1)
END = datetime.date(2026, 3, 31)


def _metrics_json(*entries):
    """A terminus env:metrics payload; entries are ("%Y-%m-%dT%H:%M:%S", visits) pairs."""
    return json.dumps(
        {
            "timeseries": {
                dt: {"datetime": dt, "visits": visits, "pages_served": 0, "cache_hits": 0}
                for dt, visits in entries
            }
        }
    )


def _period_of(command):
    return next(a for a in command if a.startswith("--period="))


def test_update_site_traffic_false_and_no_rows_on_fatal_metrics(
    psh, gateway, temp_db, monkeypatch
):
    monkeypatch.setattr(
        gateway, "run_terminus", lambda *a, **k: ("", "boom [warning]", True)
    )
    console = recording_console(monkeypatch, sc)
    session = temp_db.session()
    ok = update_site_traffic(session, SITE, "test-site-id.live", START, END)
    assert ok is False
    assert session.query(temp_db.PantheonTraffic).count() == 0
    out = console.export_text()
    assert "could not fetch metrics for its-wws-test1" in out
    # Invariant 6: the untrusted stderr is escape()d, so rich must not eat "[warning]".
    assert "boom [warning]" in out


def test_update_site_traffic_merges_rows_and_skips_the_end_date(
    psh, gateway, temp_db, monkeypatch
):
    payload = _metrics_json(("2026-03-01T00:00:00", 10), ("2026-03-31T00:00:00", 99))
    monkeypatch.setattr(gateway, "run_terminus", lambda *a, **k: (payload, "", False))
    session = temp_db.session()
    ok = update_site_traffic(session, SITE, "test-site-id.live", START, END)
    assert ok is True
    rows = session.query(temp_db.PantheonTraffic).all()
    # The end_date entry is today's partial data and must be skipped (update_traffic_rows'
    # existing rule, exercised through the new wrapper).
    assert [(r.traffic_date, r.visits) for r in rows] == [(datetime.date(2026, 3, 1), 10)]


def test_import_older_site_metrics_fetches_week_then_month_and_inserts(
    psh, gateway, temp_db, monkeypatch
):
    sc.config["Database"] = {"type": "sqlite"}  # insert_traffic_rows' backend switch
    calls = []

    def fake_run(command, input_data=None):
        calls.append(command)
        if _period_of(command) == "--period=week":
            # One week starting Mon 2026-02-02, 70 visits -> 7 daily rows of 10.
            return (_metrics_json(("2026-02-02T00:00:00", 70)), "", False)
        # One month, September 2025 (30 days), 30 visits -> 30 daily rows of 1.
        return (_metrics_json(("2025-09-01T00:00:00", 30)), "", False)

    monkeypatch.setattr(gateway, "run_terminus", fake_run)
    session = temp_db.session()
    import_older_site_metrics(session, SITE, "test-site-id.live", END)
    # Fetch order is part of the moved contract: week, then month (B24 comment).
    assert [_period_of(c) for c in calls] == ["--period=week", "--period=month"]
    assert session.query(temp_db.PantheonTraffic).count() == 7 + 30
    feb2 = (
        session.query(temp_db.PantheonTraffic)
        .filter_by(traffic_date=datetime.date(2026, 2, 2))
        .one()
    )
    assert feb2.visits == 10


def test_load_site_traffic_returns_the_window_rows(psh, temp_db):
    session = temp_db.session()
    session.add(
        temp_db.PantheonTraffic(
            site_id="test-site-id",
            traffic_date=datetime.date(2026, 3, 1),
            site_plan="Basic",
            visits=10,
            pages_served=0,
            cache_hits=0,
        )
    )
    session.commit()
    rows = load_site_traffic(session, SITE, START, END)
    assert rows == [
        psh.TrafficRow("test-site-id", datetime.date(2026, 3, 1), "Basic", 10, 0, 0)
    ]
