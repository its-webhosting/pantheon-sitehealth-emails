"""Syrupy pin of both its-recommends-plan variants (campaign I1, SPEC F4)."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_plan_recommendation_render(psh, snapshot, umich):
    assert psh.build_plan_recommendation_notice(
        "s", "Performance Medium", "Performance Small", 1234.5, 42, umich
    ) == snapshot
