"""Unit tests for build_traffic_table_rows() -- the extracted, retryable overage-protection unit
of work.  See development/2026-07-13-db-connection-resilience/SPEC.md sections 3.3.1 and 3.4."""

import datetime

import pytest
import sqlalchemy as db
from sqlalchemy.exc import OperationalError

import script_context as sc

PLAN_INFO = {
    "Basic": {"traffic_limit": 25000, "upgrade_at": 25000, "upgrade_to": "Performance Small",
              "downgrade_to": None},
    "Performance Small": {"traffic_limit": 250000, "upgrade_at": 250000,
                          "upgrade_to": "Performance Medium", "downgrade_to": "Basic"},
    "Performance Medium": {"traffic_limit": 500000, "upgrade_at": 500000,
                           "upgrade_to": "Performance Medium",
                           "downgrade_to": "Performance Small"},
}


def make_session(psh):
    engine = db.create_engine("sqlite://")
    psh.Base.metadata.create_all(engine)
    return db.orm.sessionmaker(bind=engine, expire_on_commit=False)()


def call(psh, session):
    """One site, two months, on a plan whose overage protection applies."""
    plan_on_day = {
        datetime.date(2026, 2, 1) + datetime.timedelta(days=n): "Performance Small"
        for n in range(90)
    }
    return psh.build_traffic_table_rows(
        session,
        {"id": "s1", "name": "its-wws-test1"},
        {"2026-02": 300000, "2026-03": 100000},   # February overruns the 250k limit
        plan_on_day,
        PLAN_INFO,
        datetime.date(2026, 2, 1),                # site_plan_start
        datetime.date(2026, 2, 1),                # first_plan_day
        datetime.date(2026, 3, 31),               # last_plan_day
        datetime.date(2026, 2, 1),                # start_date
        datetime.date(2026, 3, 31),               # end_date
        10000,                                    # overage_block_size
        20,                                       # overage_block_cost
    )


def op_rows(psh, session):
    return sorted(
        (r.month, r.months_remaining, r.used_this_month)
        for r in session.query(psh.PantheonOverageProtection).all()
    )


@pytest.mark.unit
def test_build_traffic_table_rows_writes_overage_protection(psh):
    session = make_session(psh)
    rows = call(psh, session)
    assert list(rows.keys()) == ["2026-02", "2026-03"]
    assert rows["2026-02"]["visitors"] == "300,000"
    assert "waived" in rows["2026-02"]["overage-cost"]  # protection absorbed the overage
    assert op_rows(psh, session) == [
        (datetime.date(2026, 2, 1), 3, True),
        (datetime.date(2026, 3, 1), 3, False),
    ]


@pytest.mark.unit
def test_build_traffic_table_rows_is_idempotent_under_retry(psh, monkeypatch):
    # The claim db_retry()'s whole design rests on (SPEC 3.3.1).  The failure MUST land while an
    # earlier month's overage row is already pending -- that is the ONLY position where a rollback
    # could discard writes and a naive retry could commit a partial write set.  The gets are:
    #   1: the pre-loop session.get, before the for-month loop starts
    #   2: February's session.get, inside the loop, BEFORE that iteration's session.add()
    #   3: March's session.get, inside the loop, AFTER February's session.add() -- pending writes exist
    # An earlier draft of this test raised on call 2, where session.new is empty: it proved
    # nothing.  The assert below fails loudly if the fixture ever drifts back to that position.
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(sc, "run_state", psh.RunState())
    session = make_session(psh)
    expected_rows = call(psh, session)
    expected_ops = op_rows(psh, session)

    session = make_session(psh)
    calls = []
    real_get = session.get

    def flaky_get(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            assert session.new, "the retry must be exercised WITH pending writes (SPEC 3.3.1)"
            raise OperationalError("SELECT", {}, Exception("(2013, 'Lost connection')"))
        return real_get(*args, **kwargs)

    monkeypatch.setattr(session, "get", flaky_get)
    rows = psh.db_retry(
        session, lambda: call(psh, session), what="overage protection", site="its-wws-test1"
    )

    assert rows == expected_rows
    assert op_rows(psh, session) == expected_ops  # no partial write set survived


@pytest.mark.unit
def test_build_traffic_table_rows_for_a_zero_traffic_site(psh):
    # The real zero-traffic shape (SPEC 3.7): main() pre-seeds visits_by_month to 0 for every
    # month in the window (the while-loop just before it reads the traffic rows), so an EMPTY
    # dict is unreachable -- do not test for it. With no traffic rows, plan_on_day falls back to
    # {end_date: current_plan} (main()'s "brand-new site with no traffic history yet" branch) and
    # site_plan_start is the report month, so months before it hit build_traffic_table_rows()'s
    # `if ymd1 < site_plan_start: continue`.
    session = make_session(psh)
    rows = psh.build_traffic_table_rows(
        session,
        {"id": "s1", "name": "its-wws-test1"},
        {"2026-02": 0, "2026-03": 0},
        {datetime.date(2026, 3, 31): "Basic"},
        PLAN_INFO,
        datetime.date(2026, 3, 1),                # site_plan_start = the report month
        datetime.date(2026, 3, 31),               # first_plan_day
        datetime.date(2026, 3, 31),               # last_plan_day
        datetime.date(2026, 2, 1),
        datetime.date(2026, 3, 31),
        10000,
        20,
    )
    assert list(rows.keys()) == ["2026-03"]
    assert rows["2026-03"]["visitors"] == "0"
    assert op_rows(psh, session) == []  # Basic plan: no overage-protection rows
