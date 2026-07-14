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

    def __init__(self, rollback_raises=False, rollback_error=None):
        self.rollbacks = 0
        self.rollback_raises = rollback_raises
        self.rollback_error = rollback_error

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_raises:
            raise self.rollback_error if self.rollback_error is not None else _op_error()


def _op_error():
    return OperationalError("SELECT 1", {}, Exception("(2013, 'Lost connection')"))


@pytest.mark.unit
def test_db_retry_heals_a_lost_connection(psh, monkeypatch):
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})  # never assign: psh is session-scoped
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
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
    # (SPEC 3.6, audit question 4).  A HEAL, counted only because the retry actually returned.
    assert psh.db_reconnects_by_site == {"its-wws-test1": 1}
    assert psh.db_reconnect_failures_by_site == {}


@pytest.mark.unit
def test_db_retry_raises_named_error_when_the_retry_also_fails(psh, monkeypatch):
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    session = FakeSession()

    def unit():
        raise _op_error()

    with pytest.raises(psh.DatabaseUnavailableError) as excinfo:
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
    assert "loading traffic rows" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, OperationalError)  # original error survives
    # The retry did not heal anything, so it is NOT a reconnect.  The old code incremented before
    # the retry ran, so the aborted run's metadata claimed `"reason": "database"` AND
    # `"db_reconnects_this_run": 1` -- a heal that never happened.
    assert psh.db_reconnects_by_site == {}
    assert psh.db_reconnect_failures_by_site == {"its-wws-test1": 1}


@pytest.mark.unit
def test_db_retry_names_the_error_when_the_rollback_itself_fails(psh, monkeypatch):
    # If SQLAlchemy did not classify the error as a disconnect, the connection is NOT
    # invalidated and the ROLLBACK is really emitted -- and can itself die.  That must not escape
    # as a raw OperationalError past main()'s handler (SPEC 3.3.3).
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    session = FakeSession(rollback_raises=True)

    def unit():
        raise _op_error()

    with pytest.raises(psh.DatabaseUnavailableError):
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
    # The run's most DEFINITE connection loss -- it never even got to the retry.  The old code
    # raised before the increment, so this case reported ZERO reconnects: nothing went wrong,
    # said the counter, on the run that died of exactly this.
    assert psh.db_reconnects_by_site == {}
    assert psh.db_reconnect_failures_by_site == {"its-wws-test1": 1}


@pytest.mark.unit
def test_db_retry_does_not_rename_a_non_retryable_rollback_failure(psh, monkeypatch):
    # The rollback guard must use db_retryable(), the SAME predicate as everywhere else in this
    # function -- not treat every DBAPIError from rollback() as a database outage. A genuine bug
    # (e.g. an IntegrityError) surfacing from rollback() must propagate untouched, not be renamed
    # to DatabaseUnavailableError and routed to the "exit 1, safe to resume" path.
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    rollback_bug = IntegrityError("ROLLBACK", {}, Exception("duplicate key"))
    session = FakeSession(rollback_raises=True, rollback_error=rollback_bug)

    def unit():
        raise _op_error()

    with pytest.raises(IntegrityError) as excinfo:
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
    assert excinfo.value is rollback_bug
    # A data bug is not a connection loss, so it is counted as neither.
    assert psh.db_reconnects_by_site == {}
    assert psh.db_reconnect_failures_by_site == {}


@pytest.mark.unit
def test_db_retry_never_retries_a_data_bug(psh, monkeypatch):
    # An IntegrityError is a real data bug, not a network blip.  Retrying it would turn a loud
    # failure into a quiet wrong one, so it must propagate untouched (SPEC 3.3).
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
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


def op_window_session(psh, rows=()):
    """A DEFAULT sessionmaker (expire_on_commit=True) seeded with overage-protection rows.

    Default on purpose: if load_overage_protection_window() materialized its plain rows AFTER the
    commit, the expired ORM objects would lazy-refresh with a fresh SELECT -- reopening a
    transaction and silently un-releasing the connection.  expire_on_commit=False would paper
    over exactly that.
    """
    engine = db.create_engine("sqlite://")
    psh.Base.metadata.create_all(engine)
    session = db.orm.sessionmaker(bind=engine)()
    for month, months_remaining, used in rows:
        session.add(
            psh.PantheonOverageProtection(
                site_id="s1",
                month=month,
                months_remaining=months_remaining,
                used_this_month=used,
            )
        )
    session.commit()
    return session


