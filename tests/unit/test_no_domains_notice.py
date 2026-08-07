"""psh.no_domains_notice unit tests.

The pure `no-domains` Notice builder extracted from main()'s B29 emission
(development/2026-08-07-main-extraction/SPEC.md section 5.3, R3.6d -- the Spine's
named-extraction rule: the emission had no seam above the golden, and
SiteContext.add_notice projects a Notice into a six-key render dict immediately, so
nothing at the fetch_site_domains seam returns a Notice to assert on).

Two of these tests are the reason this seam exists at all:

* test_the_literal_interior_stays_at_column_16 is the Invariant 8 instrument (SPEC R3.6c
  / section 8.3).  The html/text literal is rendered into 3 of the 4 e2e goldens
  (test_golden, test_golden_drupal, test_golden_nonumich -- NOT test_golden_cdn_change),
  and a re-indent of it changes the email 4,000 site owners receive.  `git diff -w` is
  blind to exactly that change (CLAUDE.md section Conventions & gotchas), so the column is
  asserted directly here.
* test_a_non_dict_domains_payload_suppresses_the_notice covers the load-bearing outer
  isinstance guard (R3.6b), which had NO test at any tier before this file: DnsFacts is
  all-empty for any non-dict domain:list payload, so without the guard a malformed payload
  emits a false "paid plan but does not have any custom domains connected" ALERT to the
  owner.
"""
import pytest

pytestmark = pytest.mark.unit

SITE = {"name": "its-wws-test1", "id": "abc123", "framework": "wordpress"}
# The shape terminus("domain:list") really returns: a dict keyed by domain id.
DOMAINS = {"its-wws-test1.pantheonsite.io": {"type": "platform", "id": "its-wws-test1.pantheonsite.io"}}


def test_paid_plan_with_no_custom_domains_returns_the_alert(psh):
    notice = psh.no_domains_notice(SITE, DOMAINS, [])
    assert notice is not None
    assert notice.code == "no-domains"
    assert notice.severity == "alert"
    assert notice.short == "no domains connected"
    # No csv_extra: the historical -notices.csv row for this code is `site,no-domains`
    # with nothing after it (contrast no-primary-domain's one empty field).
    assert notice.csv_extra == ()


def test_the_notice_projects_to_the_historical_csv_row(psh, reset_sc):
    ctx = reset_sc.SiteContext(SITE)
    ctx.add_notice(psh.no_domains_notice(SITE, DOMAINS, []))
    assert ctx["notices"][0]["csv"] == f"{SITE['name']},no-domains"


def test_at_least_one_custom_domain_suppresses_the_notice(psh):
    assert psh.no_domains_notice(SITE, DOMAINS, ["www.example.com"]) is None


@pytest.mark.parametrize(
    "payload",
    [[], ["a.example.com"], "", "not a dict", None, 0],
    ids=["empty-list", "json-list", "empty-string", "string", "none", "zero"],
)
def test_a_non_dict_domains_payload_suppresses_the_notice(psh, payload):
    """R3.6b: the outer isinstance(domains, dict) guard is LOAD-BEARING, not defensive.

    classify_domains returns an all-empty DnsFacts for any non-dict payload, so
    custom_domains is [] here for every one of these -- the inner test alone would fire the
    ALERT.  Removing the outer guard tells the owner their paid site has no custom domains
    connected when the run never established that."""
    assert psh.no_domains_notice(SITE, payload, []) is None


def test_the_literal_interior_stays_at_column_16(psh):
    """Invariant 8 (SPEC R3.6c / section 8.3).

    Every interior line of the html= and text= f-strings -- and both closing triple
    quotes -- sits at column 16 counted from the start of the line, WHATEVER the enclosing
    def/if frame.  Moving the literal out of main() moves the frame; it must not move the
    literal.  `git diff -w` cannot see a violation (a line that only gained leading
    whitespace is precisely what -w ignores), and the goldens catch it only after the fact,
    so this asserts the bytes directly."""
    notice = psh.no_domains_notice(SITE, DOMAINS, [])
    assert notice is not None
    for field, body in (("html", notice.html), ("text", notice.text)):
        lines = body.splitlines()
        assert lines[0] == "", f"{field}: the literal must open immediately after f\"\"\""
        interior = [line for line in lines[1:] if line.strip()]
        assert len(interior) >= 3, f"{field}: expected the multi-line literal, got {interior!r}"
        for line in interior:
            indent = len(line) - len(line.lstrip(" "))
            assert indent == 16, f"{field}: interior line at column {indent}, expected 16: {line!r}"
        # The CLOSING triple quote's own line is interior whitespace too: it is what makes
        # the string end in "\n" + 16 spaces, and it is in the goldens.
        assert lines[-1] == " " * 16, f"{field}: closing quote line is {lines[-1]!r}, expected 16 spaces"


def test_the_alert_body_names_the_site_and_the_remedy(psh):
    """Non-vacuous companion to the column assertion: the column test would still pass on
    an empty-but-correctly-indented literal, so pin the substance the owner reads."""
    notice = psh.no_domains_notice(SITE, DOMAINS, [])
    assert notice is not None
    assert "its-wws-test1 is on a paid plan but does not have any custom domains connected." in notice.html
    assert "downgrade the site's plan to Sandbox to save" in notice.html
    assert "its-wws-test1 is on a paid plan but does not have" in notice.text
