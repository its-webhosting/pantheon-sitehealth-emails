"""The machine-readable per-phase contract (psh.modules.CONTRACT) vs the code that stuffs it.

CONTRACT is authoritative (CAMPAIGN.md section 4); CLAUDE.md's table is its prose rendering.
These tests are registry-driven -- set(keys a stuffer writes) == set(CONTRACT[phase]) -- so
adding a key to one side and not the other goes red."""
import pytest

import dns_classify

pytestmark = pytest.mark.unit

BASE_KEYS = {"site", "notices", "sections", "attachments"}


def _fresh_ctx(reset_sc):
    return reset_sc.SiteContext({"name": "test-site"})


def test_contract_phases_match_engine_phases(psh, reset_sc):
    import psh.modules
    assert tuple(psh.modules.CONTRACT) == psh.modules.PHASES


def test_contract_empty_phases(psh):
    import psh.modules
    for phase in ("setup", "run_finish"):
        assert psh.modules.CONTRACT[phase] == ()


def test_site_pre_contract_key(psh):
    import psh.modules
    assert psh.modules.CONTRACT["site_pre"] == ("envs",)


def test_envs_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    envs = {"live": {"initialized": True, "php_version": "8.2"}}
    psh.modules.stuff_envs_contract(ctx, envs)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_pre"])
    assert ctx["envs"] is envs


def test_site_pre_render_contract_keys(psh):
    import psh.modules
    assert psh.modules.CONTRACT["site_pre_render"] == (
        "current_plan", "recommended_plan", "plan_costs", "savings")


def test_plans_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    import psh.plans
    ctx = _fresh_ctx(reset_sc)
    psh.plans.stuff_plans_contract(ctx, "Basic", "Performance Small",
                                   {"same": {"Basic": 1.0}, "median": {}, "best": {}},
                                   12.5)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_pre_render"])
    assert ctx["current_plan"] == "Basic"
    assert ctx["recommended_plan"] == "Performance Small"
    assert ctx["plan_costs"]["same"] == {"Basic": 1.0}
    assert ctx["savings"] == 12.5


def test_traffic_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    psh.modules.stuff_traffic_contract(ctx, [("row",)], "2026-03-01", "2026-03-31")
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_traffic"])
    assert ctx["traffic_rows"] == [("row",)]
    assert ctx["start_date"] == "2026-03-01"
    assert ctx["end_date"] == "2026-03-31"


def test_gather_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    psh.modules.stuff_gather_contract(ctx, "wordpress", "https://x/", "6.5",
                                      ["a-plugin"], None, None)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_gather"])
    assert ctx["wordpress_plugins"] == ["a-plugin"]
    assert ctx["drupal_modules"] is None


def test_gather_stuffer_normalizes_non_list_plugins_and_non_dict_mods(psh, reset_sc):
    """The isinstance guards moved verbatim from main(): a failed gather leaves plugins/mods
    as a non-list/non-dict sentinel and the contract promises None for those."""
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    psh.modules.stuff_gather_contract(ctx, "drupal8", "", "unknown",
                                      None, "10.2", {"mod": {}})
    assert ctx["wordpress_plugins"] is None
    assert ctx["drupal_modules"] == {"mod": {}}


def test_dns_stuffer_writes_exactly_the_registry_keys(psh, reset_sc):
    import psh.modules
    ctx = _fresh_ctx(reset_sc)
    facts = dns_classify.DnsFacts([], [], "", [], [], [], [], [], [])
    dns_classify.stuff_dns_contract(ctx, {}, facts)
    assert set(ctx) - BASE_KEYS == set(psh.modules.CONTRACT["site_post_dns"])
