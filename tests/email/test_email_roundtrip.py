"""Email tier: GMail send -> receive -> error-detection round-trip.

DEFERRED and skipped: the program's SMTP send is disabled and must stay disabled until
SMTP/SendGrid lands (SPEC §11, constraint C4).  This file exists and collects cleanly so
the tier is wired and ready to activate; the flow it will run is documented below.
"""
import pytest

pytestmark = pytest.mark.email


@pytest.mark.skip(reason="email send is disabled until SMTP/SendGrid lands (SPEC §11, C4)")
def test_gmail_roundtrip():
    # When activated (SPEC §11):
    #   1. Authenticate to the GMail test account via the Gmail API + OAuth refresh token
    #      (stored as a secret; no password in the harness).
    #   2. Run the program so it sends the report to the GMail test identity (sender ==
    #      recipient, so bounce/error notices land in the same inbox).  A guard asserts the
    #      recipient is that test identity, never a customer address (mirrors run_program).
    #   3. Poll the inbox by a unique per-run subject/token for a few minutes; assert receipt.
    #   4. Scan for error notices (unknown sender / undeliverable / rejected / spam).
    #   5. Optionally load the received HTML in Playwright for GMail-render checks.
    raise NotImplementedError
