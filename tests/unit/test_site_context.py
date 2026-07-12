"""Unit tests for the SiteContext class (script_context.SiteContext).

SiteContext is a dict subclass — subscript access (site_context['notices'|'sections'|
'attachments'|'site']) is unchanged — that also owns the mutators for its collections.  These
replaced the old module-level sc.add_notice/add_notices free functions.
"""
import pytest

pytestmark = pytest.mark.unit


def _n(message="<p>Hi</p>", type="info", **extra):
    return {"type": type, "message": message, **extra}


_LINKED = ('<p>Some pages on <a href="https://a.example.edu/">a.example.edu</a> are not '
           'cached, which protects your site from traffic spikes and makes pages load '
           'faster.</p>')


def test_plaintext_rendering_is_deterministic_across_notices(reset_sc):
    """The html2text renderer must be stateless across calls.

    Regression: sc used ONE shared html2text.HTML2Text instance.  That instance flips its
    own `inline_links` True->False during the first handle(), so the FIRST notice of a run
    ignored the configured reference-link style, and the reference counter then climbed
    ([1], [2], ...) for the rest of the run -- every notice rendered differently from its
    siblings, and test outcomes depended on how many notices any earlier test had rendered.
    """
    first = reset_sc.SiteContext({"name": "x"})
    first.add_notice(_n(_LINKED))

    # Render several more notices, exactly as a real multi-site run does...
    for _ in range(3):
        other = reset_sc.SiteContext({"name": "y"})
        other.add_notice(_n(_LINKED))

    # ...then the same HTML again.  Identical input must give identical plaintext.
    last = reset_sc.SiteContext({"name": "z"})
    last.add_notice(_n(_LINKED))

    assert last["notices"][0]["text"] == first["notices"][0]["text"]


def test_plaintext_links_keep_their_urls_intact_and_wrap_the_prose(reset_sc):
    """Reference-style links: prose wraps, URLs stay whole.

    The e2e golden's fixture notices carry no links, so nothing else covers how a LINKED
    notice renders to plaintext.  Both failure modes of the inline-link alternative are
    pinned here: unwrapped 250+ char lines, and URLs split mid-string (which would break the
    link for the reader).
    """
    long_url = "https://documentation.its.umich.edu/cloudflare-cache-report#short-cache-time"
    ctx = reset_sc.SiteContext({"name": "x"})
    ctx.add_notice(_n(f'<p>These pages are only cached for 1 hour. Increase the cache time to '
                      f'31536000 seconds for the full cost-savings and performance benefit. '
                      f'<a href="{long_url}">How to fix this</a></p>'))
    text = ctx["notices"][0]["text"]

    assert max(len(line) for line in text.splitlines()) < 100   # prose wrapped
    assert long_url in text                                     # URL never split mid-string


def test_construction_has_empty_collections(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    assert isinstance(ctx, dict)  # subscript access preserved
    assert ctx["site"] == {"name": "x"}
    assert ctx["notices"] == []
    assert ctx["sections"] == []
    assert ctx["attachments"] == []


def test_add_notice_fills_icon_and_text(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    ctx.add_notice(_n())
    n = ctx["notices"][0]
    assert n["icon"]           # filled from 'type'
    assert n["text"].strip()   # filled via html2text


def test_add_notice_preserves_existing_icon_and_text(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    ctx.add_notice(_n(icon="ICON", text="TEXT"))
    n = ctx["notices"][0]
    assert n["icon"] == "ICON"  # not overwritten
    assert n["text"] == "TEXT"


def test_add_notice_missing_message_exits(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    with pytest.raises(SystemExit):
        ctx.add_notice({"type": "info"})  # no 'message'


def test_add_notice_order_first_prepends(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    ctx.add_notice(_n(message="a", icon="i", text="a"))
    ctx.add_notice(_n(message="b", icon="i", text="b", order="first"))
    assert [n["message"] for n in ctx["notices"]] == ["b", "a"]


def test_add_notices_bulk_in_order(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    ctx.add_notices([_n(message="a", icon="i", text="a"), _n(message="b", icon="i", text="b")])
    assert [n["message"] for n in ctx["notices"]] == ["a", "b"]


def test_add_section_and_attachment(reset_sc):
    ctx = reset_sc.SiteContext({"name": "x"})
    ctx.add_section({"heading": "H"})
    ctx.add_attachment({"cid": "c"})
    assert ctx["sections"] == [{"heading": "H"}]
    assert ctx["attachments"] == [{"cid": "c"}]
