"""Non-U-M golden: prove a deployment with [UMich] disabled and generic [Email] produces a
report driven by config, not U-M literals (P8).

Renders its-wws-test1 with tests/fixtures/config/minimal-nonumich.toml (no [UMich] section;
generic [Email]/[SMTP]).  Assertions are scoped to what P8 actually changes:
  * the MIME From / Reply-to / dry-run To and the inline-image msgid domain come from [Email];
  * the P8b-guarded Cloudflare-cache doc URLs (node/5114, node/4242) do not appear.
The email template still hardcodes some U-M branding (its.umich.edu, node/4705,
webmaster@umich.edu in the body) -- that is deferred template debt, so this does NOT assert
"no umich.edu anywhere".
"""
import email
import email.policy

import pytest

from conftest import (
    E2E_DATE,
    E2E_SITE,
    E2E_SITE_ID,
    E2E_SMTP_USERNAME,
    MINIMAL_CONFIG,
    make_workdir,
    run_program,
    seed_traffic,
)

pytestmark = pytest.mark.e2e

NONUMICH_CONFIG = MINIMAL_CONFIG.parent / "minimal-nonumich.toml"


@pytest.fixture(scope="module")
def nonumich_render(tmp_path_factory):
    work = make_workdir(tmp_path_factory.mktemp("nonumich"))
    run_program(["--create-tables", "--config", str(NONUMICH_CONFIG)], cwd=work)
    seed_traffic(work / "test.db", site_id=E2E_SITE_ID)
    proc = run_program(
        [E2E_SITE, "--date", E2E_DATE, "--smtp-username", E2E_SMTP_USERNAME,
         "--config", str(NONUMICH_CONFIG)],
        cwd=work,
    )
    build = work / "build"
    return {
        "proc": proc,
        "html": build / f"{E2E_SITE}.html",
        "txt": build / f"{E2E_SITE}.txt",
        "eml": build / f"{E2E_SITE}.eml",
    }


def test_nonumich_render_succeeds(nonumich_render):
    assert nonumich_render["proc"].returncode == 0, nonumich_render["proc"].stderr
    assert "Traceback" not in nonumich_render["proc"].stderr


def test_nonumich_html_matches_golden(nonumich_render, normalize_html, snapshot):
    html = normalize_html(nonumich_render["html"].read_text())
    assert html == snapshot


def test_nonumich_txt_matches_golden(nonumich_render, snapshot):
    assert nonumich_render["txt"].read_text() == snapshot


def test_headers_come_from_email_config(nonumich_render):
    msg = email.message_from_bytes(nonumich_render["eml"].read_bytes(), policy=email.policy.default)
    assert str(msg["From"]) == "Example Web Team <webteam@example.edu>"
    assert msg["Reply-to"] == "webteam@example.edu"
    assert str(msg["To"]) == "ops@example.edu, testuser@example.edu"
    # No U-M sender identity leaks into the moved headers.
    assert "umich.edu" not in str(msg["From"])
    assert "umich.edu" not in str(msg["Reply-to"])


def test_msgid_domain_from_config(nonumich_render):
    msg = email.message_from_bytes(nonumich_render["eml"].read_bytes(), policy=email.policy.default)
    cids = [
        p.get("Content-ID") for p in msg.walk()
        if p.get_content_maintype() == "image" and p.get("Content-ID")
    ]
    assert cids
    assert all(c.endswith("@reports.example.edu>") for c in cids)


def test_no_guarded_umich_doc_urls(nonumich_render):
    html = nonumich_render["html"].read_text()
    # The P8b-guarded Cloudflare-cache checks link to these U-M docs; absent for a non-U-M run.
    assert "node/5114" not in html
    assert "node/4242" not in html
