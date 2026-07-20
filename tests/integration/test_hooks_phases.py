"""The named-phase hook registry (script_context.PHASES).

add_hook/invoke_hooks accept exactly the bare names in sc.PHASES plus dotted plugin-defined
events ('setup.umich.portal' style); anything else is a loud fatal error.  Within a phase,
hooks run in registration order.  See CLAUDE.md ("Per-site report pipeline") for the
per-phase site_context data contract.
"""
import pytest

pytestmark = pytest.mark.integration

EXPECTED_PHASES = (
    "setup",
    "site_pre",
    "site_post_traffic",
    "site_post_dns",
    "site_post_gather",
    "site_pre_render",
    "run_finish",
)


def test_phases_order_and_content(reset_sc):
    sc = reset_sc
    assert sc.PHASES == EXPECTED_PHASES


def test_add_hook_unknown_bare_name_is_fatal(reset_sc):
    sc = reset_sc
    with pytest.raises(SystemExit):
        sc.add_hook("check", {"name": "old-name-probe", "func": lambda: None})
    with pytest.raises(SystemExit):
        sc.add_hook("nonsense", {"name": "probe", "func": lambda: None})


def test_invoke_hooks_unknown_bare_name_is_fatal(reset_sc):
    sc = reset_sc
    with pytest.raises(SystemExit):
        sc.invoke_hooks("check")


def test_dotted_event_registers_and_invokes(reset_sc):
    sc = reset_sc
    fired = []
    sc.add_hook("setup.custom.event", {"name": "probe", "func": lambda x: fired.append(x),
                                       "consumes": [], "produces": []})
    sc.invoke_hooks("setup.custom.event", 42)
    assert fired == [42]


def test_empty_valid_phase_is_a_noop(reset_sc):
    sc = reset_sc
    for phase in EXPECTED_PHASES:
        sc.invoke_hooks(phase)  # must not raise, must not print errors


def test_invoke_unregistered_dotted_event_is_a_noop(reset_sc):
    sc = reset_sc
    sc.invoke_hooks("setup.never.registered")  # allowed: dotted names need no registration


def test_within_phase_registration_order_preserved(reset_sc):
    sc = reset_sc
    seen = []
    for tag in ("a", "b", "c"):
        sc.add_hook("site_pre", {"name": tag, "func": lambda t=tag: seen.append(t),
                                 "consumes": [], "produces": []})
    sc.invoke_hooks("site_pre")
    assert seen == ["a", "b", "c"]


def test_reset_sc_seeds_all_phases(reset_sc):
    sc = reset_sc
    assert set(sc.hooks.keys()) == set(EXPECTED_PHASES)
    assert all(v == [] for v in sc.hooks.values())


def test_add_hook_missing_declarations_is_fatal(reset_sc):
    """CAMPAIGN.md section 4 condition 5: no legacy mode -- a hook without consumes/produces
    (or with a non-list / non-str member) must die loudly at registration."""
    sc = reset_sc
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None})
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None, "consumes": []})
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None,
                                 "consumes": "traffic_rows", "produces": []})
    with pytest.raises(SystemExit):
        sc.add_hook("site_pre", {"name": "probe", "func": lambda: None,
                                 "consumes": [42], "produces": []})


def test_add_hook_dotted_event_must_declare_empty(reset_sc):
    """Contract keys are phase-anchored; a dotted event has no phase position, so a non-empty
    declaration is unvalidatable (SPEC D-i4-3)."""
    sc = reset_sc
    with pytest.raises(SystemExit):
        sc.add_hook("setup.custom.event", {"name": "probe", "func": lambda: None,
                                           "consumes": ["traffic_rows"], "produces": []})
    sc.add_hook("setup.custom.event", {"name": "probe", "func": lambda: None,
                                       "consumes": [], "produces": []})  # empty is fine
