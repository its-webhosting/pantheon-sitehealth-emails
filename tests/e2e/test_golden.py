"""Golden tier: snapshot the rendered report so unintended rendering drift fails loudly
(SPEC §9 `golden`, §5.9).

The HTML is normalized (make_msgid CIDs -> placeholder) before snapshotting; the .txt is
already deterministic.  Regenerate deliberately with `./run-tests --update-goldens`.
"""
import pytest

pytestmark = pytest.mark.e2e


def test_rendered_html_matches_golden(rendered_report, normalize_html, snapshot):
    html = normalize_html(rendered_report["html"].read_text())
    assert html == snapshot


def test_rendered_txt_matches_golden(rendered_report, snapshot):
    assert rendered_report["txt"].read_text() == snapshot
