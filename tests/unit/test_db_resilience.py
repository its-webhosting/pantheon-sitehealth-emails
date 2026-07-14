"""Unit tests for the database connection-resilience layer.

See development/2026-07-13-db-connection-resilience/SPEC.md.
"""

import datetime

import pytest
import sqlalchemy as db
from sqlalchemy.exc import (
    IntegrityError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)


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


@pytest.mark.unit
def test_load_traffic_rows_releases_the_connection_with_default_session(psh):
    # Same regression as above, but with a DEFAULT sessionmaker (expire_on_commit=True, the
    # SQLAlchemy default -- no flag passed). If load_traffic_rows() materializes the TrafficRow
    # list AFTER the commit instead of before, reading r.site_id etc. from the now-expired ORM
    # rows triggers a lazy-refresh SELECT that opens a fresh transaction, so the connection is
    # NOT actually released -- reintroducing the MySQL-2013 bug this function exists to fix. The
    # prior test alone can't catch that: it builds its session with expire_on_commit=False, which
    # papers over exactly this failure mode.
    engine = db.create_engine("sqlite://")
    psh.Base.metadata.create_all(engine)
    session = db.orm.sessionmaker(bind=engine)()
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
    assert rows[0].visits == 10
    assert rows[0].traffic_date == datetime.date(2026, 3, 1)
    assert rows[0].site_plan == "Basic"


@pytest.mark.unit
def test_load_overage_protection_releases_the_connection_on_a_miss(psh):
    # The mirror of test_load_traffic_rows_releases_the_connection, for the OTHER per-site read.
    # A Session.get() that MISSES the identity map emits a real SELECT, which autobegins a
    # transaction; without the commit the session then holds that connection, idle in a
    # transaction, through matplotlib, the render, the php inliner, the SMTP send and the NEXT
    # site's terminus calls -- the reaped-idle-flow bug all over again.  Misses are the common
    # case: a get() that returns None is never cached, so every candidate plan re-SELECTs.
    engine = db.create_engine("sqlite://")
    psh.Base.metadata.create_all(engine)
    session = db.orm.sessionmaker(bind=engine, expire_on_commit=False)()

    op = psh.load_overage_protection(session, {"id": "s1"}, "2026-03")

    assert op is None                          # nothing in the table: a guaranteed miss
    assert session.in_transaction() is False   # connection returned to the pool


@pytest.mark.unit
def test_load_overage_protection_row_is_readable_after_the_commit(psh):
    # The commit must not cost the caller the row: plan_costs() reads op.used_this_month straight
    # after the lookup, and main()'s session sets expire_on_commit=False for exactly this reason.
    engine = db.create_engine("sqlite://")
    psh.Base.metadata.create_all(engine)
    session = db.orm.sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        psh.PantheonOverageProtection(
            site_id="s1",
            month=datetime.date(2026, 3, 1),
            months_remaining=2,
            used_this_month=True,
        )
    )
    session.commit()

    op = psh.load_overage_protection(session, {"id": "s1"}, "2026-03")

    assert op.used_this_month is True
    assert session.in_transaction() is False


@pytest.mark.unit
def test_resume_command_preserves_every_flag_of_the_original_run(psh):
    # Rebuilt from argv, NOT re-enumerated from sc.options: enumerating would silently drop any
    # flag added later, and the operator pastes this command verbatim.  An --import-older-metrics
    # run whose hint came back as a plain report run would generate and send full reports
    # (SPEC 3.5.1).
    argv = [
        "./pantheon-sitehealth-emails",
        "-c", "prod.toml", "--date", "20260331", "--all", "--import-older-metrics", "-vv",
    ]
    cmd = psh.resume_command(argv, "its-wws-test2")
    for fragment in ("-c prod.toml", "--date 20260331", "--all", "--import-older-metrics", "-vv"):
        assert fragment in cmd
    assert cmd.endswith("--resume-from its-wws-test2")


@pytest.mark.unit
def test_resume_command_replaces_an_existing_resume_from(psh):
    for argv in (
        ["./pantheon-sitehealth-emails", "--all", "--resume-from", "its-wws-test1"],
        ["./pantheon-sitehealth-emails", "--all", "--resume-from=its-wws-test1"],
    ):
        cmd = psh.resume_command(argv, "its-wws-test2")
        assert "its-wws-test1" not in cmd
        assert cmd.count("--resume-from") == 1
        assert cmd.endswith("--resume-from its-wws-test2")


