"""Syrupy pin of both its-recommends-plan variants (campaign I1, SPEC F4)."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_plan_recommendation_render(psh, reset_sc, snapshot, umich):
    # The builder returns a Notice since campaign I14c; the whole-dict pin survives by
    # snapshotting the PROJECTION (SPEC D-i14c-10).  Both entries already carried all six
    # render keys, so the .ambr stays byte-identical.
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(psh.build_plan_recommendation_notice(
        "s", "Performance Medium", "Performance Small", 1234.5, 42, umich
    )) == snapshot
