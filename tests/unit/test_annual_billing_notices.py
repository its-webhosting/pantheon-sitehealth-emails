"""Annual-billing notice builders (campaign I1, SPEC F5)."""
import pytest

pytestmark = pytest.mark.unit


def _upcoming(psh):
    return psh.build_annual_bill_upcoming_notice("s", "Performance Small", 500.0, "SC123", 42)


def _in_progress(psh):
    return psh.build_annual_bill_in_progress_notice("s", "Performance Small", 500.0, "SC123")


def test_codes_are_distinct(psh):
    # RED pre-fix: both notices emitted "annual-bill", so a June U-M run wrote two
    # indistinguishable CSV rows for the same site.
    assert _upcoming(psh)["csv"].split(",")[1] != _in_progress(psh)["csv"].split(",")[1]


def test_upcoming_notice_shape(psh):
    n = _upcoming(psh)
    assert n["type"] == "alert"
    assert n["csv"] == "s,annual-bill,500.0,SC123"
    assert "will be billed" in n["short"]
    assert "/sites/42/plan/" in n["message"] and "/sites/42/edit/" in n["message"]


def test_in_progress_notice_shape(psh):
    n = _in_progress(psh)
    assert n["type"] == "alert"
    assert n["csv"] == "s,annual-bill-in-progress,500.0,SC123"
    assert "in the process of billing" in n["message"]
    assert "in the process of billing" in n["text"]
