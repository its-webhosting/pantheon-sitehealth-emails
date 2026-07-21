"""PlanCatalog/PlanInfo (campaign I7, SPEC D-i7-2): the typed view over
[Pantheon].plan_info.  from_config performs B12's "-" -> None normalization MUTATING the
config sub-dict (main()'s plan_info alias and the I11/I12 regions read the same object)."""
import pytest

from psh.plans import PlanCatalog, PlanInfo

pytestmark = pytest.mark.unit


def _pantheon_config():
    return {
        "plan_info": {
            "Basic": {"cost": 300.0, "traffic_limit": 1000, "upgrade_at": 800,
                      "upgrade_to": "Performance Small", "downgrade_to": "-"},
            "Performance Small": {"cost": "1200.00", "traffic_limit": "5000",
                                  "upgrade_at": 4000,
                                  "upgrade_to": "Performance Medium",
                                  "downgrade_to": "Basic"},
        },
    }


def _catalog(cfg=None):
    cfg = cfg or _pantheon_config()
    return PlanCatalog.from_config(cfg, overage_block_size=1000, overage_block_cost=100.0)


def test_normalization_mutates_the_config_dict():
    cfg = _pantheon_config()
    _catalog(cfg)
    assert cfg["plan_info"]["Basic"]["downgrade_to"] is None       # "-" -> None, in place
    assert cfg["plan_info"]["Basic"]["upgrade_to"] == "Performance Small"


def test_catalog_exposes_raw_alias_and_ordered_names():
    cfg = _pantheon_config()
    catalog = _catalog(cfg)
    assert catalog.plan_info is cfg["plan_info"]                   # alias, not a copy
    assert catalog.plan_names == ["Basic", "Performance Small"]    # insertion order
    assert catalog.overage_block_size == 1000
    assert catalog.overage_block_cost == 100.0


def test_typed_plans_cast_string_config_values():
    # The umich portal substitution supplies cost/traffic_limit as strings.
    p = _catalog().plans["Performance Small"]
    assert p == PlanInfo(cost=1200.0, traffic_limit=5000, upgrade_at=4000,
                         upgrade_to="Performance Medium", downgrade_to="Basic")


def test_missing_plan_info_key_raises_keyerror():
    with pytest.raises(KeyError):
        PlanCatalog.from_config({}, overage_block_size=1, overage_block_cost=1.0)
