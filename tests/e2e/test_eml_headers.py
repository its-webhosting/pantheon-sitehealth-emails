"""Guard the assembled .eml's identity headers (From / Reply-to / Bcc / dry-run To / msgid).

There is NO byte .eml golden (the Date: header is datetime.now(UTC), volatile), so the HTML/TXT
snapshots do not cover these headers.  P8a moves them from hardcoded literals to [Email]/[SMTP]
config with byte-identical defaults; this test is the guard that proves the defaults reproduce the
exact bytes.  Written before P8a so a regression is caught.

Dry run (no --for-real): To is the logged-in user, Bcc is absent.
"""
import email
import email.policy

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def message(rendered_report):
    data = rendered_report["eml"].read_bytes()
    return email.message_from_bytes(data, policy=email.policy.default)


def test_from_header(message):
    assert str(message["From"]) == "University of Michigan Webmaster Team <webmaster@umich.edu>"


def test_reply_to_header_exact_including_capitalization(message):
    # Note the non-RFC 'Reply-to' spelling: EmailMessage preserves header-name case, and the
    # program sets msg["Reply-to"].  P8a must keep this exact key + value.
    assert message["Reply-to"] == "webmaster@umich.edu"


def test_dry_run_to_is_logged_in_user(message):
    assert str(message["To"]) == "januside@go.mail.umich.edu, testuser@umich.edu"


def test_no_bcc_in_dry_run(message):
    # Bcc is only set under --for-real, which the interlock forbids in tests.
    assert message["Bcc"] is None


def test_msgid_domain_on_inline_images(message):
    # make_msgid(domain=...) sets the Content-ID of the inline banner/chart PNGs; that domain
    # is what P8a moves to [Email].msgid_domain.  There is no top-level Message-ID header.
    image_cids = [
        p.get("Content-ID") for p in message.walk()
        if p.get_content_maintype() == "image" and p.get("Content-ID")
    ]
    assert image_cids, "expected inline image parts with Content-IDs"
    assert all(cid.endswith("@webservices.umich.edu>") for cid in image_cids)
