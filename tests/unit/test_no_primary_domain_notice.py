"""psh.no_primary_domain_notice unit tests (campaign I10, SPEC D-i10-3).

The pure helper extracted from main()'s B30 no-primary-domain emission (the Spine's
named-extraction rule: the emission has no seam above the golden).  No existing test at
any tier covered this notice before this increment (verified: grep -rln
"no-primary-domain" tests/ was empty)."""
import pytest

pytestmark = pytest.mark.unit

SITE = {"name": "its-wws-test1", "id": "abc123", "framework": "drupal9"}


def test_gate_true_returns_the_notice(psh):
    notice = psh.no_primary_domain_notice(SITE, ["a.example.com", "b.example.com"], "", False)
    assert notice is not None
    assert notice.code == "no-primary-domain"
    assert notice.severity == "info"   # rewritten from 'type': 'info' at I14c; nothing else pins it
    # The trailing empty csv field is real and load-bearing (SPEC I14c §2.1): the row has
    # always ended in a comma, so csv_extra carries one empty field.
    assert notice.csv_extra == ("",)


def test_gate_true_projects_to_the_historical_csv_row(psh, reset_sc):
    # End-to-end pin of the exact -notices.csv row, through the projection that now owns
    # the site-name half (instrument I3).
    ctx = reset_sc.SiteContext(SITE)
    ctx.add_notice(psh.no_primary_domain_notice(
        SITE, ["a.example.com", "b.example.com"], "", False))
    assert ctx["notices"][0]["csv"] == f"{SITE['name']},no-primary-domain,"


def test_multisite_suppresses_the_notice(psh):
    notice = psh.no_primary_domain_notice(
        SITE, ["a.example.com", "b.example.com"], "", True)
    assert notice is None


def test_at_most_one_custom_domain_suppresses_the_notice(psh):
    notice = psh.no_primary_domain_notice(SITE, ["a.example.com"], "", False)
    assert notice is None


def test_primary_domain_set_suppresses_the_notice(psh):
    notice = psh.no_primary_domain_notice(
        SITE, ["a.example.com", "b.example.com"], "a.example.com", False)
    assert notice is None


def test_wordpress_network_framework_suppresses_the_notice(psh):
    site = {**SITE, "framework": "wordpress_network"}
    notice = psh.no_primary_domain_notice(
        site, ["a.example.com", "b.example.com"], "", False)
    assert notice is None