@pytest.mark.unit
def test_rerun_command_lists_the_remaining_sites_and_never_resume_from(psh):
    # --resume-from requires --all, so printing it after an explicit-SITE run would hand the
    # operator a command that exits with an error (SPEC 3.5.1).
    argv = [
        "./pantheon-sitehealth-emails", "--date", "20260331", "-c", "prod.toml",
        "its-wws-test1", "its-wws-test2", "its-wws-test3",
    ]
    cmd = psh.rerun_command(
        argv,
        ["its-wws-test1", "its-wws-test2", "its-wws-test3"],
        ["its-wws-test2", "its-wws-test3"],
    )
    assert "--resume-from" not in cmd
    assert "its-wws-test1" not in cmd        # already done, dropped
    assert cmd.endswith("its-wws-test2 its-wws-test3")
    assert "-c prod.toml" in cmd             # every other flag survives


@pytest.mark.unit
def test_rerun_command_keeps_a_site_name_that_is_an_option_value(psh):
    # A site name in an option's VALUE slot is not a positional.  A naive
    # `[a for a in argv if a not in original_sites]` deletes it, leaving `-c` to swallow the next
    # token -- handing the operator a mangled command at the moment they are least careful
    # (SPEC 3.5.1).  The value-taking options are derived from the parser, so this cannot rot.
    argv = [
        "./pantheon-sitehealth-emails", "-c", "its-wws-test1",  # a config file NAMED like a site
        "--date", "20260331", "its-wws-test1", "its-wws-test2",
    ]
    cmd = psh.rerun_command(
        argv, ["its-wws-test1", "its-wws-test2"], ["its-wws-test2"]
    )
    assert "-c its-wws-test1" in cmd         # the option value survives
    assert cmd.endswith("its-wws-test2")     # only the positional was dropped


@pytest.mark.unit
def test_resume_point_skips_a_site_whose_report_was_already_emailed(psh):
    sites = ["a", "b", "c"]
    # Not emailed: --resume-from is inclusive, so redo the site from the top.
    assert psh.resume_point(sites, "b", emailed=False) == "b"
    # Emailed: resuming AT it would send that owner a duplicate monthly report (SPEC 3.5.3).
    assert psh.resume_point(sites, "b", emailed=True) == "c"
    # Emailed, and it was the last site: nothing remains to resume.
    assert psh.resume_point(sites, "c", emailed=True) is None


def _invalidated_interface_error():
    """A reaped connection as mysqlclient really delivers it: errno 0 -> InterfaceError.

    SQLAlchemy's MySQLdb dialect calls this a disconnect (is_disconnect() matches "(0, '')") and
    invalidates the connection -- but InterfaceError is a SIBLING of OperationalError under
    DBAPIError, not a subclass, so a hardcoded `except OperationalError` never sees it.
    """
    return InterfaceError(
        "SELECT 1", {}, Exception("(0, '')"), connection_invalidated=True
    )


@pytest.mark.unit
def test_db_retryable_classifies_by_invalidation_not_by_class(psh):
    assert psh.db_retryable(_invalidated_interface_error()) is True
    assert psh.db_retryable(_op_error()) is True                      # deadlocks etc. still retried
    assert psh.db_retryable(IntegrityError("INSERT", {}, Exception("dup"))) is False
    # A ProgrammingError(2014) IS a disconnect (CR_COMMANDS_OUT_OF_SYNC: the connection was reaped
    # mid-result-set); a ProgrammingError that is a real SQL bug is not.
    assert psh.db_retryable(
        ProgrammingError("SELECT 1", {}, Exception("(2014, ...)"), connection_invalidated=True)
    ) is True
    assert psh.db_retryable(ProgrammingError("SELCT 1", {}, Exception("syntax"))) is False


@pytest.mark.unit
def test_db_retry_heals_a_disconnect_that_is_not_an_operational_error(psh, monkeypatch):
    # THE bug: a reaped connection can arrive as InterfaceError (errno 0) or ProgrammingError
    # (2014).  Neither is an OperationalError, so neither was retried, neither was caught by
    # main()'s handler, and the run died with a bare traceback -- losing every completed site's
    # artifacts.  Retry on connection_invalidated, not on a class name.
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    session = FakeSession()
    calls = []

    def unit():
        calls.append(1)
        if len(calls) == 1:
            raise _invalidated_interface_error()
        return "rows"

    result = psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
    assert result == "rows"
    assert len(calls) == 2
    assert session.rollbacks == 1
    assert psh.db_reconnects_by_site == {"its-wws-test1": 1}


@pytest.mark.unit
def test_db_retry_names_the_error_when_a_disconnect_retry_also_fails(psh, monkeypatch):
    # And when the retry fails too, it must still become the NAMED error, so main()'s handler
    # routes it to the artifact-flushing abort path instead of a traceback.
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    session = FakeSession()

    def unit():
        raise _invalidated_interface_error()

    with pytest.raises(psh.DatabaseUnavailableError):
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
