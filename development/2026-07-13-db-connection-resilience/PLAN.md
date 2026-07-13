# Database Connection Resilience — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.
>
> **Read `development/2026-07-13-db-connection-resilience/SPEC.md` first.** This plan implements
> it; the spec carries the reasoning, and section references below (§3.1 etc.) point into it.
>
> **Revised after two rounds of adversarial review.** Round 2 found that an earlier draft's claim
> "the failed site is absent from `site_results`" was false (it is written mid-gather at `:1833` /
> `:2152`), that a resume hint on a non-`--all` abort would fail when pasted (`--resume-from`
> requires `--all`, `:1238`), that the idempotence test never reached the pending-write state it
> claimed to test, and that nothing tested the site-loop `try:` wrapper at all. All are fixed below.

**Goal:** Stop `--all` runs from dying with `MySQLdb.OperationalError (2013)` after a middlebox
reaps the database connection that the program leaves idle across each site's data-gather.

**Architecture:** Release the connection before the gather (the actual fix), make the pool
self-healing (`pool_pre_ping` / `pool_recycle`), retry database failures at an idempotent
unit-of-work granularity, and on an unrecoverable failure *or a Ctrl-C* flush the epilogue, print a
command that re-runs exactly what is left, and exit nonzero.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x ORM, `mysqlclient` (MySQLdb) against AWS RDS MySQL;
sqlite for tests and goldens; pytest via `./run-tests`.

## Global Constraints

- **The four e2e goldens MUST come out byte-identical.** `./run-tests --update-goldens` is
  **prohibited** for this work. A golden diff is a bug report, not a refresh prompt. (SPEC §5.)
- **The goldens do NOT cover stdout or the artifact files** — they snapshot only the rendered
  report's html/txt. `finish_run()` is covered only by `tests/integration/test_finish_run.py`, and
  the site-loop `try:` wrapper only by `tests/e2e/test_abort_e2e.py`. (SPEC §5.)
- Catch **`sqlalchemy.exc.OperationalError` only** inside `db_retry`. **NEVER** `except Exception`,
  **NEVER** a bare `except`. The two narrow `(SQLAlchemyError, OSError)` catches in `finish_run()` /
  `abort_run()` are the only exceptions, and each carries a comment saying why. (SPEC §3.3, §3.3.3.)
- **NEVER** wrap `db_retry` around a single statement executed while the session holds pending
  writes. (SPEC §3.3.1.)
- **NEVER** let `traffic_rows` carry live ORM objects. (SPEC §3.3.2.)
- **NEVER** print `--resume-from` on a non-`--all` abort — it requires `--all` (`:1238`) and would
  fail when pasted. (SPEC §3.5.1.)
- Keep the sqlite engine kwargs `{}`. Pool settings are MySQL-only. (SPEC §3.2.)
- **Tests MUST set the module-level counters with `monkeypatch.setattr(psh, …)`**, never by direct
  assignment: `psh` is **session-scoped** and `reset_sc` does not restore module attributes. (SPEC §5.)
- House style: type-hint tuples like `-> (str, dict)` are the existing convention in this file.
- Commit after each task. Do not branch (repo convention: only branch when explicitly directed).

---

### Task 1: Engine args — pool settings and `expire_on_commit`

**Files:**
- Modify: `pantheon-sitehealth-emails:1284-1302`
- Test: `tests/unit/test_db_resilience.py` (create)

