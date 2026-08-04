import inspect
import re

import pytest
from helpers.checkload import load_check_module

pytestmark = pytest.mark.unit


@pytest.fixture
def notices(psh, reset_sc, request):
    return load_check_module(
        psh, "pantheon_cdn_change", "notices", "pcc_notices_probe", request)


@pytest.fixture
def findings(notices):
    finding = notices.Finding
    return [
        finding("occb.bus.umich.edu", "dns", "live-bus-occb.pantheonsite.io",
          ["23.185.0.4"], ["2620:12a:8000::4", "2620:12a:8001::4"], []),
        finding("backstage.its.umich.edu", "cloudflare", "live-its-backstage.pantheonsite.io",
          ["23.185.0.2"], ["2620:12a:8000::2", "2620:12a:8001::2"], []),
    ]


def test_fqdns_become_separate_csv_fields(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert n.code == "pantheon-cdn-change"
    assert n.csv_extra == ("occb.bus.umich.edu", "backstage.its.umich.edu")


def test_empty_findings_yield_no_csv_fields(notices):
    # Documented precondition (SPEC I14c §2.1, D-i14c-11): the only call site returns early on
    # `not findings` (check/pantheon_cdn_change/hook.py:50), so this case is unreachable today.
    # Pre-I14c the csv was f"{site},pantheon-cdn-change," + ",".join(...), which left a TRAILING
    # COMMA on an empty finding list; csv_extra=() leaves no trailing field.  Pinned so that
    # divergence is explicit rather than latent (PD#3's zero-length shadow).
    n = notices.cdn_change_notice("s", [], umich=True, before_cutoff=True)
    assert n.code == "pantheon-cdn-change"
    assert n.csv_extra == ()


def test_notice_shape(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert n.severity == "info"
    assert n.code == "pantheon-cdn-change"
    assert n.csv_extra == ("occb.bus.umich.edu", "backstage.its.umich.edu")
    assert n.short == "Pantheon CDN change: replace CNAME records"
    assert n.text                                    # bespoke plaintext, not html2text'd
    assert notices.DOCS_URL in n.html and notices.DOCS_URL in n.text


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
    cells = n.html.count("<td>")
    assert cells == 3 * len(findings)                       # Domain / Change it in / records
    assert n.html.count('<div class="rt-data rt-plan">') == cells
    assert n.html.count('<div class="rt-data-header rt-plan">') == cells
    assert "<td>" not in n.html.replace(
        '<td><div class="rt-data-header rt-plan">', "")     # no bare, unclassed cell survives
    for header in ("Domain", "Change it in", "Replace the CNAME record with"):
        assert n.html.count(header) == 1 + len(findings)   # the <th> plus one label per row


def test_intro_names_the_cname_target(notices, findings):
    # The owner should not have to go look up what their CNAME currently points at.
    for umich in (True, False):
        n = notices.cdn_change_notice("bus-occb", findings, umich=umich, before_cutoff=True)
        for body in (n.html, n.text):
            assert "still use a CNAME record pointing at" in body
            assert "live-bus-occb.pantheonsite.io" in body


def test_intro_lists_every_distinct_target(notices):
    # Should never happen (detect.py warns when it does), but if two domains point at different
    # legacy names the sentence must name BOTH -- naming only one would be a lie about the other.
    finding = notices.Finding
    f = [finding("a.example.org", "dns", "live-aaa.pantheonsite.io", ["1.2.3.4"], [], []),
         finding("b.example.org", "dns", "live-bbb.pantheonsite.io", ["1.2.3.4"], [], []),
         finding("c.example.org", "dns", "live-aaa.pantheonsite.io", ["1.2.3.4"], [], [])]
    n = notices.cdn_change_notice("s", f, umich=False, before_cutoff=False)
    # The plaintext puts the target list on its own line (the paragraph wraps at ~75 columns).
    assert "pointing at\nlive-aaa.pantheonsite.io and live-bbb.pantheonsite.io:" in n.text
    assert "pointing at live-aaa.pantheonsite.io and live-bbb.pantheonsite.io:" in n.html
    assert n.text.count("live-aaa.pantheonsite.io") == 1     # distinct, first-seen order


def test_target_is_html_escaped_in_the_intro(notices):
    finding = notices.Finding
    f = [finding("a.example.org", "dns", "live-<script>.pantheonsite.io", ["1.2.3.4"], [], [])]
    n = notices.cdn_change_notice("s", f, umich=False, before_cutoff=False)
    assert "<script>" not in n.html
    assert "&lt;script&gt;" in n.html


def test_intro_stays_grammatical_with_no_target(notices):
    # Defensive: a finding always carries a target, but "pointing at :" must never be rendered.
    finding = notices.Finding
    f = [finding("a.example.org", "dns", "", ["1.2.3.4"], [], [])]
    n = notices.cdn_change_notice("s", f, umich=False, before_cutoff=False)
    assert "pointing at\nthe legacy Pantheon GCDN:" in n.text
    assert "pointing at the legacy Pantheon GCDN:" in n.html
    assert "pointing at :" not in n.text and "pointing at :" not in n.html


def test_where_label_matrix(notices):
    assert notices.where_label("dns", umich=True) == "DNS"
    assert notices.where_label("dns", umich=False) == "DNS"
    assert notices.where_label("cloudflare", umich=True) == "U-M Cloudflare"
    assert notices.where_label("cloudflare", umich=False) == "our (non-Pantheon) Cloudflare"
    assert notices.where_label("both", umich=True) == "DNS and U-M Cloudflare"
    assert notices.where_label("both", umich=False) == "DNS and our (non-Pantheon) Cloudflare"


def test_where_label_rejects_an_unknown_value(notices):
    # A silent fall-through would print a WRONG instruction ("DNS and ...") to a site owner.
    with pytest.raises(ValueError):  # noqa: PT011 -- asserts the named ValueError is raised; a match= would over-constrain the message the test deliberately does not pin
        notices.where_label("elsewhere", umich=True)


def test_addresses_and_domains_appear_in_both_renderings(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for body in (n.html, n.text):
        assert "occb.bus.umich.edu" in body
        assert "23.185.0.4" in body
        assert "2620:12a:8001::4" in body
        assert "backstage.its.umich.edu" in body
        assert "23.185.0.2" in body


def test_umich_before_cutoff_promises_maintenance(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    assert "ITS will make these changes for you" in n.html
    assert "ITS will make these changes for you" in n.text


def test_the_internal_cutoff_date_cannot_reach_either_rendering(notices, findings):
    """The cutoff DATE is never disclosed to owners -- it only selects the copy variant.

    The previous version of this assertion was `"September" not in n.html and "2026-09-15" not
    in n.html`, and it was weak in three separate ways:

      1. It hardcoded the spelling of ONE value of hook.UMICH_MAINTENANCE_CUTOFF, so moving the
         constant (the edit docs/pantheon-cdn-change.md explicitly anticipates) left it guarding
         nothing at all -- stale by construction.
      2. `and` binds both operands to n.html, so the PLAINTEXT body was never checked.  That is
         the body read without following links, and the one where a leaked date would be barest.
      3. It tested a string where the real guarantee is structural, so it could not fail for the
         reason it existed.

    What actually makes the leak impossible is the module boundary: cdn_change_notice receives
    `before_cutoff` as a BOOL and never sees a date at all, so there is nothing to interpolate.
    That is what this pins, plus a value-independent sweep for any ISO-8601 date in either body.
    The complement -- that the real constant's own rendering stays out of the copy even after
    someone moves it -- is pinned where the constant is reachable, in
    tests/integration/test_check_pantheon_cdn_change.py.
    """
    parameters = inspect.signature(notices.cdn_change_notice).parameters
    assert "before_cutoff" in parameters
    assert parameters["before_cutoff"].annotation is bool
    assert not [name for name in parameters if "date" in name or "cutoff_" in name]

    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for body in (n.html, n.text):
        assert not re.search(r"\d{4}-\d{2}-\d{2}", body)


def test_umich_on_or_after_cutoff_gets_generic_instruction(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=False)
    assert "ITS will make these changes" not in n.html
    assert "Please replace each CNAME record above" in n.html
    assert "U-M Cloudflare" in n.html             # still U-M terminology


def test_generic_has_no_umich_leakage(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=False, before_cutoff=True)
    assert "our (non-Pantheon) Cloudflare" in n.html
    for body in (n.html, n.text):
        assert "U-M" not in body
        assert "ITS" not in body


def test_notice_does_not_explain_the_transition(notices, findings):
    n = notices.cdn_change_notice("s", findings, umich=True, before_cutoff=True)
    for forbidden in ("Orange to Orange", "Orange-to-Orange", "Fastly to Cloudflare"):
        assert forbidden not in n.html


def test_missing_records_render_as_unavailable(notices):
    # F4: domain:dns failed or had no row for this FQDN.
    finding = notices.Finding
    f = [finding("x.example.org", "dns", "live-x.pantheonsite.io", [], [], [])]
    umich = notices.cdn_change_notice("s", f, umich=True, before_cutoff=True)
    generic = notices.cdn_change_notice("s", f, umich=False, before_cutoff=True)
    assert "unavailable" in umich.html and "please contact us" in umich.html
    assert "unavailable" in generic.html
    assert "x.example.org" in generic.html        # the finding is STILL reported
    # A non-U-M owner has no "contact us" channel, so a bare "unavailable" would be a dead end:
    # point them at where the value actually lives.  In BOTH renderings.
    for body in (generic.html, generic.text):
        assert "Pantheon dashboard" in body
        assert "contact us" not in body


def test_cname_only_records_render_as_a_cname_not_unavailable(notices):
    # F14: an already-migrated site.  Pantheon HAS an answer -- show it.  Rendering "unavailable"
    # here would tell the owner we failed when we did not.
    finding = notices.Finding
    f = [finding("x.example.org", "dns", "live-x.pantheonsite.io", [], [],
           ["fe.cfp2c.edge.pantheon.io"])]
    for umich in (True, False):
        n = notices.cdn_change_notice("s", f, umich=umich, before_cutoff=True)
        for body in (n.html, n.text):
            assert "fe.cfp2c.edge.pantheon.io" in body
            assert "CNAME" in body
            assert "unavailable" not in body


def test_fqdn_html_escaped(notices):
    finding = notices.Finding
    f = [finding("a<b>.example.org", "dns", "live-x.pantheonsite.io", ["1.2.3.4"], [], [])]
    n = notices.cdn_change_notice("s", f, umich=False, before_cutoff=False)
    assert "&lt;b&gt;" in n.html
    assert "<b>" not in n.html
