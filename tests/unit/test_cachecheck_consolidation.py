"""Unit tests for check/cloudflare/notices.py (consolidation + notice assembly + the
U-M/generic language variants + escaping)."""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

pytestmark = pytest.mark.unit

SITE = "its-wws-test1"
DOC = "https://documentation.its.umich.edu/cloudflare-cache-report"

_CACHED = {}


def _load(psh):
    if "m" not in _CACHED:
        path = Path(psh.__file__).parent / "check" / "cloudflare" / "notices.py"
        loader = SourceFileLoader("cachecheck_notices_probe", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHED["m"] = module
    return _CACHED["m"]


@pytest.fixture
def notices(psh):
    return _load(psh)


def _item(item_id, url, kind="page", **params):
    # Production always attaches the cookie names to set-cookie items; mirror that so
    # synthetic items render the same way real ones do.
    if item_id in ("set-cookie", "set-cookie-bypass") and "cookies" not in params:
        params["cookies"] = "sessionid"
    if "cookies" in params and "cookie_count" not in params:
        params["cookie_count"] = len(params["cookies"].split(", "))
    return {"id": item_id, "kind": kind, "url": url, "params": params}


def _sample(pages, asset_pages=None):
    return {"pages": pages, "asset_pages": pages if asset_pages is None else asset_pages}


def _build(notices, items_by_fqdn, *, umich=True, framework="wordpress", extra_pages=3,
           asset_pages=None):
    return notices.build_cache_notices(
        SITE, items_by_fqdn, umich=umich, doc_url=DOC, framework=framework,
        sample_by_fqdn={fqdn: _sample(extra_pages, asset_pages) for fqdn in items_by_fqdn})


def test_identical_signatures_consolidate_into_one_notice(notices):
    out = _build(notices, {
        "a.example.edu": [_item("no-cache-control", "https://a.example.edu/")],
        "b.example.edu": [_item("no-cache-control", "https://b.example.edu/")],
    })
    assert len(out) == 1
    n = out[0]
    assert n["type"] == "info"
    assert n["csv"] == f"{SITE},cloudflare-cache,a.example.edu+b.example.edu,no-cache-control"
    assert "https://a.example.edu/" in n["message"]
    assert "https://b.example.edu/" in n["message"]


def test_different_signatures_get_separate_notices(notices):
    out = _build(notices, {
        "a.example.edu": [_item("no-cache-control", "https://a.example.edu/")],
        "b.example.edu": [_item("set-cookie", "https://b.example.edu/")],
    })
    assert len(out) == 2
    assert out[0]["csv"].startswith(f"{SITE},cloudflare-cache,a.example.edu,")
    assert out[1]["csv"].startswith(f"{SITE},cloudflare-cache,b.example.edu,")


def test_params_are_part_of_identity(notices):
    # Same id, different params -> different signatures -> no consolidation.
    out = _build(notices, {
        "a.example.edu": [_item("short-cache-time", "https://a.example.edu/", seconds=60)],
        "b.example.edu": [_item("short-cache-time", "https://b.example.edu/", seconds=90)],
    })
    assert len(out) == 2


def test_kind_is_part_of_identity(notices):
    out = _build(notices, {
        "a.example.edu": [_item("timeout", "https://a.example.edu/", timeout=5)],
        "b.example.edu": [_item("timeout", "https://b.example.edu/x.js", kind="asset", timeout=5)],
    })
    assert len(out) == 2


def test_fqdns_without_items_get_no_notice(notices):
    assert _build(notices, {"a.example.edu": []}) == []
    assert _build(notices, {}) == []


def test_umich_variant_links_doc_anchor_generic_never(notices):
    items = {"a.example.edu": [_item("set-cookie", "https://a.example.edu/")]}
    um = _build(notices, items, umich=True)[0]["message"]
    generic = _build(notices, items, umich=False)[0]["message"]
    assert f"{DOC}#set-cookie" in um
    assert DOC not in generic
    assert "developer.mozilla.org" in generic  # public docs instead


def test_d15_cms_link_selection(notices):
    items = {"a.example.edu": [_item("no-cache-control", "https://a.example.edu/")]}
    wp = _build(notices, items, umich=True, framework="wordpress")[0]["message"]
    drupal = _build(notices, items, umich=True, framework="drupal10")[0]["message"]
    other = _build(notices, items, umich=True, framework="unknown")[0]["message"]
    assert "node/5114" in wp and "node/4242" not in wp
    assert "node/4242" in drupal and "node/5114" not in drupal
    assert "node/5114" not in other and "node/4242" not in other
    # Generic variants never get the U-M CMS links regardless of framework:
    generic = _build(notices, items, umich=False, framework="wordpress")[0]["message"]
    assert "node/5114" not in generic


def test_duplicate_urls_listed_once_per_finding(notices):
    # Regression (code review): the same sitewide asset can be tested from several pages
    # (requests deliberately un-deduped per the PROMPT), but the owner-visible notice
    # must not repeat the URL.
    url = "https://a.example.edu/style.css"
    out = _build(notices, {"a.example.edu": [
        _item("set-cookie", url, kind="asset"),
        _item("set-cookie", url, kind="asset"),
        _item("set-cookie", "https://a.example.edu/other.css", kind="asset"),
    ]})
    assert len(out) == 1
    # each listed URL appears exactly twice (href + display text) per <li>:
    assert out[0]["message"].count("style.css") == 2
    assert out[0]["message"].count("other.css") == 2


def test_url_list_header_counts_extra_pages_and_pluralizes(notices):
    def header(extra_pages):
        out = _build(notices, {"a.example.edu": [
            _item("no-cache-control", "https://a.example.edu/")]}, extra_pages=extra_pages)
        return out[0]["message"]

    assert "URLs with this issue (checked main page plus 3 random pages linked from it)" \
        in header(3)
    assert "URLs with this issue (checked main page plus 1 random page linked from it)" \
        in header(1)
    assert "URLs with this issue (checked main page only)" in header(0)


def _group_header(notices, sample_by_fqdn, urls_by_fqdn=None):
    """One consolidated notice over two FQDNs with differing sample sizes."""
    urls_by_fqdn = urls_by_fqdn or {f: ["/"] for f in sample_by_fqdn}
    items = {fqdn: [_item("no-cache-control", f"https://{fqdn}{path}") for path in paths]
             for fqdn, paths in urls_by_fqdn.items()}
    out = notices.build_cache_notices(SITE, items, umich=False, doc_url=DOC, framework="",
                                      sample_by_fqdn=sample_by_fqdn)
    assert len(out) == 1  # identical signatures -> one notice
    return out[0]["message"]


def test_url_list_header_says_up_to_when_a_group_disagrees(notices):
    # A group consolidates on item SIGNATURE, so its FQDNs can have sampled different
    # numbers of pages.  Reducing them to one number cannot work: the URL list aggregates
    # URLs from every FQDN, so a min renders a header that contradicts the list below it
    # and a max asserts a sample size no single FQDN reached.  "up to N" is true of all.
    message = _group_header(notices, {"a.example.edu": _sample(1),
                                      "b.example.edu": _sample(3)})
    assert "(checked main page plus up to 3 random pages linked from it)" in message


def test_url_list_header_is_exact_when_a_group_agrees(notices):
    message = _group_header(notices, {"a.example.edu": _sample(2),
                                      "b.example.edu": _sample(2)})
    assert "(checked main page plus 2 random pages linked from it)" in message
    assert "up to" not in message


def test_url_list_header_never_says_main_page_only_above_sub_page_urls(notices):
    # The min() regression: b.example.edu is a bare landing page (0 extra pages) but
    # a.example.edu found the same issue on three sampled sub-pages.  They consolidate,
    # and the header must not claim "checked main page only" above a.example.edu's URLs.
    message = _group_header(
        notices,
        {"a.example.edu": _sample(3), "b.example.edu": _sample(0)},
        {"a.example.edu": ["/", "/about", "/news", "/contact"], "b.example.edu": ["/"]})
    assert "/about" in message and "/news" in message
    assert "checked main page only" not in message
    assert "(checked main page plus up to 3 random pages linked from it)" in message


def test_url_list_header_describes_the_items_own_kind(notices):
    # extra_pages counts PAGES; assets are sampled per class from each checked page, so an
    # asset item's header must not claim its URLs came from the sampled pages.
    out = _build(notices, {"a.example.edu": [
        _item("no-cache-control", "https://a.example.edu/"),
        _item("no-cache-control", "https://a.example.edu/app.js", kind="asset"),
    ]}, extra_pages=2)
    message = out[0]["message"]
    assert "(checked main page plus 2 random pages linked from it)" in message
    assert ("(checked static assets on the main page plus 2 random pages linked from it)"
            in message)

    only_main = _build(notices, {"a.example.edu": [
        _item("cc-private", "https://a.example.edu/app.js", kind="asset")]},
        extra_pages=0)[0]["message"]
    assert "(checked static assets on the main page only)" in only_main


def test_asset_header_uses_the_asset_page_count_not_the_page_count(notices):
    # A picked page that timed out is a CHECKED page (it gets a result item) but is never
    # mined for assets, so pages=1 while asset_pages=0.  The asset header must not claim
    # assets were sampled from a page that was never opened for them.
    out = _build(notices, {"a.example.edu": [
        _item("no-cache-control", "https://a.example.edu/"),
        _item("no-cache-control", "https://a.example.edu/app.js", kind="asset"),
    ]}, extra_pages=1, asset_pages=0)
    message = out[0]["message"]
    assert "(checked main page plus 1 random page linked from it)" in message
    assert "(checked static assets on the main page only)" in message


def test_url_list_is_a_child_of_its_header(notices):
    # The header is an <li> whose child <ul> holds the URLs: that is the only construct
    # that breaks the line in Outlook, keeps the plaintext indented under the finding, and
    # associates the list with its caption for a screen reader.
    message = _build(notices, {"a.example.edu": [
        _item("no-cache-control", "https://a.example.edu/")]}, extra_pages=0)[0]["message"]
    assert "<br>" not in message
    assert "display: block" not in message
    header = "URLs with this issue (checked main page only)"
    nested = (f'<li>{header}<ul style="list-style-type: none;">'
              f'<li><a href="https://a.example.edu/">https://a.example.edu/</a> (page)</li>'
              f'</ul></li>')
    assert nested in message


def test_plaintext_indents_the_header_under_its_finding(psh, reset_sc, notices):
    # Regression for the <br> version, whose header rendered flush at column 0 -- to the
    # LEFT of both its parent bullet and the URLs it introduced.
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(_build(notices, {"a.example.edu": [
        _item("no-cache-control", "https://a.example.edu/")]}, extra_pages=0)[0]))
    lines = [l for l in ctx["notices"][0]["text"].splitlines() if l.strip()]
    finding = next(l for l in lines if "does not send" in l)
    header = next(l for l in lines if "URLs with this issue" in l)
    url = next(l for l in lines if "a.example.edu/>" in l)

    def indent(line):
        return len(line) - len(line.lstrip())

    assert indent(finding) < indent(header) < indent(url)


