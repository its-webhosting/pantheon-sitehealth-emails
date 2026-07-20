"""The database layer: every table this program touches and every query it runs.

ORM models (PantheonTraffic, PantheonOverageProtection), their detached row types
(TrafficRow, OverageProtectionRow), the connection-resilience layer (DatabaseUnavailableError /
record_db_reconnect / db_retryable / db_retry), the idempotent units of work it protects
(update_traffic_rows, insert_traffic_rows, load_traffic_rows, load_overage_protection_window),
and db_engine_args -- the ONE engine builder, also exposed as sc.db_engine_args so
plugin/umich/portal.py gets the same pool settings (CLAUDE.md § Database).

Moved from psh/_legacy.py at campaign increment I5 (CAMPAIGN.md section 3.1;
development/2026-07-20-mod-I5-db/SPEC.md).  The governing design is
development/2026-07-13-db-connection-resilience/SPEC.md, which the docstrings below cite by
bare section number.

The run-scoped reconnect counters (db_reconnects_by_site / db_reconnect_failures_by_site)
live in script_context, NOT here: CAMPAIGN.md section 3.4 bars module-level mutable state in
psh/ modules, and the remnant's finish_run/abort_run read them until I13's RunState absorbs
them -- one owning namespace (sc), attribute-accessed at call time by the writer (db_retry,
below) and the remnant readers (SPEC D-i5-1).
"""
import datetime
import sys
import time
from typing import NamedTuple

from rich.markup import escape
from sqlalchemy import (
    Boolean,
    Date,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    insert,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR

import script_context as sc


class Base(DeclarativeBase):
    pass


class PantheonTraffic(Base):
    __tablename__ = "pantheon_traffic"

    site_id: Mapped[str] = mapped_column(CHAR(36))
    traffic_date: Mapped[datetime.date] = mapped_column(Date)
    site_plan: Mapped[str] = mapped_column(String(64))
    visits: Mapped[int] = mapped_column(Integer)
    pages_served: Mapped[int] = mapped_column(Integer)
    cache_hits: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        PrimaryKeyConstraint("site_id", "traffic_date", name="pk_site_id_traffic_date"),
        UniqueConstraint("site_id", "traffic_date", name="uix_site_id_traffic_date"),
    )

    def __repr__(self):
        return (
            f"<{self.site_id} {self.traffic_date} : {self.site_plan} visits={self.visits} "
            f"pages={self.pages_served} cache_hits={self.cache_hits}>"
        )


class PantheonOverageProtection(Base):
    __tablename__ = "pantheon_overage_protection"

    site_id: Mapped[str] = mapped_column(CHAR(36))
    month: Mapped[datetime.date] = mapped_column(Date)
    months_remaining: Mapped[int] = mapped_column(Integer)
    used_this_month: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (
        PrimaryKeyConstraint("site_id", "month", name="pk_op_site_id_traffic_date"),
        UniqueConstraint("site_id", "month", name="uix_op_site_id_traffic_date"),
    )

    def __repr__(self):
        return f"<{self.site_id} {self.month} : {self.months_remaining}>"


class TrafficRow(NamedTuple):
    """A pantheon_traffic row, detached from the ORM.

    Plain data on purpose: a db_retry() rollback expires every live ORM object, so a row held
    across a retryable unit would emit an unretried SELECT on the next attribute read -- outside
    every unit of work.  The attribute names match PantheonTraffic's, so consumers of the
    site_post_traffic data-contract key `traffic_rows` are unaffected.  See SPEC 3.3.2.
    """

    site_id: str
    traffic_date: datetime.date
    site_plan: str
    visits: int
    pages_served: int
    cache_hits: int


class OverageProtectionRow(NamedTuple):
    """A pantheon_overage_protection row, detached from the ORM.

    Plain data for the same reason as TrafficRow: load_overage_protection_window() snapshots the
    site's whole window in one unit of work, and plan_costs() reads it minutes later, after other
    db_retry() units may have rolled back (which expires every live ORM object).  The attribute
    names match PantheonOverageProtection's.
    """

    site_id: str
    month: datetime.date
    months_remaining: int
    used_this_month: bool


