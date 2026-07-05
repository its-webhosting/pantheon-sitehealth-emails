"""Integration tests for plugin/umich/portal.py (test-suite SPEC §7.4).

No live MySQL: a temp SQLite DB stands in for the portal database (portal.py reflects the
tables with autoload_with, which works against SQLite), and db.create_engine is monkeypatched
to hand back that engine.  Asserts the runtime plan_sku_to_name override, site loading, and the
nested setup.umich.portal hook ordering.
"""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
import sqlalchemy as db

pytestmark = pytest.mark.integration


def _build_portal_db(path):
    engine = db.create_engine(f"sqlite:///{path}")
    md = db.MetaData()
    sites_site = db.Table(
        "sites_site", md,
        db.Column("id", db.Integer, primary_key=True),
        db.Column("site_slug", db.String),
        db.Column("owner_group", db.String),
        db.Column("shortcode", db.String),
    )
    sites_pantheonplan = db.Table(
        "sites_pantheonplan", md,
        db.Column("id", db.Integer, primary_key=True),
        db.Column("portal_plan_name", db.String),
        db.Column("pantheon_plan_sku", db.String),
        db.Column("traffic_limits", db.Integer),
        db.Column("annual_plan_customer_charge", db.Integer),
        db.Column("is_active", db.Boolean),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sites_site.insert(), [
            {"id": 101, "site_slug": "its-wws-test1", "owner_group": "grp1", "shortcode": "T1"},
            {"id": 102, "site_slug": "its-wws-test2", "owner_group": "grp2", "shortcode": "T2"},
        ])
        conn.execute(sites_pantheonplan.insert(), [
            {"portal_plan_name": "Performance Small", "pantheon_plan_sku": "plan-perf-small",
             "traffic_limits": 35000, "annual_plan_customer_charge": 1925, "is_active": True},
            {"portal_plan_name": "Legacy", "pantheon_plan_sku": "plan-legacy",
             "traffic_limits": 5000, "annual_plan_customer_charge": 100, "is_active": False},
        ])
    return engine


@pytest.fixture
def portal_module(psh):
    path = Path(psh.__file__).parent / "plugin" / "umich" / "portal.py"
    loader = SourceFileLoader("umich_portal_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_setup_portal_db_overrides_config_and_populates(portal_module, reset_sc, tmp_path, monkeypatch):
    sc = reset_sc
    engine = _build_portal_db(tmp_path / "portal.db")
    monkeypatch.setattr(portal_module.db, "create_engine", lambda *a, **k: engine)

    sc.config = {
        "UMich": {"portal": {"db": {"user": "u", "password": "p", "host": "h", "port": 3306, "name": "n"}}},
        "Pantheon": {"plan_sku_to_name": {"stale": "Stale"}},
    }
    # setup_portal_db fires the nested 'setup.umich.portal' hook (SiteLens setup depends on it).
    fired = []
    sc.hooks["setup.umich.portal"] = [{"name": "probe", "func": lambda conn: fired.append(conn)}]

    portal_module.setup_portal_db()

    # plan_sku_to_name is fully replaced from the portal DB (stale mapping gone; both plans mapped
    # regardless of is_active).
    assert sc.config["Pantheon"]["plan_sku_to_name"] == {
        "plan-perf-small": "Performance Small",
        "plan-legacy": "Legacy",
    }
    # Only the active plan populates portal_plan_info (values stringified).
    assert portal_module.portal_plan_info["Performance Small"] == {"traffic_limit": "35000", "cost": "1925"}
    assert "Legacy" not in portal_module.portal_plan_info
    # Sites keyed by slug with id/owner_group/shortcode.
    sites = sc.config["UMich"]["portal"]["sites"]
    assert sites["its-wws-test1"] == {"id": 101, "owner_group": "grp1", "shortcode": "T1"}
    assert sites["its-wws-test2"]["shortcode"] == "T2"
    # The nested hook fired exactly once, with the live connection.
    assert len(fired) == 1
    # The plan_info substitution now resolves against the loaded data.
    assert portal_module.plan_info("Performance Small", "cost") == "1925"


def test_plan_info_before_setup_returns_placeholder(portal_module):
    # Fresh module, setup not run -> returns the <{...}> placeholder so the 2nd config pass retries.
    assert portal_module.plan_info("Anything", "cost").startswith("<{umich portal plan_info")