def test_item_language_agrees_with_the_number_of_urls_listed(notices):
    one = _build(notices, {"a.example.edu": [
        _item("no-cache-control", "https://a.example.edu/")]})[0]["message"]
    assert "This page does not send" in one
    assert "caching it for" in one

    two = _build(notices, {"a.example.edu": [
        _item("no-cache-control", "https://a.example.edu/"),
        _item("no-cache-control", "https://a.example.edu/about")]})[0]["message"]
    assert "These pages do not send" in two
    assert "caching them for" in two
    assert "This page" not in two

    assets = _build(notices, {"a.example.edu": [
        _item("cc-private", "https://a.example.edu/a.js", kind="asset"),
        _item("cc-private", "https://a.example.edu/b.js", kind="asset")]})[0]["message"]
    assert "These static assets' <code>Cache-Control</code> headers contain" in assets


def test_site_config_items_direct_the_owner_site_wide(notices):
    # The listed URLs are only a sample, so items whose fix is a site-wide configuration
    # change must say so rather than implying only those URLs are affected.
    params_by_id = {"short-cache-time": {"seconds": 60},
                    "cc-must-revalidate": {"directive": "must-revalidate"}}
    for item_id in ("no-cache-control", "no-max-age", "short-cache-time", "cc-private",
                    "cc-no-cache", "cc-no-store", "cc-must-revalidate", "expires-short"):
        one = _build(notices, {"a.example.edu": [
            _item(item_id, "https://a.example.edu/", **params_by_id.get(item_id, {}))
        ]})[0]["message"]
        assert ("Apply this to all pages site-wide &mdash; the one listed below is only "
                "what we sampled." in one), item_id

        two = _build(notices, {"a.example.edu": [
            _item(item_id, "https://a.example.edu/x.js", kind="asset",
                  **params_by_id.get(item_id, {})),
            _item(item_id, "https://a.example.edu/y.js", kind="asset",
                  **params_by_id.get(item_id, {})),
        ]})[0]["message"]
        assert ("Apply this to all static assets site-wide &mdash; the ones listed below "
                "are only what we sampled." in two), item_id


