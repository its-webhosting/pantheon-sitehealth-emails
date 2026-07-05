"""Render tier: load the report HTML in a headless browser and check it renders cleanly
(test-suite SPEC §7.6) for both the WordPress and Drupal reports.

The report's images are attached by Content-ID (cid:), which a standalone browser can't
resolve, so we extract them from the .eml, write them locally, and rewrite the cid: refs
before loading.  Then we assert: the DOM structure is present, the banner image actually
resolves to pixels, there are no console errors, and axe-core (vendored locally — no network)
reports no serious/critical accessibility violations outside a small, explicit allowlist.

If Chromium can't launch (browser binary or system libraries not installed), the test SKIPS
with the exact setup command rather than erroring.
"""
import email
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.render

_CID_REF = re.compile(r"cid:([^\"'\s>]+)")
_SETUP_HINT = "one-time setup: python -m playwright install --with-deps chromium"
_AXE = Path(__file__).resolve().parent.parent / "vendor" / "axe.min.js"

# Accessibility rules we currently accept for this static, email-oriented HTML report.
# Keep this list SMALL and explicit so genuinely new serious/critical issues still fail.
#   * color-contrast: email palette is brand-fixed and out of scope for this tool.
#   * region: email HTML has no ARIA landmarks by design.
# (link-name was removed once P9 was fixed: the caption's site-url anchor rendered as an
#  empty <a href=""></a> when site_url was blank; it is now guarded by {%if site_url%}.)
_AXE_ALLOWLIST = {"color-contrast", "region"}


def _rewrite_cids_to_local(rendered, dest_dir):
    """Extract inline images from the .eml and rewrite the HTML's cid: refs to file URIs."""
    msg = email.message_from_bytes(rendered["eml"].read_bytes())
    cid_to_uri = {}
    for part in msg.walk():
        cid = part.get("Content-ID")
        if cid and part.get_content_maintype() == "image":
            key = cid.strip("<>")
            out = dest_dir / f"{key}.{part.get_content_subtype()}"
            out.write_bytes(part.get_payload(decode=True))
            cid_to_uri[key] = out.as_uri()
    html = rendered["html"].read_text()
    html = _CID_REF.sub(lambda m: cid_to_uri.get(m.group(1), m.group(0)), html)
    page_file = dest_dir / "render.html"
    page_file.write_text(html)
    return page_file


@pytest.mark.parametrize("report_fixture", ["rendered_report", "rendered_report_drupal"])
def test_report_renders_cleanly(report_fixture, request, tmp_path):
    from playwright.sync_api import sync_playwright

    rendered = request.getfixturevalue(report_fixture)
    page_file = _rewrite_cids_to_local(rendered, tmp_path)

    pw = sync_playwright().start()
    try:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - environment provisioning, not a test failure
            pytest.skip(f"Chromium can't launch ({type(exc).__name__}); {_SETUP_HINT}")
        try:
            page = browser.new_page()
            console_errors = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.goto(page_file.as_uri(), wait_until="load")

            # ── structure ────────────────────────────────────────────────────────────
            assert "Pantheon Traffic Report" in page.title()
            assert page.locator("img.banner_image").count() == 1
            assert page.locator("img.chart_image").count() >= 1
            banner_width = page.eval_on_selector("img.banner_image", "el => el.naturalWidth")
            assert banner_width and banner_width > 0  # banner actually loaded

            # ── no console errors (email HTML has no JS; broken assets would show here) ─
            assert console_errors == [], f"console errors: {console_errors}"

            # ── accessibility smoke (axe-core, vendored; offline) ─────────────────────
            page.add_script_tag(path=str(_AXE))
            result = page.evaluate("async () => await axe.run(document)")
            serious = [
                v for v in result["violations"]
                if v.get("impact") in ("serious", "critical") and v["id"] not in _AXE_ALLOWLIST
            ]
            assert not serious, "axe serious/critical violations: " + json.dumps(
                [(v["id"], v["impact"]) for v in serious]
            )
        finally:
            browser.close()
    finally:
        pw.stop()
