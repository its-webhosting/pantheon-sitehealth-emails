import pytest

import script_context as sc
from psh.notice import Notice, Severity

pytestmark = pytest.mark.unit


def test_notice_projects_to_the_render_dict():
    """The whole projection, end to end, against a FROZEN expected dict (instrument I5).

    Until campaign I14c this compared a Notice-fed add_notice against a dict-fed one -- an arm
    that is impossible now that add_notice takes only a Notice (SPEC §2.6).  Writing the six
    render keys out by hand is what makes this a pin rather than a tautology: every value here
    is what email_template.{html,txt}, sort_notices_and_subject and record_site_notices read.
    """
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(
        Notice(severity=Severity.ALERT, code="no-domains",
               short="no domains connected", html="<p>hi</p>", text="hi")
    )
    assert ctx["notices"][0] == {
        "type": "alert",
        "icon": "&#x1F6A8;",
        "csv": "s1,no-domains",
        "short": "no domains connected",
        "message": "<p>hi</p>",
        "text": "hi",
    }


def test_notice_text_defaults_via_html2text():
    html = "<p>hello world</p>"
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.INFO, code="x", short="s", html=html))
    assert ctx["notices"][0]["text"] == sc.html_to_text(html)


def test_csv_extra_fields_are_joined_after_site_and_code():
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.ALERT, code="wp-error", html="<p>x</p>",
                          csv_extra=("version-check", "boom")))
    assert ctx["notices"][0]["csv"] == "s1,wp-error,version-check,boom"


def test_csv_extra_preserves_a_trailing_empty_field():
    # psh/cli.py's no-primary-domain csv ends in a comma; the empty field is real.
    ctx = sc.SiteContext({"name": "s1"})
    ctx.add_notice(Notice(severity=Severity.INFO, code="no-primary-domain", html="<p>x</p>",
                          csv_extra=("",)))
    assert ctx["notices"][0]["csv"] == "s1,no-primary-domain,"


def test_projection_fills_the_icon_from_the_severity():
    ctx = sc.SiteContext({"name": "s1"})
    for severity, expected in (
        (Severity.INFO, "&#x1F50E;"),
        (Severity.WARNING, "&#x26A0;"),
        (Severity.ALERT, "&#x1F6A8;"),
    ):
        d = ctx.notice_to_dict(Notice(severity=severity, code=f"c-{severity}", html="<p>x</p>"))
        assert d["icon"] == expected


def test_projection_honors_an_explicit_icon():
    ctx = sc.SiteContext({"name": "s1"})
    d = ctx.notice_to_dict(Notice(severity=Severity.ALERT, code="annual-bill",
                                  html="<p>x</p>", icon="&#x1F4B5;"))
    assert d["icon"] == "&#x1F4B5;"


def test_projection_emits_exactly_the_six_render_keys():
    ctx = sc.SiteContext({"name": "s1"})
    d = ctx.notice_to_dict(Notice(severity=Severity.INFO, code="c", html="<p>x</p>",
                                  order="first"))
    assert set(d) == {"type", "icon", "csv", "short", "message", "text"}   # no 'order'