def test_uncacheable_directives_lead_with_the_origin_hit_consequence(notices):
    """private/no-cache/no-store all mean Cloudflare never serves the visitor from cache.

    The old text led with the mechanism ("prevents Cloudflare from caching it"), which was
    imprecise for no-cache -- Cloudflare's docs disagree with themselves about whether a
    no-cache response is stored-and-revalidated or bypassed.  What is true under BOTH
    readings, and is what the owner actually pays for, is that every request reaches the
    origin.
    """
    def message(item_id, umich=True):
        return _build(notices, {"a.example.edu": [
            _item(item_id, "https://a.example.edu/p")]}, umich=umich)[0]["message"]

    for item_id in ("cc-private", "cc-no-cache", "cc-no-store"):
        msg = message(item_id)
        assert "every visitor request is passed through to your web server" in msg, item_id
        assert "count toward the Pantheon visit limits" in msg, item_id
        # The imprecise mechanism claim is gone:
        assert "prevents Cloudflare from caching" not in msg, item_id

    # no-cache is the one that is NOT simply "cannot cache": Cloudflare may hold a copy but
    # must check with the origin before serving it.
    assert ("will not serve it from its cache without first checking with your web "
            "server") in message("cc-no-cache")
    assert "cannot serve it from its cache" in message("cc-private")
    assert "cannot serve it from its cache" in message("cc-no-store")

    # Generic (non-U-M) variant carries the same consequence:
    assert "every visitor request is passed through to your web server" in message(
        "cc-no-cache", umich=False)


