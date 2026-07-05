"""Integration tests for the SQLAlchemy models against a temp sqlite DB (test-suite SPEC §7.3).

Covers the upsert/merge semantics main() relies on and the unique key that protects a
(site_id, date/month) from duplicating.
"""
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from conftest import E2E_SITE_ID

pytestmark = pytest.mark.integration

DAY = datetime.date(2026, 3, 15)
MONTH = datetime.date(2026, 3, 1)


def _traffic(temp_db, visits):
    return temp_db.PantheonTraffic(
        site_id=E2E_SITE_ID,
        traffic_date=DAY,
        site_plan="Performance Small",
        visits=visits,
        pages_served=visits * 3,
        cache_hits=visits * 2,
    )


def test_traffic_merge_is_idempotent_upsert(temp_db):
    session = temp_db.session()
    session.merge(_traffic(temp_db, 1000))
    session.commit()
    session.merge(_traffic(temp_db, 2000))  # same PK (site_id, traffic_date) -> update, not insert
    session.commit()
    rows = session.query(temp_db.PantheonTraffic).all()
    assert len(rows) == 1
    assert rows[0].visits == 2000
    session.close()


def test_traffic_duplicate_insert_violates_unique_key(temp_db):
    session = temp_db.session()
    session.add(_traffic(temp_db, 10))
    session.commit()
    session.add(_traffic(temp_db, 20))  # duplicate (site_id, traffic_date)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_overage_protection_get_add_update(temp_db):
    session = temp_db.session()
    key = {"site_id": E2E_SITE_ID, "month": MONTH}

    assert session.get(temp_db.PantheonOverageProtection, key) is None
    session.add(
        temp_db.PantheonOverageProtection(
            site_id=E2E_SITE_ID, month=MONTH, months_remaining=4, used_this_month=False
        )
    )
    session.commit()

    op = session.get(temp_db.PantheonOverageProtection, key)
    assert op is not None and op.months_remaining == 4 and op.used_this_month is False

    op.months_remaining = 3
    op.used_this_month = True
    session.commit()

    refetched = session.get(temp_db.PantheonOverageProtection, key)
    assert refetched.months_remaining == 3 and refetched.used_this_month is True
    session.close()
