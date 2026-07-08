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
    return {"id": item_id, "kind": kind, "url": url, "params": params}


def _build(notices, items_by_fqdn, *, umich=True, framework="wordpress"):
    return notices.build_cache_notices(SITE, items_by_fqdn, umich=umich, doc_url=DOC,
                                       framework=framework)


def test_identical_signatures_consolidate_into_one_notice(notices):
    out = _build(notices, {
        "a.example.edu": [_item("no-cache-control", "https://a.example.edu/")],
        "b.example.edu": [_item("no-cache-control", "https://b.example.edu/")],
    })
    assert len(out) == 1
    n = out[0]
    assert n["type"] == "warning"
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
    assert line == "https://a.example.edu/ (page): Cf-Cache-Status DYNAMIC — not being cached"
    line = notices.console_line(_item("timeout", "https://a.example.edu/x.js", kind="asset",
                                      timeout=5))
    assert line == "https://a.example.edu/x.js (asset): no response within 5s"


def test_every_item_id_has_console_and_html_language(notices):
    params_by_id = {
        "http-error": {"status": 404}, "cf-status-uncacheable": {"status": "DYNAMIC"},
        "short-cache-time": {"seconds": 60}, "timeout": {"timeout": 5},
        "request-failed": {"reason": "connection refused"},
        "too-many-redirects": {"max_redirects": 5},
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
                                      framework="")
    populated = {f for f, items in items_by_fqdn.items() if items}
    covered = []
    for n in out:
        covered.extend(n["csv"].split(",")[2].split("+"))
    assert sorted(covered) == sorted(populated)  # partition: exactly once each
