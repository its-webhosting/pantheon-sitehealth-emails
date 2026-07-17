import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def notices(psh, reset_sc, monkeypatch):
    # Load check/dns/notices.py standalone (it only needs sc.escape_url).
    # Use monkeypatch (not direct assignment) so sc.escape_url is RESTORED after each test:
    # reset_sc does not track escape_url, so a leaked identity stub would pollute other suites
    # (e.g. check/cloudflare's escaping tests).
    monkeypatch.setattr(reset_sc, "escape_url", lambda u: u)
    path = Path(psh.__file__).resolve().parents[1] / "check" / "dns" / "notices.py"
    spec = importlib.util.spec_from_file_location("dns_notices_probe", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_notice_has_csv(notices):
    n = notices.not_in_dns_notice("s", ["a.example.org"])
    assert n["csv"].startswith("s,not-in-dns,")
    assert "a.example.org" in n["message"]


def test_transient_aggregates_all_hosts(notices):
    n = notices.transient_notice("s", ["a.example.org", "b.example.org"])
    assert n["type"] == "warning"
    assert n["csv"] == "s,dns-lookup-failed,a.example.org,b.example.org"
    assert "a.example.org" in n["message"] and "b.example.org" in n["message"]


def test_not_behind_cloudflare_umich_vs_generic(notices):
    umich = notices.not_behind_cloudflare_notice("s", ["a.example.org"], umich=True)
    generic = notices.not_behind_cloudflare_notice("s", ["a.example.org"], umich=False)
    assert "its.umich.edu" in umich["message"]
    assert "umich.edu" not in generic["message"] and "umich.edu" not in generic["text"]


def test_bug2_not_proxied_plaintext_lists_correct_hosts(notices):
    # Regression: the plaintext body must list behind_cloudflare_not_proxied, not the other list.
    n = notices.behind_cloudflare_not_proxied_notice("s", ["np.example.org"], umich=True)
    assert "np.example.org" in n["text"]
    assert n["csv"].startswith("s,behind-cloudflare-not-proxied,")


def test_hostname_html_escaped_in_display(notices):
    # Owner-facing HTML: the hostname text node must be html.escape'd (the href separately uses
    # sc.escape_url). Guards against markup injection via a remotely-derived domain id.
    n = notices.not_in_dns_notice("s", ["a<b>.example.org"])
    assert "&lt;b&gt;" in n["message"]
