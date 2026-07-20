"""Each CAMPAIGN.md section-4 fatal condition demonstrated red (PD#14), plus the
topological invoke order with registration-order tie-breaking."""
import pytest

pytestmark = pytest.mark.unit


def _hook(name, consumes=(), produces=(), fired=None):
    return {"name": name, "consumes": list(consumes), "produces": list(produces),
            "func": (lambda *a, **k: fired.append(name)) if fired is not None else (lambda *a, **k: None)}


def test_condition_1_unproduced_consumed_key_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", consumes=["no-such-key"]))
    with pytest.raises(m.UnproducedKeyError, match="no-such-key"):
        m.validate_hooks()


def test_condition_2_two_hook_producers_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", produces=["shared"]))
    reset_sc.add_hook("site_pre", _hook("b", produces=["shared"]))
    with pytest.raises(m.DuplicateProducerError, match="shared"):
        m.validate_hooks()


def test_condition_2_hook_producing_a_core_registry_key_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", produces=["traffic_rows"]))
    with pytest.raises(m.DuplicateProducerError, match="traffic_rows"):
        m.validate_hooks()


def test_condition_3_same_phase_cycle_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", consumes=["x"], produces=["y"]))
    reset_sc.add_hook("site_pre", _hook("b", consumes=["y"], produces=["x"]))
    with pytest.raises(m.HookCycleError):
        m.validate_hooks()


def test_condition_4_key_first_produced_in_a_later_phase_is_fatal(psh, reset_sc):
    import psh.modules as m
    reset_sc.add_hook("site_pre", _hook("a", consumes=["framework"]))  # owned by site_post_gather
    with pytest.raises(m.LaterPhaseKeyError, match="framework"):
        m.validate_hooks()


def test_earlier_phase_key_is_legal(psh, reset_sc):
    """The check.umich.cloudflare_cms shape: consuming a site_post_dns key at site_post_gather."""
    import psh.modules as m
    reset_sc.add_hook("site_post_gather", _hook("a", consumes=["fqdns_behind_cloudflare"]))
    m.validate_hooks()  # must not raise


def test_hook_produced_key_consumed_same_phase_is_legal_and_ordered(psh, reset_sc):
    import psh.modules as m
    fired = []
    reset_sc.add_hook("site_pre", _hook("consumer", consumes=["made"], fired=fired))
    reset_sc.add_hook("site_pre", _hook("producer", produces=["made"], fired=fired))
    m.validate_hooks()  # must not raise
    reset_sc.invoke_hooks("site_pre")
    assert fired == ["producer", "consumer"]  # producer first despite later registration


def test_edgeless_hooks_keep_registration_order(psh, reset_sc):
    import psh.modules as m
    fired = []
    for tag in ("a", "b", "c"):
        reset_sc.add_hook("site_pre", _hook(tag, fired=fired))
    m.validate_hooks()
    reset_sc.invoke_hooks("site_pre")
    assert fired == ["a", "b", "c"]


def test_validate_clean_on_empty_registry(psh, reset_sc):
    import psh.modules as m
    m.validate_hooks()  # a run with no hooks at all is valid