@pytest.mark.unit
def test_load_overage_protection_window_empty_releases_the_connection(psh):
    # The common case: a Basic-plan site has NO overage-protection rows at all
    # (build_traffic_table_rows() writes none for Basic).  It must cost ONE query, not ~91 misses,
    # and -- like every other unit -- it must leave no transaction open: the session would
    # otherwise hold that connection, idle, through matplotlib, the render, the php inliner, the
    # SMTP send and the NEXT site's terminus calls (the reaped-idle-flow bug).
    session = op_window_session(psh)

    window = psh.load_overage_protection_window(
        session, {"id": "s1"}, datetime.date(2025, 4, 1), datetime.date(2026, 3, 31)
    )

    assert window == {}
    assert session.in_transaction() is False   # connection returned to the pool


@pytest.mark.unit
def test_load_overage_protection_window_snapshots_plain_rows_in_range(psh):
    session = op_window_session(
        psh,
        [
            (datetime.date(2025, 3, 1), 4, False),   # BEFORE the window
            (datetime.date(2025, 4, 1), 3, True),
            (datetime.date(2026, 3, 1), 2, False),
            (datetime.date(2026, 4, 1), 1, True),    # AFTER the window
        ],
    )

    window = psh.load_overage_protection_window(
        session, {"id": "s1"}, datetime.date(2025, 4, 1), datetime.date(2026, 3, 31)
    )

    assert sorted(window) == [datetime.date(2025, 4, 1), datetime.date(2026, 3, 1)]
    row = window[datetime.date(2025, 4, 1)]
    # Plain data, not live ORM rows: a db_retry rollback expires ORM objects, and plan_costs()
    # reads this snapshot minutes later -- an expired row would emit an unretried SELECT.
    assert isinstance(row, psh.OverageProtectionRow)
    assert not isinstance(row, psh.PantheonOverageProtection)
    assert row.used_this_month is True
    assert row.months_remaining == 3
    assert window[datetime.date(2026, 3, 1)].used_this_month is False
    assert session.in_transaction() is False


@pytest.mark.unit
def test_load_overage_protection_window_is_scoped_to_the_site(psh):
    session = op_window_session(psh, [(datetime.date(2026, 3, 1), 2, True)])
    session.add(
        psh.PantheonOverageProtection(
            site_id="other",
            month=datetime.date(2026, 3, 1),
            months_remaining=0,
            used_this_month=False,
        )
    )
    session.commit()

    window = psh.load_overage_protection_window(
        session, {"id": "s1"}, datetime.date(2025, 4, 1), datetime.date(2026, 3, 31)
    )

    assert list(window) == [datetime.date(2026, 3, 1)]
    assert window[datetime.date(2026, 3, 1)].site_id == "s1"


@pytest.mark.unit
def test_op_lookup_over_the_window_matches_the_old_session_get(psh):
    # The dict-backed op_lookup main() now injects into plan_costs(): a present month yields the
    # row, a missing month yields None -- exactly what Session.get() returned.
    window = psh.load_overage_protection_window(
        op_window_session(psh, [(datetime.date(2026, 3, 1), 2, True)]),
        {"id": "s1"},
        datetime.date(2025, 4, 1),
        datetime.date(2026, 3, 31),
    )

    def op_lookup(month):
        return window.get(datetime.date.fromisoformat(month + "-01"))

    assert op_lookup("2026-03").used_this_month is True
    assert op_lookup("2025-12") is None


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
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
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
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    session = FakeSession()

    def unit():
        raise _invalidated_interface_error()

    with pytest.raises(psh.DatabaseUnavailableError):
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")


@pytest.mark.unit
def test_db_retry_records_a_failure_when_the_retry_raises_a_non_retryable_error(psh, monkeypatch):
    # first_error is a genuine, retryable connection loss; the rollback succeeds; but the RETRY
    # then raises a DIFFERENT, non-retryable DBAPIError (an unrelated data bug, e.g. a duplicate
    # key hit only after reconnecting).  The comment above db_retry() promises every lost
    # connection lands in exactly one of the two dicts -- before this fix, this path recorded
    # neither: first_error's connection loss was never healed (the retry didn't return) AND never
    # counted as a failure, because the guard re-raised before reaching either record call.
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    session = FakeSession()
    calls = []

    def unit():
        calls.append(1)
        if len(calls) == 1:
            raise _op_error()
        raise IntegrityError("INSERT", {}, Exception("dup"))

    with pytest.raises(IntegrityError):
        psh.db_retry(session, unit, what="loading traffic rows", site="its-wws-test1")
    assert psh.db_reconnects_by_site == {}
    assert psh.db_reconnect_failures_by_site == {"its-wws-test1": 1}
