"""build_plan_recommendation_notice unit tests (campaign I1, SPEC F4)."""
import pytest

pytestmark = pytest.mark.unit


def _notice(psh, umich):
    return psh.build_plan_recommendation_notice(
        "s", "Performance Medium", "Performance Small", 1234.5, 42, umich
    )


def test_umich_variant_links_the_portal(psh):
    n = _notice(psh, umich=True)
    assert "admin.webservices.umich.edu/sites/42/plan/" in n["message"]
    assert "admin.webservices.umich.edu/sites/42/plan/" in n["text"]


def test_generic_variant_has_no_umich_urls(psh):
    # RED pre-fix: the portal URL rendered un-gated, with portal_site_id=0 on non-U-M runs.
    n = _notice(psh, umich=False)
    assert "admin.webservices" not in n["message"] and "admin.webservices" not in n["text"]
    # The June 16-30 downgrade window is U-M portal billing policy (SPEC F4):
    assert "June 16" not in n["message"] and "June 16" not in n["text"]
    # The recommendation itself still reads through:
    assert "Performance Small" in n["message"] and "$1,234.50" in n["text"]


def test_csv_is_variant_independent(psh):
    # D-i7-5 (campaign I7): the savings field is comma-free -- a thousands separator
    # inside a comma-separated row split the field and made the column count variable.
    assert _notice(psh, True)["csv"] == _notice(psh, False)["csv"] == (
        "s,its-recommends-plan,Performance Medium,Performance Small,1234.50"
    )
