"""Unit tests for check/cloudflare/pages.py (pure link/asset extraction, RNG selection,
redirect classification)."""
import importlib.util
import random
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

pytestmark = pytest.mark.unit

FQDN = "www.example.edu"
BASE = f"https://{FQDN}/"

_CACHED = {}


def _load(psh):
    if "m" not in _CACHED:
        path = Path(psh.__file__).parent / "check" / "cloudflare" / "pages.py"
        loader = SourceFileLoader("cachecheck_pages_probe", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHED["m"] = module
    return _CACHED["m"]


@pytest.fixture
def pages(psh):
    return _load(psh)


def _html(hrefs):
    return "<html><body>" + "".join(f'<a href="{h}">x</a>' for h in hrefs) + "</body></html>"


# ── link extraction ─────────────────────────────────────────────────────────────────
def test_relative_and_absolute_same_fqdn_links_kept_sorted_deduped(pages):
    html = _html(["/b/", f"https://{FQDN}/a/", "/b/", "c"])
    assert pages.extract_page_links(html, FQDN, BASE) == [
        f"https://{FQDN}/a/", f"https://{FQDN}/b/", f"https://{FQDN}/c"]


def test_other_fqdns_schemes_and_main_page_links_dropped(pages):
    html = _html([
        "https://other.example.edu/page",     # other FQDN
        f"http://{FQDN}/insecure",             # non-https
        "mailto:someone@example.edu",          # non-https scheme
        "/",                                   # main page
        "#section",                            # fragment on the main page
        f"https://{FQDN}/",                    # absolute main page
        f"https://{FQDN}/?utm=x",              # main page regardless of query
        f"https://{FQDN}/#frag",               # main page fragment
    ])
    assert pages.extract_page_links(html, FQDN, BASE) == []


def test_apex_is_a_different_fqdn(pages):
    html = _html(["https://example.edu/page"])
    assert pages.extract_page_links(html, FQDN, BASE) == []


def test_fragments_are_stripped_and_merged(pages):
    html = _html(["/page#a", "/page#b", "/page"])
    assert pages.extract_page_links(html, FQDN, BASE) == [f"https://{FQDN}/page"]


BARE_MARKERS = ["/wp-admin", "/wp-login", "/login", "/logout", "/user/login", "/profile",
                "/token", "/userinfo", "/callback", "/end_session", "/register", "/signup"]


@pytest.mark.parametrize("prefix", ["/api/", "/account/", "/auth/"])
def test_slash_terminated_prefixes_exclude_all_subpaths(pages, prefix):
    html = _html([prefix + "thing", "/kept"])
    assert pages.extract_page_links(html, FQDN, BASE) == [f"https://{FQDN}/kept"]


@pytest.mark.parametrize("prefix", BARE_MARKERS)
def test_bare_markers_match_on_segment_boundaries(pages, prefix):
    # exact path, subpath, and extension forms are all excluded:
    html = _html([prefix, prefix + "/sub", prefix + ".php", "/kept"])
    assert pages.extract_page_links(html, FQDN, BASE) == [f"https://{FQDN}/kept"]


@pytest.mark.parametrize("prefix", BARE_MARKERS)
def test_bare_markers_do_not_over_exclude_longer_slugs(pages, prefix):
    # Regression (code review): /registered-programs must not match /register etc. --
    # a slug that merely EXTENDS a marker is a legitimate page and stays probeable.
    html = _html([prefix + "xy-suffix"])
    assert pages.extract_page_links(html, FQDN, BASE) == [f"https://{FQDN}{prefix}xy-suffix"]


def test_segment_boundary_real_world_examples(pages):
    html = _html(["/registered-programs", "/profiles/jane", "/tokens", "/logins",
                  "/register", "/wp-login.php"])
    assert pages.extract_page_links(html, FQDN, BASE) == [
        f"https://{FQDN}/logins",
        f"https://{FQDN}/profiles/jane",
        f"https://{FQDN}/registered-programs",
        f"https://{FQDN}/tokens",
    ]


def test_authorize_matched_anywhere_in_path(pages):
    html = _html(["/oauth2/x.authorize", "/kept"])
    assert pages.extract_page_links(html, FQDN, BASE) == [f"https://{FQDN}/kept"]


def test_malformed_href_skipped(pages):
    html = _html(["https://[bad", "/kept"])
    assert pages.extract_page_links(html, FQDN, BASE) == [f"https://{FQDN}/kept"]


# ── selection ───────────────────────────────────────────────────────────────────────
def test_choose_pages_caps_at_three_and_is_seed_deterministic(pages):
    links = [f"https://{FQDN}/p{i}" for i in range(10)]
    first = pages.choose_pages(links, random.Random("seed"))
    second = pages.choose_pages(links, random.Random("seed"))
    assert first == second
    assert len(first) == 3
    assert set(first) <= set(links)


def test_choose_pages_fewer_or_zero(pages):
    assert pages.choose_pages([], random.Random(1)) == []
    one = [f"https://{FQDN}/only"]
    assert pages.choose_pages(one, random.Random(1)) == one


# ── assets ──────────────────────────────────────────────────────────────────────────
ASSET_HTML = f"""
<html><head>
  <link rel="stylesheet" href="/css/site.css">
  <link rel="preload" href="/css/preload.css">
  <link rel="Stylesheet" href="https://{FQDN}/css/upper.css">
  <link rel="stylesheet" href="https://cdn.example.com/ext.css">
  <script src="/js/app.js"></script>
  <script>inline()</script>
</head><body>
  <img src="/img/logo.png">
  <img src="http://{FQDN}/img/insecure.png">
</body></html>
"""


def test_extract_assets_per_class(pages):
    assets = pages.extract_assets(ASSET_HTML, FQDN, BASE)
    assert assets == {
        "js": [f"https://{FQDN}/js/app.js"],
        "css": [f"https://{FQDN}/css/site.css", f"https://{FQDN}/css/upper.css"],
        "img": [f"https://{FQDN}/img/logo.png"],
    }


def test_choose_assets_one_per_present_class(pages):
    assets = {"js": ["https://x/1.js"], "css": [], "img": ["https://x/a.png", "https://x/b.png"]}
    chosen = pages.choose_assets(assets, random.Random(1))
    classes = [c for c, _ in chosen]
    assert classes == ["js", "img"]


# ── redirect classification ─────────────────────────────────────────────────────────
def test_classify_redirect(pages):
    # (a) http->https upgrade of the identical URL:
    assert pages.classify_redirect(f"http://{FQDN}/p?q=1", f"https://{FQDN}/p?q=1", FQDN) == "follow"
    # (b) same-FQDN https target, any path:
    assert pages.classify_redirect(f"https://{FQDN}/a", f"https://{FQDN}/b?x=1", FQDN) == "follow"
    # apex<->www is cross:
    assert pages.classify_redirect(f"https://{FQDN}/a", "https://example.edu/a", FQDN) == "cross"
    # other FQDN is cross:
    assert pages.classify_redirect(f"https://{FQDN}/a", "https://other.edu/a", FQDN) == "cross"
    # https->http downgrade is cross even on the same FQDN:
    assert pages.classify_redirect(f"https://{FQDN}/a", f"http://{FQDN}/a", FQDN) == "cross"


# ── Hypothesis properties ───────────────────────────────────────────────────────────
_path_chars = st.text(alphabet="abcdefghij0123456789-", min_size=1, max_size=12)


@given(st.lists(_path_chars, max_size=20))
def test_extracted_links_are_subset_of_candidates_no_excluded(psh, paths):
    pages = _load(psh)
    hrefs = [f"/{p}" for p in paths] + ["/wp-admin/x", "https://elsewhere.edu/y"]
    out = pages.extract_page_links(_html(hrefs), FQDN, BASE)
    candidates = {f"https://{FQDN}/{p}" for p in paths}
    assert set(out) <= candidates
    assert all(not pages._path_excluded(u.replace(f"https://{FQDN}", "")) for u in out)


@given(st.permutations([f"/p{i}" for i in range(8)]))
def test_extraction_stable_under_input_permutation(psh, hrefs):
    pages = _load(psh)
    assert pages.extract_page_links(_html(hrefs), FQDN, BASE) == [
        f"https://{FQDN}/p{i}" for i in range(8)]
