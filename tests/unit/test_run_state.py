"""RunState seam tests (campaign I13, SPEC section 4 items 5-7).

RunState is the one home for the run accumulators (CAMPAIGN.md section 6); the two
reconnect-counter attributes it absorbs are DELETED from script_context, so a stale
patch/read fails loudly (the I5 loud-failure property, one level up).
"""
import pytest

import script_context as sc
from psh.lifecycle import RunState


@pytest.mark.unit
def test_run_state_defaults_are_fresh_per_instance():
    a, b = RunState(), RunState()
    a.all_warnings.append("x")
    a.db_reconnects_by_site["s"] = 1
    assert b.all_warnings == [] and b.db_reconnects_by_site == {}  # no shared mutable defaults
    assert (b.emails_sent, b.site_savings, b.site_results,
            b.db_reconnect_failures_by_site) == (0, [], {}, {})


@pytest.mark.unit
def test_record_site_notices_inserts_contacts_at_field_two():
    rs = RunState()
    rs.all_warnings.append("pre-existing,row")
    rs.record_site_notices(
        [{"csv": "its-wws-test1,no-domains,"}, {"csv": "its-wws-test1,frozen,extra"}],
        "owner@example.edu",
    )
    assert rs.all_warnings == [
        "pre-existing,row",
        "its-wws-test1,owner@example.edu,no-domains,",
        "its-wws-test1,owner@example.edu,frozen,extra",
    ]


@pytest.mark.unit
def test_stale_counter_attributes_are_gone_from_script_context():
    # Guards the one-owning-namespace rule (SPEC 2.1): a test still patching the old
    # sc attributes must fail loudly, not silently miss the counters.
    assert not hasattr(sc, "db_reconnects_by_site")
    assert not hasattr(sc, "db_reconnect_failures_by_site")


@pytest.mark.unit
def test_reset_sc_provides_a_fresh_run_state(reset_sc):
    assert isinstance(sc.run_state, RunState)
    assert sc.run_state.all_warnings == [] and sc.run_state.emails_sent == 0
