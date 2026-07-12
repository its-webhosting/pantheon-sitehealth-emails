"""Syrupy snapshots of the CDN-change notice as rendered content.

Built by the real notices.py, added through the real SiteContext.add_notice, and pushed through
the real email_template.html Jinja render in-process -- the test_cachecheck_notice_render.py
precedent.  A dict-level snapshot alone would not prove the table survives the template.

This file pins the U-M copy variants; the 4th e2e golden pins the GENERIC one (its config has no
[UMich] section).  Between them, every variant that can be sent is frozen.
"""
from pathlib import Path

import pytest
from jinja2 import Template

from helpers.checkload import load_check_module

pytestmark = pytest.mark.integration

SITE = "bus-occb"


@pytest.fixture
def notices(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "notices", "pcc_render_probe", request)


@pytest.fixture
def findings(notices):
    F = notices.Finding
    return [
        F("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
          ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], []),
        F("backstage.its.umich.edu", "cloudflare", "live-its-backstage.pantheonsite.io",
          ["23.185.0.2"], ["2620:12a:8000::2", "2620:12a:8001::2"], []),
        F("both.example.org", "both", "live-x.pantheonsite.io", ["23.185.0.9"], [], []),
        # F14: an already-migrated site -- Pantheon requires a CNAME, not addresses.
        F("migrated.example.org", "dns", "live-m.pantheonsite.io", [], [],
          ["fe.cfp2c.edge.pantheon.io"]),
        # F4: domain:dns had no row at all for this one -> "unavailable", still reported.
        F("unresolvable.example.org", "dns", "live-y.pantheonsite.io", [], [], []),
    ]


@pytest.mark.parametrize(
    "umich,before_cutoff",
    [(True, True), (True, False), (False, False)],
    ids=["umich-before-cutoff", "umich-after-cutoff", "generic"])
def test_notice_message_and_text_snapshot(
        notices, findings, reset_sc, snapshot, umich, before_cutoff):
    built = notices.cdn_change_notice(SITE, findings, umich=umich, before_cutoff=before_cutoff)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(built))
    notice = ctx["notices"][0]
    assert notice["icon"] == "&#x1F50E;"      # magnifying glass, from the info type default
    assert notice["message"] == snapshot
    assert notice["text"] == snapshot         # the bespoke plaintext, NOT html2text output


def test_notice_renders_through_the_real_template(psh, notices, findings, reset_sc):
    built = notices.cdn_change_notice(SITE, findings, umich=True, before_cutoff=True)
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(built))
    template = Template((Path(psh.__file__).parent / "email_template.html").read_text())
    html_body = template.render(site_name=SITE, notices=ctx["notices"], sections=[], news=[])
    assert 'class="responsive-table site-updates"' in html_body     # the table survived
    assert "occb.bus.umich.edu" in html_body and "23.185.0.4" in html_body
    assert notices.DOCS_URL in html_body
    assert "unavailable" in html_body                               # the F4 row survived
    assert "CNAME fe.cfp2c.edge.pantheon.io" in html_body           # the F14 row survived


def test_injected_markup_cannot_escape_the_table_cell(notices, reset_sc):
    F = notices.Finding
    evil = 'a.example.org"><script>alert(1)</script>'
    built = notices.cdn_change_notice(
        SITE, [F(evil, "dns", "live-x.pantheonsite.io", ["1.2.3.4"], [], [])],
        umich=False, before_cutoff=False)
    assert "<script>" not in built["message"]
    assert "&lt;script&gt;" in built["message"]
