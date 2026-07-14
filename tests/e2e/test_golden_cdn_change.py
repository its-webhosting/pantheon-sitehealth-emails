"""4th golden: the Pantheon CDN-change check driven through the REAL main().

The other three goldens have platform-only domain:list fixtures, so they can only prove this
check stays SILENT.  This one gives its-wws-test1 a CUSTOM domain that is CNAME'd to the legacy
Pantheon GCDN, and shims DNS in the subprocess (tests/shims/pyshim), so the whole path runs:

    main() -> terminus domain:list -> dns_classify.classify_domains -> stuff_dns_contract
           -> invoke_hooks("site_post_dns") -> check.pantheon_cdn_change
           -> terminus domain:dns (Pantheon's required records) -> notice
           -> email_template.html -> inline-styles.php (Emogrifier) -> !important pass -> .eml

SCOPE (deliberate):
  * source (1) (public DNS) only -- [Cloudflare] stays disabled because enabling it makes
    plugin/cloudflare/ips.py call the live Cloudflare API.  Source (2) is covered by
    tests/unit/test_pantheon_cdn_change_detect.py and
    tests/integration/test_check_pantheon_cdn_change.py.
  * the GENERIC copy -- minimal.toml has no [UMich] section.  The U-M copy is pinned by
    tests/integration/test_pantheon_cdn_change_notice_render.py.
"""
import email
import email.policy
import json

import pytest

from conftest import (
    E2E_SITE,
    REPO_ROOT,
    build_rendered_report,
    make_workdir,
)

pytestmark = pytest.mark.e2e

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "terminus-cdnchange"
DNS_SHIM = REPO_ROOT / "tests" / "shims" / "pyshim"   # one shim dir; DNS_SHIM_ZONE activates the DNS shim

CUSTOM = "cdn-change.example.edu"
TARGET = "live-its-wws-test1.pantheonsite.io"

# The custom domain is CNAME'd to the legacy GCDN and resolves to the Pantheon edge addresses --
# so classify_domains sees real addresses (no not-in-dns alert) while the CDN-change check sees
# the CNAME.
ZONE = {
    f"{CUSTOM}|CNAME": [f"{TARGET}."],
    f"{CUSTOM}|A": ["23.185.0.4"],
    f"{CUSTOM}|AAAA": ["2620:12a:8000::4", "2620:12a:8001::4"],
}


@pytest.fixture(scope="module")
def cdn_change_render(tmp_path_factory):
    work = make_workdir(tmp_path_factory.mktemp("cdnchange"))
    zone_file = work / "zone.json"
    zone_file.write_text(json.dumps(ZONE))
    proc = build_rendered_report(
        work,
        fixtures_dir=FIXTURES,
        extra_env={"PYTHONPATH": str(DNS_SHIM), "DNS_SHIM_ZONE": str(zone_file)},
    )
    build = work / "build"
    return {
        "proc": proc,
        "html": build / f"{E2E_SITE}.html",
        "txt": build / f"{E2E_SITE}.txt",
        "eml": build / f"{E2E_SITE}.eml",
        "inline2": build / f"{E2E_SITE}-inline2.html",
    }


def test_render_succeeds(cdn_change_render):
    assert cdn_change_render["proc"].returncode == 0, cdn_change_render["proc"].stderr
    assert "Traceback" not in cdn_change_render["proc"].stderr


def test_main_wires_custom_domains_into_the_check(cdn_change_render):
    # The thing NO other test can prove: main() feeds the hook the domain strings it expects, the
    # domain:dns call goes through terminus(), and the notice reaches the rendered report with
    # PANTHEON's replacement addresses (NOT "unavailable", which is what a missing fixture yields).
    html = cdn_change_render["html"].read_text()
    assert CUSTOM in html
    assert "23.185.0.4" in html
    assert "2620:12a:8000::4" in html and "2620:12a:8001::4" in html
    assert "making a change to their CDN" in html
    assert "unavailable" not in html


def test_golden_pins_the_generic_copy(cdn_change_render):
    # minimal.toml has no [UMich] section -> umich_enabled() is False.  Assert the variant
    # explicitly so the distinction cannot rot into "we thought we were testing the U-M copy".
    html = cdn_change_render["html"].read_text()
    assert "Please replace each CNAME record above" in html
    assert "ITS will make these changes" not in html


def test_notice_survives_the_inline_css_pipeline(cdn_change_render):
    # build/<site>-inline2.html is what actually gets attached to the message.
    inline2 = cdn_change_render["inline2"].read_text()
    assert CUSTOM in inline2 and "23.185.0.4" in inline2


def test_notice_reaches_the_eml(cdn_change_render):
    msg = email.message_from_bytes(cdn_change_render["eml"].read_bytes(),
                                   policy=email.policy.default)
    bodies = [p.get_content() for p in msg.walk() if p.get_content_maintype() == "text"]
    assert any(CUSTOM in b for b in bodies)


def test_html_matches_golden(cdn_change_render, normalize_html, snapshot):
    assert normalize_html(cdn_change_render["html"].read_text()) == snapshot


def test_txt_matches_golden(cdn_change_render, snapshot):
    assert cdn_change_render["txt"].read_text() == snapshot
