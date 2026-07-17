import pytest

import script_context as sc
from psh.notice import Notice, Severity

pytestmark = pytest.mark.unit


def test_notice_projects_to_legacy_dict():
    html = "<p>hi</p>"
    from_notice = sc.SiteContext({"name": "s1"})
    from_notice.add_notice(
        Notice(severity=Severity.ALERT, code="no-domains",
               short="no domains connected", html=html, text="hi")
    )
    from_dict = sc.SiteContext({"name": "s1"})
    from_dict.add_notice(
        {"type": "alert", "csv": "s1,no-domains",
         "short": "no domains connected", "message": html, "text": "hi"}
    )
    assert from_notice["notices"] == from_dict["notices"]   # full dict equality (both lack 'order')


def test_notice_text_defaults_via_html2text():
    html = "<p>hello world</p>"
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.INFO, code="x", short="s", html=html))
    assert ctx["notices"][0]["text"] == sc.html_to_text(html)
