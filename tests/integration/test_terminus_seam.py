"""Integration tier: in-process, run_terminus monkeypatched, temp DB, check hook (SPEC §9).

Exercises the single Pantheon seam and the shared-state plumbing without any network.
"""
import datetime

import pytest

from conftest import E2E_SITE_ID

pytestmark = pytest.mark.integration


def test_terminus_parses_json_from_monkeypatched_run_terminus(psh, monkeypatch):
    monkeypatch.setattr(psh, "run_terminus", lambda *a, **k: ('{"framework": "wordpress"}', "", False))
    assert psh.terminus("site:info", "its-wws-test1") == {"framework": "wordpress"}


def test_terminus_empty_output_yields_empty_result(psh, monkeypatch):
    # json.loads("") raises JSONDecodeError, caught at the terminus() try/except -> "".
    monkeypatch.setattr(psh, "run_terminus", lambda *a, **k: ("", "", False))
    assert psh.terminus("env:info", "x") == ""


def test_temp_db_roundtrips_a_traffic_row(temp_db):
    session = temp_db.session()
    session.add(
        temp_db.PantheonTraffic(
            site_id=E2E_SITE_ID,
            traffic_date=datetime.date(2026, 3, 15),
            site_plan="Performance Small",
            visits=1234,
            pages_served=3702,
            cache_hits=2468,
        )
    )
    session.commit()
    rows = session.query(temp_db.PantheonTraffic).all()
    assert len(rows) == 1
    assert rows[0].visits == 1234
    session.close()


def test_check_hook_runs_against_a_site_context(psh, reset_sc):
    sc = reset_sc
    sc.add_hook("check", {"name": "probe", "func": lambda ctx: ctx["notices"].append("seen")})
    ctx = {"notices": []}
    sc.invoke_hooks("check", ctx)
    assert ctx["notices"] == ["seen"]
