"""Golden tier for the Drupal (drush) path — its-wws-test2 (test-suite SPEC §7.5).

Mirrors the WordPress golden but drives the entire drush code path, which the WordPress
fixtures never touch.  Fixtures live in tests/fixtures/terminus-drupal (recorded read-only via
`python tests/tools/record.py --drupal`); the HTML is CID-normalized before snapshotting.
Regenerate deliberately with `./run-tests --update-goldens`.
"""
import pytest

pytestmark = pytest.mark.e2e


def test_drupal_report_renders(rendered_report_drupal):
    proc = rendered_report_drupal["proc"]
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    assert rendered_report_drupal["html"].read_text().strip()
    assert rendered_report_drupal["txt"].read_text().strip()


def test_drupal_html_matches_golden(rendered_report_drupal, normalize_html, snapshot):
    html = normalize_html(rendered_report_drupal["html"].read_text())
    assert html == snapshot


def test_drupal_txt_matches_golden(rendered_report_drupal, snapshot):
    assert rendered_report_drupal["txt"].read_text() == snapshot
