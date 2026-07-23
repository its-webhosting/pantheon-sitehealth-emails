"""psh.sort_notices_and_subject: B50's sort/subject core + billing-key wiring (campaign I12).

This pure helper is the runtime seam for the previously-untested umich-only billing call
sites (LEDGER I1 obligation).  Pins the preserved quirks: the in-progress notice renders
first but NEVER influences the subject (it is inserted after the subject computation),
and billing dicts never enter site_context["notices"].
"""
import pytest

pytestmark = pytest.mark.integration

REPORT = "Pantheon Traffic Report, Mar 31, 2026"


def _notice(ntype, short="s"):
    return {"type": ntype, "short": short, "csv": f"x,{ntype}"}


def _ctx(reset_sc, notices=(), **keys):
    ctx = reset_sc.SiteContext({"name": "mysite"})
    for n in notices:
        ctx["notices"].append(n)
    for k, v in keys.items():
        ctx[k] = v
    return ctx


def test_default_subject_and_empty_notices(psh, reset_sc):
    sorted_notices, subject = psh.sort_notices_and_subject(_ctx(reset_sc), REPORT)
    assert sorted_notices == [] and subject == f"mysite: {REPORT}"


def test_sorts_alert_warning_info_and_prefixes_action_required(psh, reset_sc):
    ns = [_notice("info"), _notice("alert", "bad"), _notice("warning")]
    ctx = _ctx(reset_sc, notices=ns)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert [n["type"] for n in sorted_notices] == ["alert", "warning", "info"]
    assert subject == f"Action Required: mysite: bad | {REPORT}"


def test_warning_first_prefixes_action_recommended(psh, reset_sc):
    ctx = _ctx(reset_sc, notices=[_notice("warning", "meh")])
    _, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert subject == f"Action Recommended: mysite: meh | {REPORT}"


def test_info_only_keeps_default_subject(psh, reset_sc):
    ctx = _ctx(reset_sc, notices=[_notice("info")])
    _, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert subject == f"mysite: {REPORT}"


def test_upcoming_key_overrides_subject_and_leads(psh, reset_sc):
    up = {"type": "alert", "short": "bill", "csv": "x,annual-bill"}
    ctx = _ctx(reset_sc, notices=[_notice("alert", "other")], annual_bill_upcoming=up)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert subject == "Time Sensitive: mysite annual billing"
    assert sorted_notices[0] is up


def test_in_progress_key_leads_but_never_touches_subject(psh, reset_sc):
    ip = {"type": "alert", "short": "billing", "csv": "x,annual-bill-in-progress"}
    ctx = _ctx(reset_sc, notices=[_notice("warning", "meh")], annual_bill_in_progress=ip)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert sorted_notices[0] is ip
    assert subject == f"Action Recommended: mysite: meh | {REPORT}"   # the preserved quirk


def test_both_keys_render_in_progress_first_then_upcoming(psh, reset_sc):
    up = {"type": "alert", "short": "u", "csv": "x,annual-bill"}
    ip = {"type": "alert", "short": "i", "csv": "x,annual-bill-in-progress"}
    ctx = _ctx(reset_sc, annual_bill_upcoming=up, annual_bill_in_progress=ip)
    sorted_notices, subject = psh.sort_notices_and_subject(ctx, REPORT)
    assert sorted_notices[0] is ip and sorted_notices[1] is up
    assert subject == "Time Sensitive: mysite annual billing"


def test_helper_does_not_mutate_site_context_notices(psh, reset_sc):
    ip = {"type": "alert", "short": "i", "csv": "x,annual-bill-in-progress"}
    ctx = _ctx(reset_sc, notices=[_notice("info")], annual_bill_in_progress=ip)
    psh.sort_notices_and_subject(ctx, REPORT)
    assert ctx["notices"] == [_notice("info")]   # billing keys never join the csv source
