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