**Interfaces:**
- Produces: `db_engine_args(db_config: dict) -> (str, dict)` — module-level, importable as
  `psh.db_engine_args`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_db_resilience.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./run-tests tests/unit/test_db_resilience.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'db_engine_args'`

- [ ] **Step 3: Extract the helper and add the settings**

Add `db_engine_args()` at module level, near `sites_from_resume_point` (`:1117-1135`):

```python
def db_engine_args(db_config: dict) -> (str, dict):
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
        # that reap idle flows.  pool_pre_ping validates a connection at pool checkout and
        # transparently replaces a reaped one; pool_recycle retires connections before any
        # plausible middlebox idle timeout.  Deliberately hardcoded rather than configurable:
        # development/2026-07-13-db-connection-resilience/SPEC.md section 2.2.
        return conn_str, {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
    sys.exit(f"Unsupported database type: {db_config['type']}")
```

Replace `pantheon-sitehealth-emails:1284-1302` with:

```python
    traffic_db_conn_str, traffic_db_conn_kwargs = db_engine_args(sc.config["Database"])

    db_engine = db.create_engine(
        traffic_db_conn_str,
        echo=True if sc.options.verbose >= 2 else False,
        **traffic_db_conn_kwargs,
    )
    # expire_on_commit=False is REQUIRED, not a tuning knob: load_traffic_rows() commits to
    # release the connection before the gather (SPEC 3.1), and the report reads those rows
    # afterwards.  With expiry on, that commit would silently re-SELECT every row.  Safe here
    # because both models use composite natural primary keys with no server defaults, so nothing
    # depends on a post-commit refresh.
    db_session_factory = db.orm.sessionmaker(bind=db_engine, expire_on_commit=False)
    db_session = db_session_factory()
```

- [ ] **Step 4: Run the tests**

Run: `./run-tests tests/unit/test_db_resilience.py -v` → 3 passed.

- [ ] **Step 5: Verify the goldens did not move**

Run: `./run-tests --fast`
Expected: all pass, zero golden diffs. (A diff means `expire_on_commit=False` changed observable
output — stop and investigate; do NOT update the golden.)

- [ ] **Step 6: Commit**

```bash
git add pantheon-sitehealth-emails tests/unit/test_db_resilience.py
git commit -m "feat(db): pool_pre_ping/pool_recycle for MySQL, expire_on_commit=False

Extracts db_engine_args() so the pool settings are unit-testable.  These settings are inert on
their own -- they only take effect once the session releases its connection before the per-site
gather (Task 3).  See development/2026-07-13-db-connection-resilience/SPEC.md."
```

---

### Task 2: `DatabaseUnavailableError` and `db_retry()`

**Files:**
- Modify: `pantheon-sitehealth-emails` — imports (`:35`, `:49-60`); the exception class and helpers
  near `ResumeSiteNotFoundError` (`:1117`)
- Test: `tests/unit/test_db_resilience.py` (extend)

**Interfaces:**
- Produces:
  - `DatabaseUnavailableError(RuntimeError)`
  - `db_retry(session, unit, *, what: str, site: str = None)` — runs `unit()`; on
    `OperationalError`, rolls back, counts the reconnect against `site`, and re-runs `unit()` once;
    raises `DatabaseUnavailableError` if the retry (or the rollback itself) fails.
  - `db_reconnects_by_site` — module-level `dict[str, int]`, the **single** source of truth for
    reconnect counts. The total is `sum(db_reconnects_by_site.values())`; there is no separate
    counter to drift out of sync with it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_db_resilience.py  (append)


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


```

The credential-leak test does real (refused) network I/O, so it belongs in the **integration**
tier — `pyproject.toml` defines `unit` as "pure/in-process function tests, no I/O". Create
`tests/integration/test_db_credentials.py`:

```python
# tests/integration/test_db_credentials.py
"""The abort handler prints the underlying database error.  It must never render the connection
URL, which embeds the DB password.  See SPEC section 3.8.
"""

import pytest
import sqlalchemy as db


@pytest.mark.integration
def test_db_retry_error_leaks_no_credentials(psh, monkeypatch):
    # Driven through a REAL engine whose URL contains a password, so a leak is actually possible
    # and this assertion can fail.  (A hand-built OperationalError contains no URL at all, which
    # is what made an earlier draft of this test vacuous.)
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    # connect_timeout=1: loopback port 1 normally REFUSES instantly, but a host that DROPs it
    # would otherwise hang the suite for MySQLdb's default timeout.
    engine = db.create_engine(
        "mysql+mysqldb://dbuser:hunter2@127.0.0.1:1/sitehealth",
        connect_args={"connect_timeout": 1},
    )
    session = db.orm.sessionmaker(bind=engine)()

    def unit():  # the connection is refused: MySQLdb raises OperationalError on connect
        return session.execute(db.text("SELECT 1")).all()

    with pytest.raises(psh.DatabaseUnavailableError) as excinfo:
        psh.db_retry(session, unit, what="probing the database", site="its-wws-test1")
    message = str(excinfo.value)
    # Assert on the password and the whole URL -- NOT merely on the host: MySQLdb's own 2003
    # error text contains "127.0.0.1", so a host-only assertion would pass for the wrong reason.
    assert "hunter2" not in message
    assert str(engine.url) not in message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests tests/unit/test_db_resilience.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'db_retry'`

- [ ] **Step 3: Implement**

Extend the existing `typing` import (`:35`) to `from typing import Any, NamedTuple`, add `import
signal` to the stdlib import block (`:13-35`, alphabetical: after `shlex`/`stat`), and add to the
SQLAlchemy imports (`:49-60`):

```python
from sqlalchemy.exc import OperationalError, SQLAlchemyError
```

Add next to `ResumeSiteNotFoundError` (`:1117`):

```python
class DatabaseUnavailableError(RuntimeError):
    """A database operation failed, was retried once, and failed again.

    Raised by db_retry().  Caught once, around the site loop in main(), which flushes the
    end-of-run artifacts and exits nonzero with a command to re-run what is left (SPEC 3.5).
    """


# Reconnects healed by db_retry(), attributed to the site that caused them.  The single source
# of truth: the run total is sum(db_reconnects_by_site.values()), so there is no second counter
# to drift out of sync.  Reported on the console and in results.json's _run key (SPEC 3.6).
db_reconnects_by_site = {}


def db_retry(session, unit, *, what: str, site: str = None):
    """Run `unit()`; on a database failure, roll back and re-run it exactly once.

    `unit` MUST be idempotent.  A rollback discards every pending ORM change in the session, so
    the retry re-runs the unit from scratch -- which is why retries happen at unit-of-work
    granularity and NEVER around a single statement that runs while writes are pending
    (SPEC 3.3.1).

    A rollback ALSO expires every loaded ORM object, regardless of expire_on_commit.  So a
    retryable unit must never be placed where live ORM rows will be read afterwards: the read
    would emit a fresh SELECT outside any unit, and therefore outside any retry.  This is why
    load_traffic_rows() returns plain TrafficRow data (SPEC 3.3.2).

    Only OperationalError is retried -- a lost connection, but also a deadlock, a lock-wait
    timeout, or too-many-connections, which MySQLdb surfaces through the same class.  We
    deliberately do not sniff error codes to tell them apart (SPEC 2.2); the abort message says
    "a database operation failed" and prints the underlying error, which names the real cause.
    IntegrityError, ProgrammingError and friends are real bugs and must stay loud.
    """
    try:
        return unit()
    except OperationalError as first_error:
        try:
            session.rollback()
        except OperationalError as rollback_error:
            # The rollback hit the wire and died too (the connection was not invalidated, so
            # SQLAlchemy really emitted a ROLLBACK).  Name it rather than let a raw
            # OperationalError escape past main()'s handler -- SPEC 3.3.3.
            raise DatabaseUnavailableError(
                f"{what}: rollback failed after {first_error}"
            ) from rollback_error
        key = site if site is not None else "(no site)"
        db_reconnects_by_site[key] = db_reconnects_by_site.get(key, 0) + 1
        sc.console.print(
            f":warning: [bold yellow]Lost the database connection during {what}; "
            "reconnecting and retrying."
        )
        time.sleep(1)
        try:
            return unit()
        except OperationalError as retry_error:
            raise DatabaseUnavailableError(f"{what}: {retry_error}") from retry_error
```

- [ ] **Step 4: Run the tests**

Run: `./run-tests tests/unit/test_db_resilience.py tests/integration/test_db_credentials.py -v`
Expected: 8 passed (3 from Task 1, 4 unit + 1 integration here).

- [ ] **Step 5: Commit**

```bash
git add pantheon-sitehealth-emails tests/unit/test_db_resilience.py \
        tests/integration/test_db_credentials.py
git commit -m "feat(db): add db_retry() and DatabaseUnavailableError

Retries a failed database operation once, at unit-of-work granularity.  Statement-level retry
would roll back pending ORM writes and commit a partial write set -- SPEC 3.3.1.  A failing
rollback is itself converted to DatabaseUnavailableError so no raw OperationalError escapes.
Reconnects are attributed to the site that caused them."
```

---

### Task 3: Release the connection before the gather

This is the bug fix. Tasks 1 and 2 are inert without it.

**Files:**
- Modify: `pantheon-sitehealth-emails:1550-1632`; add `TrafficRow` after the models (`:130`)
- Test: `tests/unit/test_db_resilience.py` (extend)

**Interfaces:**
- Consumes: `db_retry` (Task 2).
- Produces:
  - `TrafficRow(NamedTuple)` — `site_id`, `traffic_date`, `site_plan`, `visits`, `pages_served`,
    `cache_hits`. **Same attribute names as `PantheonTraffic`**, so every consumer of
    `site_context["traffic_rows"]` keeps working unchanged.
  - `update_traffic_rows(session, site, metrics, start_date, end_date) -> None`
  - `insert_traffic_rows(session, rows) -> None`
  - `load_traffic_rows(session, site, start_date, end_date) -> list[TrafficRow]` — selects,
    **commits to release the connection**, returns plain data

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_db_resilience.py  (append)


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./run-tests tests/unit/test_db_resilience.py::test_load_traffic_rows_releases_the_connection -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'load_traffic_rows'`

- [ ] **Step 3: Add `TrafficRow` and the three units**

After the model definitions (`:130`):

```python
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
```

At module level, after `db_retry()`:

```python
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
        traffic_date = datetime.datetime.strptime(
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
    """
    rows = (
        session.query(PantheonTraffic)
        .filter(
            PantheonTraffic.site_id == site["id"],
            PantheonTraffic.traffic_date.between(start_date, end_date),
        )
        .all()
    )
    session.commit()
    return [
        TrafficRow(
            site_id=r.site_id,
            traffic_date=r.traffic_date,
            site_plan=r.site_plan,
            visits=r.visits,
            pages_served=r.pages_served,
            cache_hits=r.cache_hits,
        )
        for r in rows
    ]
```

- [ ] **Step 4: Wire them into `main()`**

Replace `:1550-1632` (from `sc.debug(f"...Updating metrics...")` through the `results = (...)`
query) with:

```python
        sc.debug(f"[bold magenta]=== Updating metrics for {site['name']}:")
        db_retry(
            db_session,
            lambda: update_traffic_rows(db_session, site, metrics, start_date, end_date),
            what=f"updating traffic rows for {site['name']}",
            site=site["name"],
        )

        if sc.options.import_older_metrics:
            sc.console.print(
                f"[bold magenta]=== Importing older metrics for {site['name']}:"
            )
            # The terminus call stays OUTSIDE the retried unit: a retry must not re-run it.
            # Order (fetch week -> insert week -> fetch month -> insert month) is unchanged.
            for period in ("week", "month"):
                new_rows = get_old_metrics(live_site, site, period, end_date)
                db_retry(
                    db_session,
                    lambda rows=new_rows: insert_traffic_rows(db_session, rows),
                    what=f"importing older {period} metrics for {site['name']}",
                    site=site["name"],
                )
            continue  # skip the rest of the processing for the sites

        if sc.options.update:
            sc.console.print("site visitors updated, skipping report")
            continue

        # Get all the data we will use.  This ALSO releases the DB connection before the gather
        # below -- see load_traffic_rows().
        results = db_retry(
            db_session,
            lambda: load_traffic_rows(db_session, site, start_date, end_date),
            what=f"loading traffic rows for {site['name']}",
            site=site["name"],
        )
```

- [ ] **Step 5: Run the tests**

Run: `./run-tests --fast`
Expected: all pass, **zero golden diffs**. The goldens render the traffic table from these rows, so
they prove `TrafficRow` and the extraction are behavior-preserving.

- [ ] **Step 6: Commit**

```bash
git add pantheon-sitehealth-emails tests/unit/test_db_resilience.py
git commit -m "fix(db): release the DB connection before the per-site gather

The report's traffic SELECT opened a transaction that was never committed, so the session held
its connection -- idle, in-transaction -- for the whole gather (minutes).  A middlebox on the
path to RDS reaped the flow and the next query died with 'Lost connection to server during
query' (2013), killing hour-long --all runs.  Committing the read releases the connection to the
pool, where pool_pre_ping (Task 1) can heal it.

load_traffic_rows() returns plain TrafficRow data: a rollback expires live ORM objects, so ORM
rows held across a retryable unit would lazily re-SELECT outside any retry."
```

---

### Task 4: Extract and retry the overage-protection build

**Files:**
- Modify: `pantheon-sitehealth-emails:3278-3380` (extract), `:3400-3408` (`op_lookup` retry)
- Test: `tests/unit/test_traffic_table_rows.py` (create)

**Interfaces:**
- Consumes: `db_retry` (Task 2).
- Produces: `build_traffic_table_rows(session, site, visits_by_month, plan_on_day, plan_info,
  site_plan_start, first_plan_day, last_plan_day, start_date, end_date, overage_block_size,
  overage_block_cost) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_traffic_table_rows.py
"""Unit tests for build_traffic_table_rows() -- the extracted, retryable overage-protection unit
of work.  See development/2026-07-13-db-connection-resilience/SPEC.md sections 3.3.1 and 3.4."""

import datetime

import pytest
import sqlalchemy as db
from sqlalchemy.exc import OperationalError

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
    #   1: the pre-loop get (:3280)   2: February's get (:3343, BEFORE February's add)
    #   3: March's get (:3343, AFTER February's add -- pending writes exist)
    # An earlier draft of this test raised on call 2, where session.new is empty: it proved
    # nothing.  The assert below fails loudly if the fixture ever drifts back to that position.
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
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
    # month in the window (:2848-2853), so an EMPTY dict is unreachable -- do not test for it.
    # With no traffic rows, plan_on_day falls back to {end_date: current_plan} (:2880) and
    # site_plan_start is the report month, so months before it hit the `continue` at :3297.
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests tests/unit/test_traffic_table_rows.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_traffic_table_rows'`

- [ ] **Step 3: Extract the function**

Move `:3278-3380` **verbatim** into a module-level function — the body unchanged apart from taking
its inputs as parameters, renaming `db_session` → `session`, and returning `traffic_table_rows`.
`site_plan_start` is computed by `main()` (read again at `:3395`/`:3417`) and passed in.

```python
def build_traffic_table_rows(
    session,
    site: dict,
    visits_by_month: dict,
    plan_on_day: dict,
    plan_info: dict,
    site_plan_start: datetime.date,
    first_plan_day: datetime.date,
    last_plan_day: datetime.date,
    start_date: datetime.date,
    end_date: datetime.date,
    overage_block_size: int,
    overage_block_cost: float,
) -> dict:
    """Build the report's per-month traffic table and persist overage-protection state.

    Idempotent, so db_retry() may re-run it after a rollback: every local (traffic_table_rows,
    op_remaining, old_plan) is reset on entry, and the PantheonOverageProtection rows are
    get-or-create by primary key.  Extracting this block out of main() is what makes that true --
    see SPEC 3.3.1 for what a statement-level retry would corrupt instead.
    """
    traffic_table_rows = {}
    d = (start_date.replace(day=1) - datetime.timedelta(days=15)).replace(day=1)
    op = session.get(PantheonOverageProtection, {"site_id": site["id"], "month": d})
    op_remaining = 0 if op is None else op.months_remaining
    old_plan = None
    # ... the existing loop body from :3286-:3378, verbatim, with db_session -> session ...
    session.commit()  # save the changes we made to the pantheon_overage_protection table
    return traffic_table_rows
```

In `main()`, replace `:3278-3380` with:

```python
        site_plan_start = plan_over_time[0]["start"].replace(day=1)
        traffic_table_rows = db_retry(
            db_session,
            lambda: build_traffic_table_rows(
                db_session,
                site,
                visits_by_month,
                plan_on_day,
                plan_info,
                site_plan_start,
                first_plan_day,
                last_plan_day,
                start_date,
                end_date,
                overage_block_size,
                overage_block_cost,
            ),
            what=f"building the traffic table for {site['name']}",
            site=site["name"],
        )
```

- [ ] **Step 4: Retry `op_lookup`**

`op_lookup` (`:3401-3408`) runs *after* the commit inside `build_traffic_table_rows()`, so no writes
are pending and a statement-level retry is safe here (SPEC §3.3.1 table):

```python
            def op_lookup(month):
                return db_retry(
                    db_session,
                    lambda: db_session.get(
                        PantheonOverageProtection,
                        {
                            "site_id": site["id"],
                            "month": datetime.date.fromisoformat(month + "-01"),
                        },
                    ),
                    what=f"looking up overage protection for {site['name']} {month}",
                    site=site["name"],
                )
```

- [ ] **Step 5: Run the tests**

Run: `./run-tests --fast` → all pass, **zero golden diffs**.

- [ ] **Step 6: Commit**

```bash
git add pantheon-sitehealth-emails tests/unit/test_traffic_table_rows.py
git commit -m "refactor(db): extract build_traffic_table_rows() and retry it as a unit

The overage-protection block interleaved DB writes with report-table building and carried
loop-local state, so it could not be retried safely.  Extracted, it resets that state on entry
and is idempotent -- which is what lets db_retry() re-run it after a rollback without committing
a partial write set.  The idempotence test fails the unit WITH pending writes, the only position
that would expose one."
```

---

### Task 5: Extract `finish_run()`

**Files:**
- Modify: `pantheon-sitehealth-emails:3932-3967`
- Test: `tests/integration/test_finish_run.py` (create)

**The epilogue is `:3932`–`:3967`.** It has FOUR parts, all of which move: the `if sc.options.all:`
artifact-writing branch, the `else:` branch that prints notices and `site_results` to the console,
the unconditional "Site savings" totals, and `sc.debug("Done!")`. **No golden covers any of this**
— the test below is the only thing standing between an implementer and silently deleting the
`else:` branch.

**Interfaces:**
- Consumes: `db_reconnects_by_site` (Task 2).
- Produces: `finish_run(db_session, db_engine, site_count, emails_sent, all_warnings, site_results,
  site_savings, *, aborted_at=None, reason=None) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_finish_run.py
"""finish_run() -- the end-of-run epilogue, now called from two places (normal completion and the
abort path).  The e2e goldens snapshot only the rendered report, so NOTHING else covers what this
function prints or writes.  See SPEC section 5.
"""

import json

import pytest

from helpers.dnsfake import recording_console


class FakeSession:
    def __init__(self, close_raises=False):
        self.close_raises = close_raises

    def close(self):
        if self.close_raises:
            raise OSError("connection already dead")


class FakeEngine:
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


def run(psh, monkeypatch, reset_sc, argv, engine=None, session=None, **kwargs):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.options = psh.parse_args(argv)
    psh.finish_run(
        session or FakeSession(),
        engine or FakeEngine(),
        2,                                              # site_count
        2,                                              # emails_sent
        ["its-wws-test1,some-notice,detail"],           # all_warnings
        {"its-wws-test1": {"plan": "Basic"}},           # site_results
        [],                                             # site_savings
        **kwargs,
    )
    return console


@pytest.mark.integration
def test_finish_run_all_writes_the_artifacts(psh, tmp_path, monkeypatch, reset_sc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"])

    assert "its-wws-test1,some-notice,detail" in list(tmp_path.glob("*-notices.csv"))[0].read_text()
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    assert results["its-wws-test1"] == {"plan": "Basic"}
    # The run's outcome must outlive the terminal scrollback (SPEC 3.6).  Names say "this run"
    # because merge_prior_results() makes the FILE describe both runs while _run describes one.
    assert results["_run"] == {
        "aborted_at": None,
        "reason": None,
        "sites_completed_this_run": 1,
        "db_reconnects_this_run": 0,
        "reconnects_by_site": {},
    }


@pytest.mark.integration
def test_finish_run_without_all_prints_to_the_console(psh, tmp_path, monkeypatch, reset_sc):
    # The non---all branch of the epilogue.  No golden covers it; without this test it could be
    # deleted wholesale and the suite would stay green.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    console = run(psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "its-wws-test1"])

    output = console.export_text()
    assert "its-wws-test1,some-notice,detail" in output   # notices printed
    assert "Site savings" in output
    assert list(tmp_path.glob("*-results.json")) == []    # and nothing written


@pytest.mark.integration
def test_finish_run_aborted_does_not_claim_success(psh, tmp_path, monkeypatch, reset_sc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {"its-wws-test2": 3})
    console = run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        aborted_at="its-wws-test2", reason="database",
    )

    output = console.export_text()
    assert "aborting" in output.lower()
    assert "Database reconnects: 3" in output
    results = json.loads(list(tmp_path.glob("*-results.json"))[0].read_text())
    assert results["_run"]["aborted_at"] == "its-wws-test2"
    assert results["_run"]["reason"] == "database"
    assert results["_run"]["reconnects_by_site"] == {"its-wws-test2": 3}


@pytest.mark.integration
def test_finish_run_writes_artifacts_even_if_the_close_fails(psh, tmp_path, monkeypatch, reset_sc):
    # finish_run() is called FROM the abort path, on a session whose DB is by definition sick.  A
    # failing close() must cost neither the artifacts nor the engine dispose() (SPEC 3.3.3).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    engine = FakeEngine()
    run(
        psh, monkeypatch, reset_sc, ["--date", "2026-03-31", "--all"],
        engine=engine, session=FakeSession(close_raises=True),
    )
    assert list(tmp_path.glob("*-results.json")) != []
    assert engine.disposed is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./run-tests tests/integration/test_finish_run.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'finish_run'`

- [ ] **Step 3: Implement**

```python
def finish_run(
    db_session,
    db_engine,
    site_count: int,
    emails_sent: int,
    all_warnings: list,
    site_results: dict,
    site_savings: list,
    *,
    aborted_at: str = None,
    reason: str = None,
) -> None:
    """Close out a run: release the DB, print the totals, write the summary artifacts.

    Called from two places -- normal completion, and abort_run() (SPEC 3.5).  One epilogue with
    two callers is what makes an aborted run's artifacts identical in shape to a completed run's.

    `aborted_at` / `reason` are None on a normal run.  When set, the totals say so instead of
    claiming success, and both are recorded in results.json's `_run` key so the outcome outlives
    the terminal (SPEC 3.6).
    """
    # Two separate try blocks, deliberately: a failing close() must not skip dispose().  The
    # catches are narrow -- (SQLAlchemyError, OSError), not Exception -- so a TypeError from a
    # future edit still crashes loudly.  Neither failure may cost the operator the artifacts:
    # finish_run() is called from the abort path, on a session whose database is already sick
    # (SPEC 3.3.3).
    try:
        db_session.close()
    except (SQLAlchemyError, OSError) as e:
        sc.console.print(f":warning: [yellow]Could not close the database session: {e}")
    try:
        db_engine.dispose()
    except (SQLAlchemyError, OSError) as e:
        sc.console.print(f":warning: [yellow]Could not dispose the database engine: {e}")

    reconnects = sum(db_reconnects_by_site.values())

    if sc.options.all:
        # On a resumed run these two on-disk summaries accumulate across the original and the
        # resumed run instead of being truncated to just the resumed subset.  (The console-only
        # totals printed here and below still cover only this run's sites.)
        resuming = sc.options.resume_from is not None
        if aborted_at is None:
            sc.console.print(
                f"\n[bold green]Email sent for {emails_sent} of {site_count} sites"
                + (f" (resumed from {sc.options.resume_from}).\n" if resuming else ".\n")
            )
        else:
            sc.console.print(
                f"\n[bold yellow]Email sent for {emails_sent} sites before aborting at "
                f"{aborted_at}.\n"
            )
        ymd = datetime.datetime.today().strftime("%Y%m%d")
        with open(f"{ymd}-notices.csv", "a" if resuming else "w", encoding="utf-8") as f:
            for n in all_warnings:
                f.write(n + "\n")

        results_path = f"{ymd}-results.json"
        # On a resumed run, pull the prior payload first so this run's _run can NEST the aborted
        # run's under "previous".  A plain merge would overwrite it -- and the aborted run's block
        # is the one carrying the reconnect evidence that prompted the resume in the first place.
        prior = merge_prior_results(results_path, {}) if resuming else {}
        # "this_run" in the names, not "processed": merge_prior_results() makes the FILE describe
        # the original run plus this one, while these numbers describe only this one.  (An
        # --only-warn run emails nobody, so this counts sites processed, not sites emailed.)
        run_meta = {
            "aborted_at": aborted_at,
            "reason": reason,
            "sites_completed_this_run": len(site_results),
            "db_reconnects_this_run": reconnects,
            "reconnects_by_site": dict(db_reconnects_by_site),
        }
        if "_run" in prior:
            run_meta["previous"] = prior["_run"]
        site_results["_run"] = run_meta
        # merge_prior_results() again rather than a hand-rolled {**prior, **site_results}: it owns
        # the "new wins" rule AND the malformed-prior-file handling, and that logic must live in
        # one place.  It re-reads the file; a second read of a small JSON file at the very end of
        # a multi-hour run is not worth duplicating the semantics to avoid.
        payload = (
            merge_prior_results(results_path, site_results) if resuming else site_results
        )
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
    else:
        for n in all_warnings:
            sc.console.print(n)
        pprint(site_results)

    sc.console.print(f"\n[bold green]Site savings:\n")
    pprint(site_savings)
    sc.console.print(f"Sites with savings: {len(site_savings)}")
    sc.console.print(
        f"Total savings: ${sum([s['savings'] for s in site_savings]):,.2f}"
    )
    sc.console.print(f"Database reconnects: {reconnects}")

    sc.debug("Done!")
```

`sites_completed_this_run` is `len(site_results)` **before** `_run` is inserted — the assignment
statement evaluates its right-hand side first, so the count excludes the metadata key. Write it
exactly as shown. (`abort_run()` has already popped the failed site by the time this runs — Task 6.)

Replace `:3932`–`:3967` in `main()` with a call:

```python
    finish_run(
        db_session,
        db_engine,
        site_count,
        emails_sent,
        all_warnings,
        site_results,
        site_savings,
    )
```

- [ ] **Step 4: Run the tests**

Run: `./run-tests --fast` → all pass (incl. 4 new `test_finish_run.py` tests), zero golden diffs.

- [ ] **Step 5: Commit**

```bash
git add pantheon-sitehealth-emails tests/integration/test_finish_run.py
git commit -m "refactor: extract finish_run() from the tail of main()

One epilogue, about to have two callers: normal completion and the abort handler.  Adds the run's
reconnect count to the console and a _run key to results.json, so an operator reading the
artifacts tomorrow can tell a clean run from one that died at site X after 200 reconnects.

The e2e goldens snapshot only the rendered report, so tests/integration/test_finish_run.py is the
only cover this code has -- including its non---all console branch."
```

---

### Task 6: The abort path

**Files:**
- Modify: `pantheon-sitehealth-emails` — add `resume_point()`, `resume_command()`,
  `rerun_command()`, `abort_run()`; wrap the site loop (`:1387`); track the send inside the loop
- Test: `tests/unit/test_db_resilience.py` (extend), `tests/integration/test_abort_run.py` (create),
  `tests/e2e/test_abort_e2e.py` (create), `tests/shims/dbshim/sitecustomize.py` (create)

**Interfaces:**
- Consumes: `DatabaseUnavailableError` (Task 2), `finish_run()` (Task 5), `sites_from_resume_point()`
  (existing, `:1117-1135`), `build_arg_parser()` (existing, `:150`).
- Produces:
  - `resume_point(site_names: list, site_name: str, emailed: bool) -> str` — pure; the aborting
    site, or the **next** one when its report was already emailed, or `None` when nothing remains.
  - `resume_command(argv: list, site_name: str) -> str` — pure; for `--all` runs.
  - `rerun_command(argv: list, original_sites: list, remaining_sites: list) -> str` — pure; for
    explicit-`SITE` runs. **Never emits `--resume-from`** (it requires `--all`, `:1238`).
  - `abort_run(db_session, db_engine, site_name, reason, error, *, emailed, site_names, site_count,
    emails_sent, all_warnings, site_results, site_savings) -> None` — never returns; exits 1
    (`"database"`) or 130 (`"interrupted"`).

- [ ] **Step 1: Write the failing unit tests**

```python
# tests/unit/test_db_resilience.py  (append)


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
    # --resume-from requires --all (pantheon-sitehealth-emails:1238), so printing it after an
    # explicit-SITE run would hand the operator a command that exits with an error (SPEC 3.5.1).
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
```

- [ ] **Step 2: Write the failing integration tests**

```python
# tests/integration/test_abort_run.py
"""The abort path: flush the artifacts, drop the failed site, print a RUNNABLE command, exit
nonzero.  In-process, because the subprocess safety interlock bans --all (CLAUDE.md).

See development/2026-07-13-db-connection-resilience/SPEC.md sections 3.5.1-3.5.4.
"""

import signal

import pytest

from helpers.dnsfake import recording_console

SITE_NAMES = ["its-wws-test1", "its-wws-test2", "its-wws-test3"]


class FakeSession:
    def rollback(self):
        pass

    def close(self):
        pass


class FakeEngine:
    def dispose(self):
        pass


def abort(psh, monkeypatch, reset_sc, argv, reason, error, *, emailed=False, site_results=None):
    console = recording_console(monkeypatch, reset_sc)
    reset_sc.options = psh.parse_args(argv[1:])
    monkeypatch.setattr(psh.sys, "argv", argv)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})

    # abort_run() sets SIGINT to SIG_IGN, which is PROCESS-GLOBAL and restored by no fixture:
    # without this patch, the rest of the pytest session would silently ignore Ctrl-C
    # (SPEC 5, harness rule 2).
    signals_set = []
    monkeypatch.setattr(psh.signal, "signal", lambda sig, handler: signals_set.append((sig, handler)))

    captured = {}

    def fake_finish_run(_session, _engine, _site_count, _emails_sent, _warnings, results, *_a, **kw):
        captured.update(kw)
        captured["site_results"] = results
        captured["ran"] = True

    monkeypatch.setattr(psh, "finish_run", fake_finish_run)
    with pytest.raises(SystemExit) as excinfo:
        psh.abort_run(
            FakeSession(), FakeEngine(), "its-wws-test2", reason, error,
            emailed=emailed, site_names=SITE_NAMES,
            site_count=10, emails_sent=4, all_warnings=[],
            site_results=site_results if site_results is not None else {},
            site_savings=[],
        )
    assert (signal.SIGINT, signal.SIG_IGN) in signals_set  # the flush is protected
    return console, captured, excinfo.value.code


@pytest.mark.integration
def test_database_abort_flushes_and_prints_a_resume_command(psh, monkeypatch, reset_sc):
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all", "--only-warn"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database",
        psh.DatabaseUnavailableError("loading traffic rows: (2013, 'Lost connection')"),
    )
    assert code == 1
    assert captured["ran"] is True                  # artifacts flushed BEFORE exiting
    assert captured["aborted_at"] == "its-wws-test2"
    output = console.export_text()
    assert "--resume-from its-wws-test2" in output
    assert "--only-warn" in output                  # the run's real flags survive (SPEC 3.5.1)


@pytest.mark.integration
def test_abort_drops_the_failed_site_from_the_results(psh, monkeypatch, reset_sc):
    # site_results[site] is written DURING the gather (:1833 / :2152), long before the crash --
    # so without this pop, results.json would ship the failed site as though it had succeeded,
    # with no matching notices (SPEC 3.5.2).
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    _console, captured, _code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
        site_results={
            "its-wws-test1": {"framework": "wordpress"},
            "its-wws-test2": {"framework": "wordpress"},  # the site that died
        },
    )
    assert list(captured["site_results"].keys()) == ["its-wws-test1"]


@pytest.mark.integration
def test_ctrl_c_flushes_artifacts_and_exits_130(psh, monkeypatch, reset_sc):
    # Prime Directive #7: a run is not atomic.  Before this, Ctrl-C at hour two lost every
    # artifact of the run -- while a DB failure at hour two kept them.
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
    )
    assert code == 130                             # conventional SIGINT exit code
    assert captured["ran"] is True
    assert "--resume-from its-wws-test2" in console.export_text()


@pytest.mark.integration
def test_ctrl_c_after_the_email_was_sent_resumes_at_the_next_site(psh, monkeypatch, reset_sc):
    # The report for its-wws-test2 was already DELIVERED when the interrupt landed.  Resuming
    # there (--resume-from is inclusive) would send that owner a second copy of the same monthly
    # report -- a silent, outward-facing failure.  Resume at the next site instead, and KEEP the
    # site's results entry, because it really did complete (SPEC 3.5.3).
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "--all"]
    console, captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
        emailed=True,
        site_results={"its-wws-test2": {"framework": "wordpress"}},
    )
    assert code == 130
    assert "--resume-from its-wws-test3" in console.export_text()   # the NEXT site
    assert "its-wws-test2" in captured["site_results"]              # entry kept, not popped


@pytest.mark.integration
def test_explicit_site_abort_prints_a_rerun_command_not_resume_from(psh, monkeypatch, reset_sc):
    argv = [
        "./pantheon-sitehealth-emails", "--date", "2026-03-31",
        "its-wws-test1", "its-wws-test2", "its-wws-test3",
    ]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "database", psh.DatabaseUnavailableError("boom"),
    )
    assert code == 1
    output = console.export_text()
    assert "--resume-from" not in output           # it requires --all; would fail when pasted
    assert "its-wws-test2 its-wws-test3" in output # the sites not yet processed


@pytest.mark.integration
def test_abort_on_an_unrequested_site_does_not_crash(psh, monkeypatch, reset_sc):
    # A non---all run iterates EVERY org site and `continue`s the unrequested ones (:1402), so a
    # Ctrl-C can land on a site the operator never asked for.  Slicing the requested list at that
    # name would raise ResumeSiteNotFoundError -- inside the abort handler, after SIGINT was
    # ignored and the artifacts were flushed.  The operator would get a traceback instead of a
    # command (SPEC 3.5.4).
    argv = ["./pantheon-sitehealth-emails", "--date", "2026-03-31", "its-wws-test9"]
    console, _captured, code = abort(
        psh, monkeypatch, reset_sc, argv, "interrupted", KeyboardInterrupt(),
    )
    assert code == 130
    assert "Traceback" not in console.export_text()
    assert "its-wws-test9" in console.export_text()  # re-run what was actually requested
```

- [ ] **Step 3: Write the failing e2e test and its shim**

`tests/shims/dbshim/sitecustomize.py`:

```python
"""Make the traffic DB fail inside a subprocess run, for tests/e2e/test_abort_e2e.py.

Python auto-imports sitecustomize at interpreter startup, before the program imports anything --
the same trick tests/shims/dnsshim uses to replace dns.resolver.resolve.  Active only when
DB_SHIM_FAIL is set, so putting this directory on PYTHONPATH is otherwise inert (it is inherited
by the PATH-based fake `terminus`, which is a Python script too).

Session.get() is the seam: sessionmaker builds a runtime SUBCLASS of Session and does not override
get(), so patching the base class here reaches the program's session.  Note the first call to fire
is inside update_traffic_rows()' session.merge() -- SQLAlchemy's Session._merge() calls self.get()
for a persistent key that is not in the identity map -- not build_traffic_table_rows() as one might
assume.  Either way the failure lands INSIDE a db_retry() unit, which is what the test asserts.
"""

import os

if os.environ.get("DB_SHIM_FAIL"):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    def _dead_get(self, *args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("(2013, 'Lost connection')"))

    Session.get = _dead_get
```

```python
# tests/e2e/test_abort_e2e.py
"""The ONLY test that proves main() actually wraps the site loop in try:, catches a database
failure, runs the epilogue, and prints a command to continue.  `git diff -w` is an eyeball check;
this is a test.

A subprocess run cannot be reached by an in-process monkeypatch, so -- exactly as the DNS tests do
with tests/shims/dnsshim -- tests/shims/dbshim goes on PYTHONPATH via run_program(extra_env=...)
and patches sqlalchemy.orm.Session.get to raise OperationalError.  Single site: the safety
interlock bans --all (CLAUDE.md).
"""
import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    SHIMS_DIR,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e


def test_database_failure_aborts_the_run_and_prints_a_rerun_command(tmp_path):
    work = make_workdir(tmp_path)
    run_program(["--create-tables", "--config", str(MINIMAL_CONFIG)], cwd=work)
    seed_traffic(work / "database.db")

    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(MINIMAL_CONFIG)],
        cwd=work,
        extra_env={
            "PYTHONPATH": str(SHIMS_DIR / "dbshim"),
            "DB_SHIM_FAIL": "1",
        },
    )

    # The retry ran once, gave up, and the run aborted through the named path -- not a traceback.
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert "Database reconnects: 1" in proc.stdout   # db_retry retried, then raised
    assert E2E_SITE in proc.stdout
    # A single-site run gets a re-run command, never --resume-from (which requires --all).
    assert "--resume-from" not in proc.stdout
    assert "Continue this run with" in proc.stdout
```

> **Harness contract (verified — follow it exactly).** `run_program` is **imported from
> `conftest`**, not requested as a fixture, and its signature is `run_program(args, *, cwd,
> mode="replay", extra_env=None, timeout=300, fixtures_dir=None)`. `cwd` is **required** — without
> `make_workdir()` the subprocess inherits the repo CWD and the **production config symlink**.
> `extra_env` already prepends `PYTHONPATH` correctly (`conftest.py:429-435`). `run_program` never
> raises on a nonzero exit, so no `check=` argument is needed or accepted. If `SHIMS_DIR` is not
> already exported from `conftest.py`, add it next to the existing shim constants rather than
> hardcoding the path here — and say so in the commit message.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `./run-tests tests/unit/test_db_resilience.py tests/integration/test_abort_run.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'resume_point'`

- [ ] **Step 5: Implement the three pure helpers**

```python
def resume_point(site_names: list, site_name: str, emailed: bool) -> str:
    """Where a resumed run must start.

    Normally the aborting site itself: --resume-from is inclusive, so it is redone from the top.
    But if the interrupt landed AFTER that site's report was emailed, restarting there would send
    its owner a SECOND copy of the same monthly report, so the resume point is the next site.
    Returns None when the emailed site was the last one (nothing remains).  See SPEC 3.5.3.
    """
    if not emailed:
        return site_name
    i = site_names.index(site_name)
    return site_names[i + 1] if i + 1 < len(site_names) else None


def option_strings_taking_a_value() -> set:
    """Every option string that consumes a following argument, derived from the parser itself.

    Derived rather than hardcoded: a hardcoded list rots the first time an option is added, and
    rerun_command() would then mistake that option's VALUE for a site name and delete it.  Same
    denylist-by-omission failure that SPEC 3.5.1 exists to prevent.
    """
    return {
        opt
        for action in build_arg_parser()._actions
        if action.option_strings and action.nargs != 0
        for opt in action.option_strings
    }


def resume_command(argv: list, site_name: str) -> str:
    """Rebuild an --all invocation with --resume-from <site_name>.

    Built from argv rather than from sc.options on purpose.  Re-enumerating flags would be a
    denylist by omission -- the first flag added next year would silently vanish from the hint, and
    an operator pasting the command would get a run that does something DIFFERENT from the one that
    died (e.g. a full report-and-send instead of an --import-older-metrics backfill).
    allow_abbrev=False guarantees only these two spellings exist.  See SPEC 3.5.1.
    """
    args = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg == "--resume-from":
            skip_next = True  # drop its value too
            continue
        if arg.startswith("--resume-from="):
            continue
        args.append(arg)
    return shlex.join(args + ["--resume-from", site_name])


def rerun_command(argv: list, original_sites: list, remaining_sites: list) -> str:
    """Rebuild an explicit-SITE invocation with only the sites that were not processed.

    NOT --resume-from: that flag requires --all (main() exits otherwise), so printing it here would
    hand the operator a command that fails the moment they paste it.

    Only POSITIONAL site names are dropped.  A site name sitting in an option's value slot
    (`-c its-wws-test1`) must survive, or `-c` swallows the next token and the command is mangled.
    See SPEC 3.5.1.
    """
    value_opts = option_strings_taking_a_value()
    args = []
    previous = None
    for arg in argv:
        is_option_value = previous in value_opts
        if not is_option_value and arg in original_sites:
            previous = arg
            continue  # a site positional: dropped here, re-appended below if still pending
        args.append(arg)
        previous = arg
    return shlex.join(args + list(remaining_sites))
```

- [ ] **Step 6: Implement `abort_run()`**

```python
def abort_run(
    db_session,
    db_engine,
    site_name: str,
    reason: str,
    error: BaseException,
    *,
    emailed: bool,
    site_names: list,
    site_count: int,
    emails_sent: int,
    all_warnings: list,
    site_results: dict,
    site_savings: list,
) -> None:
    """Report an aborted run, flush its artifacts, print how to finish it, and exit.  Never returns.

    `reason` is "database" (exit 1) or "interrupted" (exit 130, the conventional SIGINT code).
    `emailed` says whether the aborting site's report was already sent (only ever True for an
    interrupt; the database abort fires long before the send).

    This function runs when things are ALREADY broken, so it must not be able to crash: every input
    it slices on is guarded (SPEC 3.5.4).
    """
    # A second Ctrl-C must not truncate the flush -- losing the artifacts is exactly the failure
    # this function exists to prevent.  The flush is sub-second (SPEC 3.5).
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        db_session.rollback()
    except (SQLAlchemyError, OSError) as e:  # the database is already sick; see finish_run()
        sc.console.print(f":warning: [yellow]Could not roll back the database session: {e}")

    if emailed:
        # The site completed -- its report went out.  Keep its results entry.
        pass
    else:
        # site_results[site] is written DURING the gather (:1833 WordPress, :2152 Drupal), ~1400
        # lines before the failure point -- so the aborting site is already in there, while its
        # notices (appended at :3922, at the END of a successful site) are not.  Drop it, so the
        # artifacts contain exactly the sites that completed end-to-end.  --resume-from is
        # inclusive, so the resumed run redoes this site and rewrites the entry.  See SPEC 3.5.2.
        site_results.pop(site_name, None)

    if reason == "database":
        sc.console.print(
            f"\n:exclamation: [bold red]FATAL: a database operation failed and could not be "
            f"retried.  Aborting while processing [bold]{site_name}[/bold]:\n{error}"
        )
    else:
        sc.console.print(
            f"\n:hand: [bold yellow]Interrupted while processing [bold]{site_name}[/bold]."
            + (
                "  Its report had already been sent, so resuming will start at the next site."
                if emailed
                else ""
            )
        )

    finish_run(
        db_session,
        db_engine,
        site_count,
        emails_sent,
        all_warnings,
        site_results,
        site_savings,
        aborted_at=site_name,
        reason=reason,
    )

    # Everything below is guarded: an interrupt can land before the first site's body runs
    # (site_name is None), or -- on a non---all run, which iterates every org site and `continue`s
    # the ones it was not asked for (:1402) -- on a site the operator never requested.  Slicing on
    # either would raise INSIDE this handler, after SIGINT was ignored and the artifacts were
    # written, and the operator would get a traceback instead of a command.  See SPEC 3.5.4.
    resume_site = (
        resume_point(site_names, site_name, emailed)
        if site_name in site_names
        else None
    )

    if resume_site is None and emailed:
        sc.console.print("\n[bold]Every site was processed; nothing remains to resume.\n")
    elif sc.options.all:
        command = (
            resume_command(sys.argv, resume_site)
            if resume_site is not None
            else shlex.join(sys.argv)  # nothing to skip: re-run as invoked
        )
        sc.console.print(
            f"\n[bold]The sites before {resume_site or site_name} were processed and their "
            "results written.  Continue this run with:\n\n"
            f"    {command}\n"
        )
    else:
        # --resume-from requires --all, so an explicit-SITE run gets a re-run command listing the
        # sites it never reached.  sites_from_resume_point() is the same inclusive-slice helper the
        # --resume-from path uses, reused here rather than reimplemented -- but only when the
        # aborting site is one the operator actually asked for.
        requested = sorted(sc.options.sites)
        remaining = (
            sites_from_resume_point(requested, resume_site)
            if resume_site in requested
            else requested
        )
        sc.console.print(
            "\n[bold]Continue this run with:\n\n"
            f"    {rerun_command(sys.argv, sc.options.sites, remaining)}\n"
        )

    sys.exit(1 if reason == "database" else 130)
```

- [ ] **Step 7: Wrap the site loop and track the send**

Two edits inside the loop, then the wrapper. First, in the loop body, record whether this site's
report went out — this is the **only** semantic change inside the re-indented block, and a reviewer
reading `git diff -w` should expect exactly these two lines:

```python
    for site_name in site_names:
        site_emailed = False          # <-- ADD as the first statement of the loop body
        ...
        if smtp_enabled:
            smtp_connection = smtp_login()
            smtp_connection.send_message(msg)
            emails_sent += 1
            site_emailed = True       # <-- ADD immediately after emails_sent += 1  (:3919)
            smtp_connection.quit()
```

Then wrap the `for site_name in site_names:` loop (`:1387`) in a `try:`, re-indenting its body by
four spaces. **Do this mechanically** — no other edit may ride along:

```python
    site_name = None
    site_emailed = False
    try:
        for site_name in site_names:
            ...  # the existing loop body, re-indented by four spaces, plus the two lines above
    except (DatabaseUnavailableError, OperationalError) as e:
        # OperationalError as well as the named error: a database failure raised OUTSIDE a unit of
        # work (a future code path, an expired-row lazy load) must still land on the named abort
        # path with the artifacts flushed, rather than as a bare traceback (SPEC 3.3.3).
        abort_run(
            db_session, db_engine, site_name, "database", e,
            emailed=False,  # the DB abort fires at :3280, long before the send
            site_names=site_names, site_count=site_count, emails_sent=emails_sent,
            all_warnings=all_warnings, site_results=site_results, site_savings=site_savings,
        )
    except KeyboardInterrupt as e:
        abort_run(
            db_session, db_engine, site_name, "interrupted", e,
            emailed=site_emailed,
            site_names=site_names, site_count=site_count, emails_sent=emails_sent,
            all_warnings=all_warnings, site_results=site_results, site_savings=site_savings,
        )
```

- [ ] **Step 8: Prove the re-indent is whitespace-only**

Run: `git diff -w -- pantheon-sitehealth-emails`
Expected: the `try:` / `except` / `abort_run(...)` lines, the two `site_emailed` lines from Step 7,
and **nothing else** from the loop body. Anything more means a semantic edit rode along — revert and
redo the re-indent.

- [ ] **Step 9: Run the tests**

Run: `./run-tests --fast`
Expected: all pass — including `tests/e2e/test_abort_e2e.py`, which is what proves the wrapper is
really there — and **zero golden diffs**.

- [ ] **Step 10: Commit**

```bash
git add pantheon-sitehealth-emails tests/unit/test_db_resilience.py \
        tests/integration/test_abort_run.py tests/e2e/test_abort_e2e.py tests/shims/dbshim
git commit -m "feat(db): flush artifacts and print a runnable command on abort

A database failure that survives the retry -- and now also a Ctrl-C -- used to kill an --all run
outright, losing an hour of completed work.  Both now write notices.csv and results.json for the
sites that completed, print the exact command to continue, and exit 1 / 130.

The command is rebuilt from sys.argv, so it cannot silently drop --config, --update,
--import-older-metrics or --only-warn, and it never strips a site name out of an option's value
slot.  An explicit-SITE run gets a re-run command instead of --resume-from, which requires --all
and would fail when pasted.  The aborting site is dropped from site_results (written mid-gather,
it would otherwise ship as a success) UNLESS its report was already emailed -- in which case
resuming starts at the next site, so no owner gets a duplicate report.

The site loop body is re-indented into a try: block; git diff -w shows only the two site_emailed
lines, and tests/e2e/test_abort_e2e.py exercises the wrapper through the real main()."
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md` — the **Database** section, the `site_post_traffic` row of the data-contract
  table, and the **Testing** section (the new shim)
- Modify: `docs/resuming-interrupted-runs.md`

- [ ] **Step 1: Update the data-contract table in `CLAUDE.md`**

`traffic_rows` is now `list[TrafficRow]` — plain `NamedTuple` data with the same attribute names as
the ORM model (`.site_id`, `.traffic_date`, `.site_plan`, `.visits`, `.pages_served`,
`.cache_hits`), **not** live ORM rows. Say why: a `db_retry` rollback expires live ORM objects, so
a hook holding one would emit an unretried SELECT on the next attribute read.

- [ ] **Step 2: Append to `CLAUDE.md`'s Database section**

```markdown
**Connection resilience.** The DB is remote (RDS) and the path crosses NAT/firewall middleboxes
that reap idle flows, so the engine sets `pool_pre_ping=True` / `pool_recycle=1800` (MySQL only;
sqlite kwargs stay `{}`) and the sessionmaker sets `expire_on_commit=False`. The load-bearing piece
is `load_traffic_rows()`'s **commit after a read-only SELECT**: it releases the connection before
the multi-minute per-site gather, without which the session holds an idle in-transaction connection
that gets reaped and dies at the next query with MySQL error 2013 — **do not remove it**
(`test_load_traffic_rows_releases_the_connection` guards it). It returns plain `TrafficRow` data,
not ORM rows, because a rollback expires live ORM objects and a later read would emit an unretried
SELECT. DB work runs through `db_retry(session, unit, what=…, site=…)`, which retries **whole
idempotent units of work** (`update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`,
`build_traffic_table_rows`) and NEVER a statement with pending writes — a rollback discards them,
so a statement-level retry would commit a partial write set. It catches `OperationalError` only
(every flavor alike — no error-code sniffing). On a second failure it raises
`DatabaseUnavailableError`; that (and a `KeyboardInterrupt`) is caught once around the site loop,
where `abort_run()` drops the failed site from `site_results` (it is written mid-gather, so it
would otherwise ship as a success), flushes the artifacts via `finish_run()`, prints a command
rebuilt from `sys.argv` (`--resume-from` for `--all`; a re-run command listing the remaining sites
otherwise, since `--resume-from` requires `--all`), and exits 1 (database) or 130 (Ctrl-C). **A
Ctrl-C that lands after a site's report was already sent resumes at the NEXT site** and keeps that
site's results entry — resuming inclusively would mail its owner a duplicate report.
`finish_run()` also writes a `_run` key into `-results.json` (`aborted_at`, `reason`,
`sites_completed_this_run`, `db_reconnects_this_run`, `reconnects_by_site`, and on a resumed run
the prior run's block under `previous`). **The e2e goldens cover neither stdout nor the
artifacts**, so `tests/integration/test_finish_run.py`, `tests/integration/test_abort_run.py`, and
`tests/e2e/test_abort_e2e.py` (which drives a DB failure through the real `main()` via
`tests/shims/dbshim`) are the only cover for that code. Note `abort_run()` sets SIGINT to
`SIG_IGN` so a second Ctrl-C cannot truncate the flush — an in-process test that calls it **must**
`monkeypatch.setattr(psh.signal, "signal", …)`, or the rest of the pytest session silently ignores
Ctrl-C. See `development/2026-07-13-db-connection-resilience/SPEC.md`.
```

- [ ] **Step 3: Note the new shim in `CLAUDE.md`'s Testing section**

Next to the `tests/shims/dnsshim` note: `tests/shims/dbshim/sitecustomize.py` is its counterpart
for the database — on `PYTHONPATH` it patches `sqlalchemy.orm.Session.get` to raise
`OperationalError` when `DB_SHIM_FAIL` is set, which is how the subprocess e2e run exercises the
abort path.

- [ ] **Step 4: Cross-reference from the resume doc**

Add to `docs/resuming-interrupted-runs.md`: an unrecoverable database error — or a Ctrl-C — now
aborts the run deliberately, writes the artifacts for the sites that completed, drops the site it
died on, and prints the exact command to continue (rebuilt from the original invocation, so it
carries the same flags).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/resuming-interrupted-runs.md
git commit -m "docs: record the DB connection-resilience invariant and the TrafficRow contract"
```

---

## Final verification (SPEC §6)

Run each command and paste the **real output** into the final commit or PR — never a summary.

```bash
./run-tests --fast                                    # all pass; zero golden diffs
./run-tests                                           # all pass, incl. the live tier
git diff -w main -- pantheon-sitehealth-emails        # no stray semantic change in the loop
./pantheon-sitehealth-emails --date 20240731 its-wws-test1   # completes; reconnects: 0
./pantheon-sitehealth-emails --date 20240731 --all     # Ctrl-C mid-run: exit 130, artifacts
                                                       # written, printed command runs verbatim
```

**Then say the honest thing:** until a real `--all` run survives past the point where the last three
died, this fix is *plausible, not verified*. The tests prove the mechanism; only production proves
the middlebox.

## Reviewer concerns carried forward (not fixed, deliberately)

Both are recorded rather than closed, per Prime Directive #9:

1. **The SIG_IGN window.** `abort_run()` ignores SIGINT *from its first line*, so a second Ctrl-C
   in the microseconds between the `KeyboardInterrupt` being raised and the handler being entered
   can still truncate the flush. Closing it would mean an interrupt-safe signal handler installed
   for the whole run — disproportionate to the risk.
2. **The notices window** (SPEC §3.5.3): a Ctrl-C in the 6 lines between `emails_sent += 1`
   (`:3919`) and `all_warnings.append(...)` (`:3925`) keeps that site's results entry and its sent
   email but loses its notices from `-notices.csv`. A transaction around six lines is not worth it.
