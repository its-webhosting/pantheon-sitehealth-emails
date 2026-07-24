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


def test_upcoming_notice_shape(billing):
    n = _upcoming(billing)
    assert n.severity == "alert"
    # csv row, read through the Notice fields the projection joins (campaign I14c): the site
    # name comes from the SiteContext, so `code` + `csv_extra` is the whole producer half of
    # "s,annual-bill,500.0,SC123".
    assert n.code == "annual-bill"
    assert n.csv_extra == ("500.0", "SC123")
    assert "will be billed" in n.short
    assert "/sites/42/plan/" in n.html and "/sites/42/edit/" in n.html


def test_upcoming_notice_keeps_its_custom_banknote_icon(billing):
    """annual-bill is the ONE notice in the program whose icon is not the severity default
    (SPEC I14c §2.4 #30, D-i14c-5).  Nothing else pins the producer's icon= argument, so
    without this the conversion could drop it and only the rendered email would notice."""
    assert _upcoming(billing).icon == "&#x1F4B5;"
