"""Annual-billing notice builders (campaign I1, SPEC F5).

The builders relocated to check/umich/annual_billing.py at campaign I12; load them
standalone (the I8 php_eol precedent -- no psh re-import exists for check/ modules)."""
import pytest

from helpers.checkload import load_check_module

pytestmark = pytest.mark.unit


@pytest.fixture
def billing(psh, request):
    return load_check_module(psh, "umich", "annual_billing", "umich_billing_unit_probe", request)


def _upcoming(billing):
    return billing.build_annual_bill_upcoming_notice("s", "Performance Small", 500.0, "SC123", 42)


def _in_progress(billing):
    return billing.build_annual_bill_in_progress_notice("s", "Performance Small", 500.0, "SC123")


def test_codes_are_distinct(billing):
    # RED pre-fix: both notices emitted "annual-bill", so a June U-M run wrote two
    # indistinguishable CSV rows for the same site.
    assert _upcoming(billing)["csv"].split(",")[1] != _in_progress(billing)["csv"].split(",")[1]


def test_upcoming_notice_shape(billing):
    n = _upcoming(billing)
    assert n["type"] == "alert"
    assert n["csv"] == "s,annual-bill,500.0,SC123"
    assert "will be billed" in n["short"]
    assert "/sites/42/plan/" in n["message"] and "/sites/42/edit/" in n["message"]


def test_in_progress_notice_shape(billing):
    n = _in_progress(billing)
    assert n["type"] == "alert"
    assert n["csv"] == "s,annual-bill-in-progress,500.0,SC123"
    assert "in the process of billing" in n["message"]
    assert "in the process of billing" in n["text"]