class DatabaseUnavailableError(RuntimeError):
    """A database operation failed, was retried once, and failed again.

    Raised by db_retry().  Caught once, around the site loop in main(), which flushes the
    end-of-run artifacts and exits nonzero with a command to re-run what is left (SPEC 3.5).
    """


def record_db_reconnect(counter: dict, site: str | None) -> None:
    """Attribute one reconnect (healed or failed) to `site`, or to "(no site)" outside the loop."""
    key = site if site is not None else "(no site)"
    counter[key] = counter.get(key, 0) + 1


def db_retryable(error: DBAPIError) -> bool:
    """Is this DBAPI error one db_retry() may roll back and re-run?

    NOT a hardcoded class list.  SQLAlchemy's MySQLdb dialect classifies a lost connection by
    error code, not by exception class: mysqlclient raises InterfaceError for errno 0 and
    ProgrammingError for CR_COMMANDS_OUT_OF_SYNC (2014, a connection reaped mid-result-set), and
    both are SIBLINGS of OperationalError under DBAPIError, not subclasses.  What every disconnect
    DOES share is connection_invalidated -- SQLAlchemy sets it from the dialect's is_disconnect().
    So retry on that, plus OperationalError (a deadlock, a lock-wait timeout or too-many-connections
    does not invalidate the connection but is still worth one retry -- SPEC 2.2).

    Everything else -- an IntegrityError, a genuine ProgrammingError bug -- is a real bug: it is a
    DBAPIError but neither an OperationalError nor an invalidated connection, so it propagates
    untouched and stays loud.
    """
    return isinstance(error, OperationalError) or error.connection_invalidated


def db_retry(session, unit, *, what: str, site: str | None = None):
    """Run `unit()`; on a database failure, roll back and re-run it exactly once.

    `unit` MUST be idempotent.  A rollback discards every pending ORM change in the session, so
    the retry re-runs the unit from scratch -- which is why retries happen at unit-of-work
    granularity and NEVER around a single statement that runs while writes are pending
    (SPEC 3.3.1).

    A rollback ALSO expires every loaded ORM object, regardless of expire_on_commit.  So a
    retryable unit must never be placed where live ORM rows will be read afterwards: the read
    would emit a fresh SELECT outside any unit, and therefore outside any retry.  This is why
    load_traffic_rows() returns plain TrafficRow data (SPEC 3.3.2).

    What is retried is decided by db_retryable(), not by an exception class: an OperationalError
    (a lost connection, but also a deadlock, a lock-wait timeout, or too-many-connections -- we
    deliberately do not sniff codes to tell those apart, SPEC 2.2), or ANY DBAPIError whose
    connection was invalidated.  A reaped connection can arrive as an InterfaceError or even a
    ProgrammingError(2014); those are not OperationalError subclasses, and retrying them is the
    whole point of this function.  A DBAPIError that is neither -- an IntegrityError, a real
    ProgrammingError bug -- is a bug and must stay loud, so it is re-raised untouched.
    """
    try:
        return unit()
    except DBAPIError as first_error:
        if not db_retryable(first_error):
            raise
        try:
            session.rollback()
        except DBAPIError as rollback_error:
            if not db_retryable(rollback_error):
                raise  # a real bug surfacing on the rollback: still not ours to rename
            # The rollback hit the wire and died too (the connection was not invalidated, so
            # SQLAlchemy really emitted a ROLLBACK).  Name it rather than let a raw
            # DBAPIError escape past main()'s handler -- SPEC 3.3.3.  It is also the run's most
            # definite connection loss, so it is COUNTED (as a failure): reporting zero here would
            # tell the operator nothing went wrong on the very run that died of it.
            record_db_reconnect(sc.db_reconnect_failures_by_site, site)
            raise DatabaseUnavailableError(
                f"{what}: rollback failed after {first_error}"
            ) from rollback_error
        sc.console.print(
            f":warning: [bold yellow]Lost the database connection during {escape(what)}; "
            "reconnecting and retrying."
        )
        time.sleep(1)
        try:
            result = unit()
        except DBAPIError as retry_error:
            if not db_retryable(retry_error):
                # Not a connection issue itself, but first_error's connection loss never got
                # healed -- record it as a failure so it lands in a dict, not neither (the
                # comment above promises every lost connection lands in exactly one).
                record_db_reconnect(sc.db_reconnect_failures_by_site, site)
                raise  # a real bug surfacing on the retry: still not ours to rename
            record_db_reconnect(sc.db_reconnect_failures_by_site, site)
            raise DatabaseUnavailableError(f"{what}: {retry_error}") from retry_error
        # Counted HERE, not before the retry: a reconnect is a connection that came BACK.  An
        # abort that reported "1 reconnect" alongside "reason: database" was claiming a heal that
        # never happened -- and the operator reads this number to judge whether the connection
        # fix is working.
        record_db_reconnect(sc.db_reconnects_by_site, site)
        return result


