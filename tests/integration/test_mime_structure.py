"""Integration test for the assembled MIME message (test-suite SPEC §7.3).

Parses build/<site>.eml from the offline render and asserts the multipart/alternative +
related structure, a non-empty plaintext alternative, dry-run addressing, and — most
importantly — bidirectional CID integrity between the HTML and its inline images (a class of
regression the golden snapshot cannot see, since it normalizes CIDs away).
"""
import email
import email.policy
import re

import pytest

pytestmark = pytest.mark.integration

_CID_REF_RE = re.compile(r"cid:([^\"'\s>)]+)")


@pytest.fixture(scope="module")
def message(rendered_report):
    data = rendered_report["eml"].read_bytes()
    return email.message_from_bytes(data, policy=email.policy.default)


def test_top_level_is_multipart_alternative(message):
    assert message.get_content_type() == "multipart/alternative"


def test_has_nonempty_plaintext_and_html(message):
    text_parts = [p for p in message.walk() if p.get_content_type() == "text/plain"]
    html_parts = [p for p in message.walk() if p.get_content_type() == "text/html"]
    assert text_parts and html_parts
    assert text_parts[0].get_content().strip() != ""
    assert html_parts[0].get_content().strip() != ""


def test_dry_run_addressing_is_the_logged_in_user_not_an_owner(message):
    to = message["To"]
    assert "testuser" in to  # E2E_SMTP_USERNAME; dry-run never addresses a site owner


def test_cid_integrity_bidirectional(message):
    html = next(p for p in message.walk() if p.get_content_type() == "text/html").get_content()
    referenced = set(_CID_REF_RE.findall(html))

    image_cids = set()
    for part in message.walk():
        cid = part.get("Content-ID")
        if cid and part.get_content_maintype() == "image":
            image_cids.add(cid.strip("<>"))

    assert referenced, "expected at least one cid: image reference in the HTML"
    # Every referenced CID must exist as an inline image part, and vice-versa.
    assert referenced == image_cids
