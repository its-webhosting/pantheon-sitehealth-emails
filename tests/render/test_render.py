"""Render tier: load the report HTML in a headless browser and check it renders (SPEC §9).

The report's images are attached by Content-ID (cid:), which a standalone browser can't
resolve, so we extract them from the .eml, write them locally, rewrite the cid: refs, then
load the page and assert the DOM structure and that the banner image actually resolves.

If Chromium can't launch (its browser binary or system libraries aren't installed), the
test SKIPS with the exact setup command rather than erroring — the render logic is fine,
the environment just needs a one-time provisioning step.
"""
import email
import re

import pytest

pytestmark = pytest.mark.render

_CID_REF = re.compile(r"cid:([^\"'\s>]+)")
_SETUP_HINT = "one-time setup: python -m playwright install --with-deps chromium"


def _rewrite_cids_to_local(rendered_report, dest_dir):
    """Extract inline images from the .eml and rewrite the HTML's cid: refs to file URIs."""
    msg = email.message_from_bytes(rendered_report["eml"].read_bytes())
    cid_to_uri = {}
    for part in msg.walk():
        cid = part.get("Content-ID")
        if cid and part.get_content_maintype() == "image":
            key = cid.strip("<>")
            out = dest_dir / f"{key}.{part.get_content_subtype()}"
            out.write_bytes(part.get_payload(decode=True))
            cid_to_uri[key] = out.as_uri()
    html = rendered_report["html"].read_text()
    html = _CID_REF.sub(lambda m: cid_to_uri.get(m.group(1), m.group(0)), html)
    page_file = dest_dir / "render.html"
    page_file.write_text(html)
    return page_file


def test_report_renders_in_browser(rendered_report, tmp_path):
    from playwright.sync_api import sync_playwright

    page_file = _rewrite_cids_to_local(rendered_report, tmp_path)

    pw = sync_playwright().start()
    try:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - environment provisioning, not a test failure
            pytest.skip(f"Chromium can't launch ({type(exc).__name__}); {_SETUP_HINT}")
        try:
            page = browser.new_page()
            page.goto(page_file.as_uri())
            assert "Pantheon Traffic Report" in page.title()
            assert page.locator("img.banner_image").count() == 1
            # The banner image resolved to real pixels (cid rewrite worked, asset loaded).
            banner_width = page.eval_on_selector("img.banner_image", "el => el.naturalWidth")
            assert banner_width and banner_width > 0
        finally:
            browser.close()
    finally:
        pw.stop()
