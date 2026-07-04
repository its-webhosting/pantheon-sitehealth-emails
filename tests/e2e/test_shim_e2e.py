"""End-to-end tier: a full subprocess run of the program against the shim (SPEC §9 `e2e`).

Exercises the real argument-building / subprocess path, the render -> php-inline -> MIME
pipeline, and artifact writing — fully offline.  Also the standing regression for the two
non-UMich render-path bugs (the run would crash on the pre-fix code).
"""
import pytest

pytestmark = pytest.mark.e2e


def test_full_pipeline_produces_artifacts(rendered_report):
    proc = rendered_report["proc"]
    assert proc.returncode == 0, f"program failed:\n{proc.stdout}\n{proc.stderr}"
    for key in ("html", "txt", "eml", "inline2"):
        path = rendered_report[key]
        assert path.exists(), f"missing artifact: {path}"
        assert path.stat().st_size > 0, f"empty artifact: {path}"


def test_rendered_html_has_expected_report_content(rendered_report):
    html = rendered_report["html"].read_text()
    assert "Pantheon Traffic Report" in html
    assert "its-wws-test1" in html


def test_eml_is_addressed_in_dev_mode_not_for_real(rendered_report):
    # Without --for-real the To: is the dev user, never the site owners (safety).
    eml = rendered_report["eml"].read_text(errors="replace")
    assert "testuser@umich.edu" in eml  # our fixed --smtp-username
