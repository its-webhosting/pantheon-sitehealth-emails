"""PURE link/asset extraction, selection, and redirect classification for the Cloudflare
cache-configuration check.  No I/O, no sc access.

Selection is deterministic for a given RNG: candidate lists are deduplicated and sorted
lexicographically BEFORE sampling (so the same seed picks the same URLs regardless of
document order), and the RNG itself is seeded from site name + report date (see cache.py).
"""

import urllib.parse

from bs4 import BeautifulSoup

# Links whose path indicates authentication/API surfaces are never probed.  Matching
# semantics (see _path_excluded): entries ending in "/" are plain prefix matches;
# ".authorize" is an extension-style marker matched anywhere in the path (e.g.
# /oauth2/x.authorize); every other entry matches only on a path-SEGMENT boundary --
# the exact path, or the entry followed by "/" or "." (so /wp-login matches
# /wp-login.php and /login matches /login/reset, but /registered-programs does NOT
# match /register and /profiles does NOT match /profile).
EXCLUDED_PATH_PREFIXES = (
    "/api/", "/wp-admin", "/wp-login", "/login", "/logout", "/user/login", "/account/",
    "/auth/", "/profile", ".authorize", "/token", "/userinfo", "/callback",
    "/end_session", "/register", "/signup",
)

MAX_PAGES = 3  # links sampled per page (PROMPT step 2e)


def _same_fqdn_https(url: str, fqdn: str):  # -> urllib.parse.SplitResult | None
    """Parse url; return the split result iff it is https on exactly this FQDN."""
    try:
        split = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if split.scheme != "https":
        return None
    if (split.hostname or "").lower() != fqdn.lower():
        return None
    return split


def _path_excluded(path: str) -> bool:
    for marker in EXCLUDED_PATH_PREFIXES:
        if not marker.startswith("/"):
            if marker in path:  # extension-style marker (.authorize)
                return True
        elif marker.endswith("/"):
            if path.startswith(marker):  # already segment-bounded
                return True
        # Bare-word entries match only on a segment boundary, so legitimate pages like
        # /registered-programs or /profiles are still cache-checked:
        elif path == marker or path.startswith(marker + "/") or path.startswith(marker + "."):
            return True
    return False


def extract_page_links(html_text: str, fqdn: str, base_url: str) -> list:
    """All a[href] links that are relative or same-FQDN https, excluding the main page
    itself (any path ""/"/" -- fragments/anchors included), non-https schemes, other
    FQDNs, and auth/API paths.  Fragments stripped; deduplicated; sorted."""
    soup = BeautifulSoup(html_text, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        try:
            absolute = urllib.parse.urljoin(base_url, a["href"])
        except ValueError:
            continue
        absolute, _fragment = urllib.parse.urldefrag(absolute)
        split = _same_fqdn_https(absolute, fqdn)
        if split is None:
            continue
        if split.path in ("", "/"):
            continue  # the main page (incl. fragment/anchor links), already tested
        if _path_excluded(split.path):
            continue
        links.add(absolute)
    return sorted(links)


def choose_pages(links: list, rng) -> list:
    """Up to MAX_PAGES links, RNG-sampled from the (already sorted) candidates."""
    return rng.sample(links, min(MAX_PAGES, len(links)))


def extract_assets(html_text: str, fqdn: str, base_url: str) -> dict:
    """Static assets referenced by the page, per class: script[src] -> js,
    link[rel=stylesheet][href] -> css, img[src] -> img.  Same https/same-FQDN/relative
    filters as links; deduplicated; sorted per class."""
    soup = BeautifulSoup(html_text, "html.parser")
    assets = {"js": set(), "css": set(), "img": set()}

    def collect(cls, url):
        try:
            absolute = urllib.parse.urljoin(base_url, url)
        except ValueError:
            return
        absolute, _fragment = urllib.parse.urldefrag(absolute)
        if _same_fqdn_https(absolute, fqdn) is not None:
            assets[cls].add(absolute)

    for tag in soup.find_all("script", src=True):
        collect("js", tag["src"])
    for tag in soup.find_all("link", href=True):
        rel = tag.get("rel") or []
        if "stylesheet" in [r.lower() for r in rel]:
            collect("css", tag["href"])
    for tag in soup.find_all("img", src=True):
        collect("img", tag["src"])
    return {cls: sorted(urls) for cls, urls in assets.items()}


def choose_assets(assets: dict, rng) -> list:
    """Up to one asset per class, as [(class, url)] in js/css/img order."""
    chosen = []
    for cls in ("js", "css", "img"):
        if assets.get(cls):
            chosen.append((cls, rng.choice(assets[cls])))
    return chosen


def classify_redirect(current_url: str, location: str, fqdn: str) -> str:
    """'follow' for (a) an http->https upgrade of the identical URL, or (b) an https
    target on the same FQDN (any path/query); 'cross' for everything else -- explicitly
    including apex<->www and https->http downgrades (never probe insecurely on purpose).

    Rule (a) is unreachable in practice (all initial URLs are https and downgrades are
    'cross'); it exists to honor the PROMPT rule verbatim.
    """
    try:
        current = urllib.parse.urlsplit(current_url)
        target = urllib.parse.urlsplit(location)
    except ValueError:
        return "cross"
    if (
        current.scheme == "http"
        and target.scheme == "https"
        and current.hostname == target.hostname
        and current.path == target.path
        and current.query == target.query
    ):
        return "follow"
    if target.scheme == "https" and (target.hostname or "").lower() == fqdn.lower():
        return "follow"
    return "cross"