def update_traffic_rows(session, site: dict, metrics: dict, start_date, end_date) -> None:
    """Merge a site's daily metrics into pantheon_traffic and commit.

    Idempotent (session.merge() is upsert-by-primary-key), so db_retry() may re-run it.
    """
    # Preload the session with the data we're going to be updating.  This makes the merge()
    # calls below much faster.
    _ = (
        session.query(PantheonTraffic)
        .filter(
            PantheonTraffic.site_id == site["id"],
            PantheonTraffic.traffic_date.between(start_date, end_date),
        )
        .all()
    )
    for e in metrics["timeseries"]:
        entry = metrics["timeseries"][e]
        traffic_date = datetime.datetime.strptime(  # noqa: DTZ007 -- Pantheon env:metrics timestamps are naive date markers; only .date() is taken, and attaching a tzinfo risks an off-by-one-day shift (a behavior change a move may not make)
            entry["datetime"], "%Y-%m-%dT%H:%M:%S"
        ).date()
        if traffic_date == end_date:
            continue  # skip today's partial data
        session.merge(
            PantheonTraffic(
                site_id=site["id"],
                traffic_date=traffic_date,
                site_plan=site["plan_name"],
                visits=entry["visits"],
                pages_served=entry["pages_served"],
                cache_hits=entry["cache_hits"],
            )
        )
    session.commit()


def insert_traffic_rows(session, rows: list) -> None:
    """Insert-or-ignore historical traffic rows and commit.

    Idempotent (ON CONFLICT DO NOTHING / INSERT IGNORE), so db_retry() may re-run it.
    """
    if len(rows) == 0:
        return
    if sc.config["Database"]["type"] == "sqlite":
        session.execute(
            sqlite_insert(PantheonTraffic).on_conflict_do_nothing(
                index_elements=["site_id", "traffic_date"]
            ),
            rows,
        )
    else:  # mysql:
        session.execute(insert(PantheonTraffic).prefix_with("IGNORE"), rows)
    session.commit()


def load_traffic_rows(session, site: dict, start_date, end_date) -> list:
    """Read a site's traffic rows for the report, then RELEASE the connection.

    The commit here looks redundant for a read-only query.  It is not, and it MUST NOT be
    removed: without it the session holds its connection, inside an open transaction, for the
    entire per-site gather (terminus, wp/drush, DNS, cache checks, matplotlib -- minutes).  A
    NAT/firewall on the path to RDS reaps that idle flow and the next query dies with MySQL error
    2013.  Committing returns the connection to the pool, where pool_pre_ping can validate and
    silently replace it on the next checkout.

    Returns plain TrafficRow data rather than ORM rows, so that a later db_retry() rollback --
    which expires every live ORM object -- cannot turn a downstream attribute read into an
    unretried SELECT.  See development/2026-07-13-db-connection-resilience/SPEC.md 3.1, 3.3.2.

    The TrafficRow list is built BEFORE the commit, on purpose: a default session (unlike
    main()'s, which sets expire_on_commit=False) expires every loaded ORM object on commit, and
    reading r.site_id etc. from an expired object triggers a lazy-refresh SELECT that opens a new
    transaction -- silently reintroducing the very connection-holding bug this function exists to
    fix. Materializing first makes "the connection is released on return" true unconditionally,
    independent of expire_on_commit.
    """
    rows = [
        TrafficRow(
            site_id=r.site_id,
            traffic_date=r.traffic_date,
            site_plan=r.site_plan,
            visits=r.visits,
            pages_served=r.pages_served,
            cache_hits=r.cache_hits,
        )
        for r in session.query(PantheonTraffic)
        .filter(
            PantheonTraffic.site_id == site["id"],
            PantheonTraffic.traffic_date.between(start_date, end_date),
        )
        .all()
    ]
    session.commit()  # releases the connection -- see the docstring; MUST NOT be removed
    return rows


