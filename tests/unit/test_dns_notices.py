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


# The five builders, each bound to a uniform (module, site_name, hostnames) call: two of them
# take an extra keyword-only `umich`, so bind it here rather than branch inside the tests.
_BUILDERS = [
    ("dns-lookup-failed", lambda m, s, h: m.transient_notice(s, h)),
    ("not-in-dns", lambda m, s, h: m.not_in_dns_notice(s, h)),
    ("not-behind-cloudflare", lambda m, s, h: m.not_behind_cloudflare_notice(s, h, umich=True)),
    ("behind-cloudflare-not-proxied",
     lambda m, s, h: m.behind_cloudflare_not_proxied_notice(s, h, umich=True)),
    ("proxied-in-multiple-cloudflare-zones",
     lambda m, s, h: m.proxied_in_multiple_zones_notice(s, h)),
]
_BUILDER_IDS = [code for code, _ in _BUILDERS]


@pytest.mark.parametrize(("code", "build"), _BUILDERS, ids=_BUILDER_IDS)
def test_hostnames_become_separate_csv_fields(notices, code, build):
    n = build(notices, "s", ["a.example.org", "b.example.org"])
    assert n.code == code
    assert n.csv_extra == ("a.example.org", "b.example.org")


@pytest.mark.parametrize(("code", "build"), _BUILDERS, ids=_BUILDER_IDS)
def test_empty_hostname_list_yields_no_csv_fields(notices, code, build):
    # Documented precondition (SPEC I14c §2.1, D-i14c-11): every call site guards a non-empty
    # list (check/dns/hook.py:26,30,33,36,40), so this case is unreachable today.  Pre-I14c the
    # csv was f"{site},{code}," + ",".join(hostnames), which left a TRAILING COMMA on an empty
    # list; csv_extra=tuple(hostnames) leaves no trailing field.  Pinned so that divergence is
    # explicit rather than latent (PD#3's zero-length shadow).
    assert build(notices, "s", []).csv_extra == ()
    assert build(notices, "s", []).code == code


def test_every_notice_has_csv(notices):
    n = notices.not_in_dns_notice("s", ["a.example.org"])
    assert n.code == "not-in-dns"
    assert n.csv_extra == ("a.example.org",)
    assert "a.example.org" in n.html


def test_transient_aggregates_all_hosts(notices):
    n = notices.transient_notice("s", ["a.example.org", "b.example.org"])
    assert n.severity == "warning"
    assert n.code == "dns-lookup-failed"
    assert n.csv_extra == ("a.example.org", "b.example.org")
    assert "a.example.org" in n.html and "b.example.org" in n.html


def test_not_behind_cloudflare_umich_vs_generic(notices):
    umich = notices.not_behind_cloudflare_notice("s", ["a.example.org"], umich=True)
    generic = notices.not_behind_cloudflare_notice("s", ["a.example.org"], umich=False)
    assert "its.umich.edu" in umich.html
    assert "umich.edu" not in generic.html and "umich.edu" not in generic.text


def test_bug2_not_proxied_plaintext_lists_correct_hosts(notices):
    # Regression: the plaintext body must list behind_cloudflare_not_proxied, not the other list.
    n = notices.behind_cloudflare_not_proxied_notice("s", ["np.example.org"], umich=True)
    assert "np.example.org" in n.text
    assert n.code == "behind-cloudflare-not-proxied"


def test_hostname_html_escaped_in_display(notices):
    # Owner-facing HTML: the hostname text node must be html.escape'd (the href separately uses
    # sc.escape_url). Guards against markup injection via a remotely-derived domain id.
    n = notices.not_in_dns_notice("s", ["a<b>.example.org"])
    assert "&lt;b&gt;" in n.html
