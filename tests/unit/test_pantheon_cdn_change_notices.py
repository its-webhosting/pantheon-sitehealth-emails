import pytest

from helpers.checkload import load_check_module

pytestmark = pytest.mark.unit


@pytest.fixture
def notices(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "notices", "pcc_notices_probe", request)


@pytest.fixture
def findings(notices):
    F = notices.Finding
    return [
        F("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
          ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], []),
        F("backstage.its.umich.edu", "cloudflare", "live-its-backstage.pantheonsite.io",
          ["23.185.0.2"], ["2620:12a:8000::2", "2620:12a:8001::2"], []),
    ]


def test_notice_shape(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert n["type"] == "info"
    assert n["csv"] == "s,pantheon-cdn-change,occb.bus.umich.edu,backstage.its.umich.edu"
    assert n["short"] == "Pantheon CDN change: replace CNAME records"
    assert n["text"]                                    # bespoke plaintext, not html2text'd
    assert notices.DOCS_URL in n["message"] and notices.DOCS_URL in n["text"]


def test_notices_module_is_pure(notices):
    # It must not drag dnspython or terminus into the notice builder.  Assert on the MODULE
    # objects it actually imported -- `"dns.resolver" not in str(vars(notices))` looks like a
    # test and is vacuous (vars() keys are attribute NAMES).
    import types
    imported = {v.__name__ for v in vars(notices).values() if isinstance(v, types.ModuleType)}
    assert imported == {"html"}
    assert not hasattr(notices, "chain") and not hasattr(notices, "pantheon")


def test_every_body_cell_is_left_aligned_and_labelled(notices, findings):
    # email_template.html's .responsive-table defaults to text-align: right; only the rt-* classes
    # override it.  A bare <td> therefore right-aligns under its left-aligned header.  Each cell
    # also carries an rt-data-header div, which is hidden on desktop and becomes the row label when
    # the table stacks into one column on a phone (there is no <thead> left to label the value).
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    cells = n["message"].count("<td>")
    assert cells == 3 * len(findings)                       # Domain / Change it in / records
    assert n["message"].count('<div class="rt-data rt-plan">') == cells
    assert n["message"].count('<div class="rt-data-header rt-plan">') == cells
    assert "<td>" not in n["message"].replace(
        '<td><div class="rt-data-header rt-plan">', "")     # no bare, unclassed cell survives
    for header in ("Domain", "Change it in", "Replace the CNAME record with"):
        assert n["message"].count(header) == 1 + len(findings)   # the <th> plus one label per row


def test_where_label_matrix(notices):
    assert notices.where_label("dns", umich=True) == "DNS"
    assert notices.where_label("dns", umich=False) == "DNS"
    assert notices.where_label("cloudflare", umich=True) == "U-M Cloudflare"
    assert notices.where_label("cloudflare", umich=False) == "our (non-Pantheon) Cloudflare"
    assert notices.where_label("both", umich=True) == "DNS and U-M Cloudflare"
    assert notices.where_label("both", umich=False) == "DNS and our (non-Pantheon) Cloudflare"


def test_where_label_rejects_an_unknown_value(notices):
    # A silent fall-through would print a WRONG instruction ("DNS and ...") to a site owner.
    with pytest.raises(ValueError):
        notices.where_label("elsewhere", umich=True)


def test_addresses_and_domains_appear_in_both_renderings(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for body in (n["message"], n["text"]):
        assert "occb.bus.umich.edu" in body
        assert "23.185.0.4" in body
        assert "2620:12a:8001::4" in body
        assert "backstage.its.umich.edu" in body
        assert "23.185.0.2" in body


def test_umich_before_cutoff_promises_maintenance(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert "ITS will make these changes for you" in n["message"]
    assert "ITS will make these changes for you" in n["text"]
    # The internal cutoff DATE is never disclosed to owners.
    assert "September" not in n["message"] and "2026-09-15" not in n["message"]


def test_umich_on_or_after_cutoff_gets_generic_instruction(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=False)
    assert "ITS will make these changes" not in n["message"]
    assert "Please replace each CNAME record above" in n["message"]
    assert "U-M Cloudflare" in n["message"]             # still U-M terminology


def test_generic_has_no_umich_leakage(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=False, before_cutoff=True)
    assert "our (non-Pantheon) Cloudflare" in n["message"]
    for body in (n["message"], n["text"]):
        assert "U-M" not in body
        assert "ITS" not in body


def test_notice_does_not_explain_the_transition(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for forbidden in ("Orange to Orange", "Orange-to-Orange", "Fastly to Cloudflare"):
        assert forbidden not in n["message"]


def test_missing_records_render_as_unavailable(notices):
    # F4: domain:dns failed or had no row for this FQDN.
    F = notices.Finding
    f = [F("x.example.org", "dns", "live-x.pantheonsite.io", [], [], [])]
    umich = notices.cdn_change_notice("s", f, umich=True, before_cutoff=True)
    generic = notices.cdn_change_notice("s", f, umich=False, before_cutoff=True)
    assert "unavailable" in umich["message"] and "please contact us" in umich["message"]
    assert "unavailable" in generic["message"]
    assert "x.example.org" in generic["message"]        # the finding is STILL reported


def test_cname_only_records_render_as_a_cname_not_unavailable(notices):
    # F14: an already-migrated site.  Pantheon HAS an answer -- show it.  Rendering "unavailable"
    # here would tell the owner we failed when we did not.
    F = notices.Finding
    f = [F("x.example.org", "dns", "live-x.pantheonsite.io", [], [],
           ["fe.cfp2c.edge.pantheon.io"])]
    for umich in (True, False):
        n = notices.cdn_change_notice("s", f, umich=umich, before_cutoff=True)
        for body in (n["message"], n["text"]):
            assert "fe.cfp2c.edge.pantheon.io" in body
            assert "CNAME" in body
            assert "unavailable" not in body


def test_fqdn_html_escaped(notices):
    F = notices.Finding
    f = [F("a<b>.example.org", "dns", "live-x.pantheonsite.io", ["1.2.3.4"], [], [])]
    n = notices.cdn_change_notice("s", f, umich=False, before_cutoff=False)
    assert "&lt;b&gt;" in n["message"]
    assert "<b>" not in n["message"]
