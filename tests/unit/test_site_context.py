"""Unit tests for the SiteContext class (script_context.SiteContext).

SiteContext is a dict subclass — subscript access (site_context['notices'|'sections'|
'attachments'|'site']) is unchanged — that also owns the mutators for its collections.  These
replaced the old module-level sc.add_notice/add_notices free functions.
"""
import pytest

pytestmark = pytest.mark.unit


def _n(message="<p>Hi</p>", type="info", **extra):
    return {"type": type, "message": message, **extra}


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
