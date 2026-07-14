"""The abort handler prints the underlying database error.  It must never render the connection
URL, which embeds the DB password.  See SPEC section 3.8.
"""

import pytest
import sqlalchemy as db

# create_engine("mysql+mysqldb://...") imports the DBAPI EAGERLY, so on a sqlite-only install
# (the [mysql] extra is optional and CLAUDE.md's setup line sanctions dropping it) that line
# raises ModuleNotFoundError OUTSIDE the pytest.raises block below -- a hard ERROR in the
# documented offline inner loop (`./run-tests --fast`), unrelated to whatever the contributor
# changed.  Skip cleanly instead.
pytest.importorskip(
    "MySQLdb", reason="needs the optional [mysql] extra: the leak test drives a real MySQL engine"
)


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
    # The UNREDACTED URL: str(engine.url) is render_as_string(hide_password=True), i.e.
    # "mysql+mysqldb://dbuser:***@..." -- a string no credential leak could ever produce, so
    # asserting on it passed no matter what the message said.  hide_password=False is the string a
    # leak WOULD produce.
    unredacted = engine.url.render_as_string(hide_password=False)
    assert "hunter2" in unredacted, "guard: the URL under test must actually carry the password"
    # Assert on the password and the whole URL -- NOT merely on the host: MySQLdb's own 2003
    # error text contains "127.0.0.1", so a host-only assertion would pass for the wrong reason.
    assert "hunter2" not in message
    assert unredacted not in message
