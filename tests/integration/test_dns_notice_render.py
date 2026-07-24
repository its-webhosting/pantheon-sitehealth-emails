import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def dns_notices(psh, reset_sc, monkeypatch):
    # monkeypatch so sc.escape_url is restored after each test (reset_sc does not track it;
    # a leaked identity stub would pollute other suites' escaping tests).
    monkeypatch.setattr(reset_sc, "escape_url", lambda u: u)
    path = Path(psh.__file__).resolve().parents[1] / "check" / "dns" / "notices.py"
    spec = importlib.util.spec_from_file_location("dns_notices_render_probe", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HOSTS = ["a.example.org", "b.example.org"]

# The builders return Notices since I14c, so each snapshot is taken through the ONE public
# projection, SiteContext.notice_to_dict (SPEC I14c D-i14c-10) -- keeping the whole-dict pin
# (type/icon/csv/short/message/text) rather than degrading it to three string snapshots.  The
# csv row's site field now comes from the context, hence SiteContext({"name": "s"}): the site
# name is the same "s" the builders were called with, so every csv line is byte-identical.
# The projection ALWAYS emits `icon`, which these five builders never set, so each of the 7
# entries gains exactly one 'icon' line and no other byte -- the increment's only sanctioned
# snapshot change (SPEC I14c §3).


def test_transient_render(dns_notices, reset_sc, snapshot):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(dns_notices.transient_notice("s", HOSTS)) == snapshot


def test_not_in_dns_render(dns_notices, reset_sc, snapshot):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(dns_notices.not_in_dns_notice("s", HOSTS)) == snapshot


def test_multiple_zones_render(dns_notices, reset_sc, snapshot):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(dns_notices.proxied_in_multiple_zones_notice("s", HOSTS)) == snapshot


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_not_behind_cloudflare_render(dns_notices, reset_sc, snapshot, umich):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(
        dns_notices.not_behind_cloudflare_notice("s", HOSTS, umich=umich)) == snapshot


@pytest.mark.parametrize("umich", [True, False], ids=["umich", "generic"])
def test_not_proxied_render(dns_notices, reset_sc, snapshot, umich):
    ctx = reset_sc.SiteContext({"name": "s"})
    assert ctx.notice_to_dict(
        dns_notices.behind_cloudflare_not_proxied_notice("s", HOSTS, umich=umich)) == snapshot
