"""Unit tests for the database connection-resilience layer.

See development/2026-07-13-db-connection-resilience/SPEC.md.
"""

import datetime

import pytest
import sqlalchemy as db
from sqlalchemy.exc import IntegrityError, OperationalError


@pytest.mark.unit
def test_db_engine_args_sqlite_has_no_pool_kwargs(psh):
    conn_str, kwargs = psh.db_engine_args({"type": "sqlite", "name": "database.db"})
    assert conn_str == "sqlite:///database.db"
    assert kwargs == {}


@pytest.mark.unit
def test_db_engine_args_mysql_enables_pre_ping_and_recycle(psh):
    # pre_ping and recycle are what let SQLAlchemy silently replace a connection that a
    # middlebox reaped while it sat in the pool (SPEC 3.2).  A future edit that drops them
    # re-opens the bug, so they are pinned here.
    conn_str, kwargs = psh.db_engine_args(
        {
            "type": "mysql",
            "name": "sitehealth",
            "user": "u",
            "password": "p",
            "host": "db.example.org",
            "port": 3306,
        }
    )
    assert conn_str == "mysql+mysqldb://u:p@db.example.org:3306/sitehealth"
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 1800
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20


@pytest.mark.unit
def test_db_engine_args_unsupported_type_exits(psh):
    with pytest.raises(SystemExit):
        psh.db_engine_args({"type": "postgres", "name": "x"})


class FakeSession:
    """Minimal stand-in: records rollbacks so the retry contract can be asserted."""

    def __init__(self, rollback_raises=False):
        self.rollbacks = 0
        self.rollback_raises = rollback_raises

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_raises:
            raise _op_error()


def _op_error():
    return OperationalError("SELECT 1", {}, Exception("(2013, 'Lost connection')"))


@pytest.mark.unit
def test_db_retry_heals_a_lost_connection(psh, monkeypatch):
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})  # never assign: psh is session-scoped
    session = FakeSession()
    calls = []

    def unit():
        calls.append(1)
        if len(calls) == 1:
            raise _op_error()
        return "rows"

    result = psh.db_retry(
        session, unit, what="loading traffic rows for its-wws-test1", site="its-wws-test1"
    )
    assert result == "rows"
    assert len(calls) == 2         # the unit was re-run from scratch
    assert session.rollbacks == 1  # ... after a rollback, which is what makes that safe
    # Attributed, not just counted: an operator seeing 37 reconnects needs to know WHICH sites
    # (SPEC 3.6, audit question 4).
    assert psh.db_reconnects_by_site == {"its-wws-test1": 1}


@pytest.mark.unit
def test_db_retry_raises_named_error_when_the_retry_also_fails(psh, monkeypatch):
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    session = FakeSession()

    def unit():
        raise _op_error()

    with pytest.raises(psh.DatabaseUnavailableError) as excinfo:
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
    assert "loading traffic rows" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, OperationalError)  # original error survives


@pytest.mark.unit
def test_db_retry_names_the_error_when_the_rollback_itself_fails(psh, monkeypatch):
    # If SQLAlchemy did not classify the error as a disconnect, the connection is NOT
    # invalidated and the ROLLBACK is really emitted -- and can itself die.  That must not escape
    # as a raw OperationalError past main()'s handler (SPEC 3.3.3).
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    session = FakeSession(rollback_raises=True)

    def unit():
        raise _op_error()

    with pytest.raises(psh.DatabaseUnavailableError):
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")


@pytest.mark.unit
def test_db_retry_never_retries_a_data_bug(psh, monkeypatch):
    # An IntegrityError is a real data bug, not a network blip.  Retrying it would turn a loud
    # failure into a quiet wrong one, so it must propagate untouched (SPEC 3.3).
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    session = FakeSession()
    calls = []

    def unit():
        calls.append(1)
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    with pytest.raises(IntegrityError):
        psh.db_retry(session, unit, what="writing overage protection", site="its-wws-test1")
    assert len(calls) == 1         # not retried
    assert session.rollbacks == 0  # and not swallowed into a rollback


@pytest.mark.unit
def test_load_traffic_rows_releases_the_connection(psh):
    # THE regression test for the bug this whole change exists to fix.  If load_traffic_rows()
    # leaves a transaction open, the connection stays checked out of the pool for the entire
    # per-site gather (minutes), a NAT/firewall reaps the idle flow, and the next query dies with
    # MySQL error 2013.  A committed session reports in_transaction() == False.
    engine = db.create_engine("sqlite://")
    psh.Base.metadata.create_all(engine)
    session = db.orm.sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        psh.PantheonTraffic(
            site_id="s1",
            traffic_date=datetime.date(2026, 3, 1),
            site_plan="Basic",
            visits=10,
            pages_served=20,
            cache_hits=5,
        )
    )
    session.commit()

    rows = psh.load_traffic_rows(
        session, {"id": "s1"}, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
    )

    assert session.in_transaction() is False  # connection returned to the pool
    # Plain data, not live ORM rows: a db_retry rollback expires ORM objects, and a later read of
    # an expired row would emit an unretried SELECT outside every unit (SPEC 3.3.2).
    assert isinstance(rows[0], psh.TrafficRow)
    assert not isinstance(rows[0], psh.PantheonTraffic)
    assert rows[0].visits == 10
    assert rows[0].traffic_date == datetime.date(2026, 3, 1)
    assert rows[0].site_plan == "Basic"
