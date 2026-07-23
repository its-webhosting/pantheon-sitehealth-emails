"""open_database seam (campaign I13, SPEC 2.6 -- every DB touch now in psh/db.py)."""
import pytest

from psh.db import open_database


@pytest.mark.integration
def test_open_database_builds_engine_and_session(tmp_path):
    engine, session = open_database({"type": "sqlite", "name": str(tmp_path / "t.db")})
    try:
        assert engine.echo is not True
        # REQUIRED, not tuning (SPEC 2.6): load_traffic_rows commits to release the
        # connection; with expiry on, that commit would silently re-SELECT every row.
        assert session.expire_on_commit is False
        assert session.get_bind() is engine
    finally:
        session.close()
        engine.dispose()


@pytest.mark.integration
def test_open_database_echo_flag(tmp_path):
    engine, session = open_database({"type": "sqlite", "name": str(tmp_path / "t.db")}, echo=True)
    try:
        assert engine.echo is True
    finally:
        session.close()
        engine.dispose()
