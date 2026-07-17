"""Integration tests for check/umich/sitelens.py (test-suite SPEC §7.4).

No live portal DB: the module globals it reads (sitelens_configured_scans_by_site,
sitelens_scores) are set directly, and a synthetic site_context is passed in.  Covers the
score averaging + color banding (GOOD/OK/BAD), the section/attachment assembly, gauge PNG
generation, and the "configure more paths" notice.
"""
import datetime
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SITE = "its-wws-test1"
PORTAL_ID = 101
TS = datetime.datetime(2026, 3, 20, 10, 30)


@pytest.fixture
def sitelens(psh):
    path = Path(psh.__file__).resolve().parents[1] / "check" / "umich" / "sitelens.py"
    loader = SourceFileLoader("umich_sitelens_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _score(a, p, bp, seo, cfg_id):
    return {
        "configuration_id": cfg_id,
        "accessibility_score": a,
        "performance_score": p,
        "best_practices_score": bp,
        "seo_score": seo,
        "timestamp": TS,
    }


def test_create_gauge_image_returns_png(sitelens):
    for value, color in [(95, sitelens.GOOD_SCORE_COLOR), (60, sitelens.OK_SCORE_COLOR), (10, sitelens.BAD_SCORE_COLOR)]:
        img = sitelens.create_gauge_image(value, color, "Test")
        assert isinstance(img, bytes)
        assert img[:8] == b"\x89PNG\r\n\x1a\n"  # PNG signature


def test_scores_section_and_attachments(sitelens, reset_sc):
    sc = reset_sc
    sc.config = {"UMich": {"portal": {"sites": {SITE: {"id": PORTAL_ID}}}}}
    sitelens.sitelens_configured_scans_by_site = {PORTAL_ID: [1, 2]}
    # Per-scan scores DIFFER, so the cross-scan averaging is genuinely exercised (a "use only the
    # first/last scan" bug would give different values and fail).  Means -> accessibility 90 (GOOD),
    # performance 70 (OK), best_practices 40 (BAD), seo 100 (GOOD).
    sitelens.sitelens_scores = {
        1: _score(0.80, 0.60, 0.30, 1.00, 1),
        2: _score(1.00, 0.80, 0.50, 1.00, 2),
    }
    ctx = reset_sc.SiteContext({"name": SITE})

    sitelens.check_sitelens_scores(ctx)

    # One inline PNG attachment per score (4), each with a cid.
    assert len(ctx["attachments"]) == 4
    for att in ctx["attachments"]:
        assert att["maintype"] == "image" and att["subtype"] == "png"
        assert att["disposition"] == "inline"
        assert att["cid"] and att["data"][:8] == b"\x89PNG\r\n\x1a\n"

    assert len(ctx["sections"]) == 1
    section = ctx["sections"][0]
    assert section["heading"] == "SiteLens"
    # Averaged scores appear in the plaintext, exercising each color band.
    for band in ("90 / 100", "70 / 100", "40 / 100", "100 / 100"):
        assert band in section["text"]
    # HTML references the inline images by cid.
    assert section["content"].count("cid:") == 4
    # P9 (link-name): every gauge <img> (each wrapped in an anchor) must carry a non-empty
    # alt so the anchor has a discernible name.  Guards against re-introducing a text-less link.
    import re
    imgs = re.findall(r"<img\b[^>]*>", section["content"])
    assert imgs
    for tag in imgs:
        m = re.search(r'alt="([^"]*)"', tag)
        assert m and m.group(1).strip(), f"gauge img missing non-empty alt: {tag}"


def test_urls_notice_when_too_few_paths(sitelens, reset_sc):
    sc = reset_sc
    sc.config = {"UMich": {"portal": {"sites": {SITE: {"id": PORTAL_ID}}}}}
    sitelens.sitelens_configured_scans_by_site = {PORTAL_ID: [1, 2]}  # 2 < 4 -> notice
    ctx = reset_sc.SiteContext({"name": SITE})

    sitelens.check_sitelens_urls(ctx)

    assert len(ctx["notices"]) == 1
    assert ctx["notices"][0]["short"] == "add paths to SiteLens"


def test_no_urls_notice_when_enough_paths(sitelens, reset_sc):
    sc = reset_sc
    sc.config = {"UMich": {"portal": {"sites": {SITE: {"id": PORTAL_ID}}}}}
    sitelens.sitelens_configured_scans_by_site = {PORTAL_ID: [1, 2, 3, 4]}  # >= 4 -> no notice
    ctx = reset_sc.SiteContext({"name": SITE})

    sitelens.check_sitelens_urls(ctx)

    assert ctx["notices"] == []