def load_overage_protection_window(session, site: dict, start_date, end_date) -> dict:
    """Snapshot a site's overage-protection rows for the report window in ONE query.

    Returns {month (a date, day=1) -> OverageProtectionRow}, for plan_costs()' op_lookup to read
    as a plain dict.  A missing month is simply absent from the dict, so op_lookup's `.get()`
    returns None exactly where the old per-month Session.get() did.

    One query, not ~91.  plan_costs() asks for the overage state once per candidate plan PER
    MONTH (~7 non-Basic plans x ~13 months), and a Session.get() that misses is never negatively
    cached, so it re-SELECTs every time -- and a Basic-plan site, which has no rows at all, missed
    on every single call.  Each of those was its own db_retry() unit against a remote RDS over the
    WAN: pool checkout + pre-ping probe + SELECT + COMMIT.  A snapshot is equivalent because
    nothing writes to pantheon_overage_protection between build_traffic_table_rows()' commit and
    plan_costs()' reads.

    The commit is load_traffic_rows()' commit, for the same reason and with the same rule: it MUST
    NOT be removed.  Even a read autobegins a transaction, and without the commit the session
    would hold that connection, idle, through matplotlib, the Jinja render, the php inliner, the
    SMTP send and the NEXT site's terminus calls -- exactly the reaped-idle-flow bug this change
    exists to fix.  The rows are materialized as plain data BEFORE the commit, so that holds
    regardless of expire_on_commit (see load_traffic_rows()).
    """
    rows = {
        r.month: OverageProtectionRow(
            site_id=r.site_id,
            month=r.month,
            months_remaining=r.months_remaining,
            used_this_month=r.used_this_month,
        )
        for r in session.query(PantheonOverageProtection)
        .filter(
            PantheonOverageProtection.site_id == site["id"],
            PantheonOverageProtection.month.between(start_date.replace(day=1), end_date),
        )
        .all()
    }
    session.commit()  # releases the connection -- see the docstring; MUST NOT be removed
    return rows


def db_engine_args(db_config: dict) -> tuple[str, dict]:
    """Build the (connection string, create_engine kwargs) for the traffic database.

    Behavior-preserving extraction of main()'s inline construction, so the pool settings below
    are unit-testable.  `type` and `name` are read unconditionally: a [Database] section without
    them is a KeyError, not a default (see CLAUDE.md).
    """
    if db_config["type"] == "sqlite":
        return f"sqlite:///{db_config['name']}", {}
    if db_config["type"] == "mysql":
        conn_str = (
            f"mysql+mysqldb://{db_config['user']}:{db_config['password']}@"
            f"{db_config['host']}:{db_config['port']}/{db_config['name']}"
        )
        # The database is remote (RDS) and the network path crosses NAT/firewall middleboxes
        # that reap idle flows.  pool_pre_ping is the LOAD-BEARING setting: it validates the
        # connection at pool checkout and transparently replaces a reaped one -- it is the only
        # thing here that actually defends against the reaping this whole change exists to fix.
        # pool_recycle does NOT: it bounds a connection's total AGE since creation (SQLAlchemy
        # compares time.time() - starttime at checkout), not its idle time, so a NAT gateway with
        # a 350s idle timeout can reap a connection nowhere near 1800s old.  It is a cheap
        # backstop against long-lived-connection problems, nothing more.  Do not weaken or drop
        # pool_pre_ping on the strength of it.  Deliberately hardcoded rather than configurable:
        # development/2026-07-13-db-connection-resilience/SPEC.md section 2.2.
        return conn_str, {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
    sys.exit(f"Unsupported database type: {db_config['type']}")