def test_must_revalidate_states_the_stale_risk_and_says_remove_it(notices):
    def message(count, kind="page", directive="must-revalidate", umich=True):
        items = [_item("cc-must-revalidate", f"https://a.example.edu/p{i}", kind=kind,
                       directive=directive)
                 for i in range(count)]
        return _build(notices, {"a.example.edu": items}, umich=umich)[0]["message"]

    one = message(1)
    assert "<code>must-revalidate</code>" in one
    assert "You should remove it" in one
    assert "no effect until this page goes stale" in one
    assert "visitors will get errors rather than a stale copy of this page." in one

    # Number agreement with the URL list rendered below the sentence:
    two = message(2)
    assert "no effect until these pages go stale" in two
    assert "visitors will get errors rather than stale copies of these pages." in two
    assert "these static assets" in message(2, kind="asset")

    # The notice names the directive actually seen.  NOTE: assert on the <code> span, not the
    # bare string -- the U-M variant's "How to fix this" link is {doc_url}#cc-must-revalidate,
    # so the raw substring "must-revalidate" appears in EVERY U-M message.
    proxy = message(1, directive="proxy-revalidate")
    assert "<code>proxy-revalidate</code>" in proxy
    assert "<code>must-revalidate</code>" not in proxy

    # The old, wrong language is gone from BOTH variants:
    for msg in (one, message(1, umich=False)):
        assert "defeats caching" not in msg
        assert "reduces caching benefit" not in msg
        assert "strict freshness requirement" not in msg
        assert "home page" not in msg
        assert "emergency" not in msg


def test_revalidate_directives_do_not_consolidate_into_each_other(notices):
    # Consolidation identity is (id, kind, params), so the differing directive keeps them
    # apart even though they share an item id.
    items = [_item("cc-must-revalidate", "https://a.example.edu/a", directive="must-revalidate"),
             _item("cc-must-revalidate", "https://a.example.edu/b", directive="proxy-revalidate")]
    message = _build(notices, {"a.example.edu": items})[0]["message"]
    assert "<code>must-revalidate</code>" in message
    assert "<code>proxy-revalidate</code>" in message


