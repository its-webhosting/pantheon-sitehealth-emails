"""psh.render.render_report: Jinja -> build files -> php inline -> !important pass (campaign I12).

The e2e goldens prove byte-identity of the whole pipeline through main(); this file pins the
function's own I/O contract at its seam (SPEC I12 §4).  Uses the real php inliner, like
tests/integration/test_css_inliner_encoding.py (skip when php is absent).
"""
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# A style block whose declaration lacks !important, so the B54 regex pass must add it,
# plus one Jinja placeholder per body so rendering is proven.
HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<style>@media screen { p { color: red; } }</style></head>
<body><p>{{ site_name }}</p></body></html>
"""
TXT_TEMPLATE = "report for {{ site_name }}\n"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    if shutil.which("php") is None:
        pytest.skip("php not on PATH")
    (tmp_path / "email_template.html").write_text(HTML_TEMPLATE, encoding="utf-8")
    (tmp_path / "email_template.txt").write_text(TXT_TEMPLATE, encoding="utf-8")
    for asset in ("inline-styles.php", "vendor"):
        (tmp_path / asset).symlink_to(REPO_ROOT / asset)
    (tmp_path / "build").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_render_report_writes_all_four_build_files(workdir):
    import psh.render
    psh.render.render_report("testsite", {"site_name": "testsite"})
    for name in ("testsite.html", "testsite.txt", "testsite-inline.html", "testsite-inline2.html"):
        assert (workdir / "build" / name).exists(), name


def test_render_report_returns_inline2_html_and_rendered_text(workdir):
    import psh.render
    html_body, text_body = psh.render.render_report("testsite", {"site_name": "testsite"})
    assert html_body == (workdir / "build" / "testsite-inline2.html").read_text(encoding="utf-8")
    # Jinja2's default keep_trailing_newline=False strips the template's single trailing
    # "\n" -- render_report reproduces main()'s bare Template(f.read()) behavior verbatim,
    # so the rendered text has no trailing newline.  (The e2e goldens are the authoritative
    # byte-identity oracle for the whole pipeline.)
    assert text_body == "report for testsite"
    assert "testsite" in html_body


def test_render_report_appends_important_to_inlined_css(workdir):
    import psh.render
    html_body, _ = psh.render.render_report("testsite", {"site_name": "testsite"})
    # The template's @media rule is not inlinable, so Emogrifier retains the <style> block
    # verbatim in -inline.html; the B54 regex pass then appends !important to it, producing
    # -inline2.html (returned as html_body).  Guard-of-the-guard: if Emogrifier ever started
    # deleting/inlining this block, "<style" would vanish from inline1 and the assertion below
    # would be checking a no-op -- so pin its presence explicitly rather than let that go quiet.
    inline1 = (workdir / "build" / "testsite-inline.html").read_text(encoding="utf-8")
    assert "<style" in inline1  # the block must survive Emogrifier, or this test is vacuous
    assert "color: red !important;" not in inline1
    assert "color: red !important;" in html_body
