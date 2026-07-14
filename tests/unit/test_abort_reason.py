"""Unit tests for abort_reason(), the pure classifier main() uses to pick how an exception
escaping the site loop is handled: "database" (exit 1), "interrupted" (exit 130), or "fatal"
(re-raise).  Extracted so it is testable at all -- main() cannot be called in-process, and the
subprocess safety interlock bans --all, so nothing else exercises this branch.

See development/2026-07-13-db-connection-resilience/SPEC.md.
"""

import pytest
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError

pytestmark = pytest.mark.unit


def _op_error():
    return OperationalError("SELECT 1", {}, Exception("(2013, 'Lost connection')"))


@pytest.mark.unit
def test_database_unavailable_error_is_database(psh):
    assert psh.abort_reason(psh.DatabaseUnavailableError("boom")) == "database"


@pytest.mark.unit
def test_operational_error_is_database(psh):
    # A deadlock or lock-wait timeout: connection_invalidated is False, but db_retryable() still
    # calls it retryable, so it must still land on the database abort path.
    assert psh.abort_reason(_op_error()) == "database"


@pytest.mark.unit
def test_invalidated_non_operational_dbapi_error_is_database(psh):
    # A reaped connection can arrive as InterfaceError (errno 0), a SIBLING of OperationalError,
    # not a subclass. db_retryable() catches it via connection_invalidated; abort_reason() must
    # reuse that same predicate rather than re-listing exception classes.
    error = InterfaceError("SELECT 1", {}, Exception("(0, '')"), connection_invalidated=True)
    assert psh.abort_reason(error) == "database"


@pytest.mark.unit
def test_integrity_error_is_fatal(psh):
    # A genuine data bug, not a network blip: NOT retryable, so NOT a database abort -- it must
    # keep its traceback on the fatal path.
    error = IntegrityError("INSERT", {}, Exception("duplicate key"))
    assert psh.abort_reason(error) == "fatal"


@pytest.mark.unit
def test_keyboard_interrupt_is_interrupted(psh):
    assert psh.abort_reason(KeyboardInterrupt()) == "interrupted"


@pytest.mark.unit
def test_system_exit_is_fatal(psh):
    assert psh.abort_reason(SystemExit("Bailing out.")) == "fatal"


@pytest.mark.unit
def test_plain_runtime_error_is_fatal(psh):
    assert psh.abort_reason(RuntimeError("the php inliner died")) == "fatal"