def test_location_specific_items_are_not_given_the_site_wide_direction(notices):
    # The transport/status items are about the listed URLs themselves, not about a site-wide
    # configuration, so they must not carry the "apply this site-wide" direction.
    for item_id, params in (("http-error", {"status": 404}),
                            ("timeout", {"timeout": 5}), ("invalid-cert", {})):
        message = _build(notices, {"a.example.edu": [
            _item(item_id, "https://a.example.edu/p", **params)]})[0]["message"]
        assert "site-wide" not in message, item_id


def test_no_parenthesized_s_pluralization_in_owner_facing_text(notices):
    for seconds, expected in ((3600, "1 hour"), (7200, "2 hours"), (60, "1 minute"),
                              (120, "2 minutes"), (1, "1 second"), (30, "30 seconds")):
        message = _build(notices, {"a.example.edu": [
            _item("short-cache-time", "https://a.example.edu/", seconds=seconds)]})[0]["message"]
        assert f"only cached for {expected}." in message
        assert "(s)" not in message


def test_cookie_phrase_agrees_with_the_number_of_cookies(notices):
    one = _build(notices, {"a.example.edu": [
        _item("set-cookie", "https://a.example.edu/", cookies="sessionid")]})[0]["message"]
    assert "sets a cookie (<code>sessionid</code>)" in one
    many = _build(notices, {"a.example.edu": [
        _item("set-cookie", "https://a.example.edu/", cookies="a, b")]})[0]["message"]
    assert "sets cookies (<code>a, b</code>)" in many

    # The count comes from cookie_count, never from re-splitting the display string: a
    # malformed Set-Cookie can yield ONE cookie whose name contains a comma.
    comma = _build(notices, {"a.example.edu": [
        _item("set-cookie", "https://a.example.edu/", cookies="theme_a,theme_b",
              cookie_count=1)]})[0]["message"]
    assert "sets a cookie (<code>theme_a,theme_b</code>)" in comma


def test_timeout_and_redirect_counts_pluralize(notices):
    one = _build(notices, {"a.example.edu": [
        _item("timeout", "https://a.example.edu/", timeout=1)]})[0]["message"]
    assert "did not respond within 1 second;" in one
    many = _build(notices, {"a.example.edu": [
        _item("timeout", "https://a.example.edu/", timeout=5)]})[0]["message"]
    assert "did not respond within 5 seconds;" in many
    redirects = _build(notices, {"a.example.edu": [
        _item("too-many-redirects", "https://a.example.edu/", max_redirects=1)]})[0]["message"]
    assert "more than 1 time &mdash;" in redirects


def _all_item_messages(notices, **build_kwargs):
    """Every item id rendered once, so encoding assertions cover the whole vocabulary."""
    params_by_id = {
        "http-error": {"status": 404}, "cf-status-uncacheable": {"status": "DYNAMIC"},
        "short-cache-time": {"seconds": 60}, "timeout": {"timeout": 5},
        "request-failed": {"reason": "connection refused"},
        "too-many-redirects": {"max_redirects": 5},
        "cc-must-revalidate": {"directive": "must-revalidate"},
    }
    for item_id in notices._CONSOLE:
        item = _item(item_id, "https://a.example.edu/p", **params_by_id.get(item_id, {}))
        yield item_id, item, _build(notices, {"a.example.edu": [item]}, **build_kwargs)[0]


def test_notice_html_has_no_raw_non_ascii_characters(notices):
    # An em dash emitted as a raw UTF-8 byte sequence is re-encoded as mojibake ("â€”") by
    # any downstream consumer that mis-guesses the charset -- notably Emogrifier's libxml.
    # Owner-facing HTML uses named entities so it survives regardless.
    for umich in (True, False):
        for item_id, _item_dict, notice in _all_item_messages(notices, umich=umich):
            raw = [c for c in notice["message"] if ord(c) > 127]
            assert not raw, f"{item_id} (umich={umich}): raw non-ASCII {raw}"


def test_console_lines_are_pure_ascii(notices):
    # The console's encoding is the terminal's, not ours: a non-UTF-8 locale turns a raw
    # em dash into a UnicodeEncodeError or a '?'.  Entities would be nonsense here.
    for item_id, item, _notice in _all_item_messages(notices):
        line = notices.console_line(item)
        assert line.isascii(), f"{item_id}: non-ASCII console line {line!r}"
        assert "&mdash;" not in line  # entities belong in HTML, not on a terminal


def test_plaintext_conversion_decodes_entities_for_screen_readers(psh, reset_sc, notices):
    # The .txt alternative is what accessibility tooling reads: it must carry real
    # characters, never the raw "&mdash;"/"&middot;" source entities.
    for _item_id, _item_dict, notice in _all_item_messages(notices, umich=True):
        ctx = reset_sc.SiteContext({"name": SITE})
        ctx.add_notice(dict(notice))
        text = ctx["notices"][0]["text"]
        assert "&mdash;" not in text and "&middot;" not in text
        assert "&amp;" not in text and "&lt;" not in text
    # and the characters the entities stand for do arrive intact:
    ctx = reset_sc.SiteContext({"name": SITE})
    ctx.add_notice(dict(_build(notices, {"a.example.edu": [
        _item("too-many-redirects", "https://a.example.edu/p", max_redirects=5)]})[0]))
    assert "—" in ctx["notices"][0]["text"]  # em dash, decoded


def test_remote_strings_are_escaped(notices):
    evil_url = 'https://a.example.edu/<script>alert(1)</script>'
    evil_reason = '<img src=x onerror=alert(1)>'
    out = _build(notices, {"a.example.edu": [
        _item("request-failed", evil_url, reason=evil_reason)]})
    message = out[0]["message"]
    assert "<script>" not in message
    assert "&lt;img src=x onerror=alert(1)&gt;" in message


def test_console_line_includes_url_kind_and_problem(notices):
    line = notices.console_line(_item("cf-status-uncacheable", "https://a.example.edu/",
                                      status="DYNAMIC"))
    assert line == "https://a.example.edu/ (page): Cf-Cache-Status DYNAMIC - not being cached"
    line = notices.console_line(_item("timeout", "https://a.example.edu/x.js", kind="asset",
                                      timeout=5))
    assert line == "https://a.example.edu/x.js (asset): no response within 5s"


def test_console_line_renders_either_revalidate_directive(notices):
    # {directive} is a placeholder precisely because cc-must-revalidate can carry either
    # directive the rule detects -- must-revalidate is covered elsewhere; this pins the
    # other one so a format-string typo affecting only proxy-revalidate isn't invisible.
    line = notices.console_line(_item("cc-must-revalidate", "https://a.example.edu/",
                                      directive="proxy-revalidate"))
    assert line == "https://a.example.edu/ (page): Cache-Control contains proxy-revalidate"


def test_every_item_id_has_console_and_html_language(notices):
    params_by_id = {
        "http-error": {"status": 404}, "cf-status-uncacheable": {"status": "DYNAMIC"},
        "short-cache-time": {"seconds": 60}, "timeout": {"timeout": 5},
        "request-failed": {"reason": "connection refused"},
        "too-many-redirects": {"max_redirects": 5},
        "set-cookie": {"cookies": "sessionid"},
        "set-cookie-bypass": {"cookies": "sessionid"},
        "cc-must-revalidate": {"directive": "must-revalidate"},
    }
    for item_id in notices._CONSOLE:
        item = _item(item_id, "https://a.example.edu/p", **params_by_id.get(item_id, {}))
        assert notices.console_line(item)
        for umich in (True, False):
            out = _build(notices, {"a.example.edu": [item]}, umich=umich)
            assert len(out) == 1 and out[0]["message"]
            # the hard rule: never suggest disabling/bypassing caching
            assert "disable" not in out[0]["message"].lower()


@given(st.dictionaries(
    st.sampled_from([f"f{i}.example.edu" for i in range(6)]),
    st.lists(st.sampled_from(["no-cache-control", "set-cookie", "cf-status-missing"]),
             max_size=3),
    max_size=6))
def test_groups_partition_the_populated_fqdns(psh, assignment):
    notices = _load(psh)
    items_by_fqdn = {
        fqdn: [_item(i, f"https://{fqdn}/") for i in item_ids]
        for fqdn, item_ids in assignment.items()
    }
    out = notices.build_cache_notices(SITE, items_by_fqdn, umich=False, doc_url=DOC,
                                      framework="",
                                      sample_by_fqdn={f: _sample(3) for f in items_by_fqdn})
    populated = {f for f, items in items_by_fqdn.items() if items}
    covered = []
    for n in out:
        covered.extend(n["csv"].split(",")[2].split("+"))
    assert sorted(covered) == sorted(populated)  # partition: exactly once each
