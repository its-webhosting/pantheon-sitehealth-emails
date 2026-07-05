"""Integration tests for plugin/cloudflare/ips.py (test-suite SPEC §7.4).

No live Cloudflare and no dependency on the `cloudflare` package being installed: a fake
`cloudflare` module is injected into sys.modules before the plugin file is loaded, so
`from cloudflare import Cloudflare` binds to the fake.
"""
import importlib.util
import ipaddress
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

V4 = ["173.245.48.0/20", "103.21.244.0/22"]
V6 = ["2400:cb00::/32", "2606:4700::/32"]


class _FakeIPList:
    def __init__(self, v4, v6):
        self.ipv4_cidrs = v4
        self.ipv6_cidrs = v6


def _make_cloudflare(list_impl):
    class FakeCloudflare:
        def __init__(self, **kwargs):
            self.ips = types.SimpleNamespace(list=list_impl)

    return FakeCloudflare


@pytest.fixture
def load_ips(psh, monkeypatch):
    """Load plugin/cloudflare/ips.py with a fake `cloudflare` module, returning (module, sc)."""
    import script_context as sc

    fake_pkg = types.ModuleType("cloudflare")
    fake_pkg.Cloudflare = object  # placeholder; each test monkeypatches module.Cloudflare
    monkeypatch.setitem(sys.modules, "cloudflare", fake_pkg)

    path = Path(psh.__file__).parent / "plugin" / "cloudflare" / "ips.py"
    loader = SourceFileLoader("cloudflare_ips_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    sc.config = {"Cloudflare": {"member_email": "e@example.com", "member_api_key": "k"}}
    sc.plugin_context = {"plugin.cloudflare": {}}
    return module, sc


def test_cidrs_become_ip_networks(load_ips, monkeypatch):
    module, sc = load_ips
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare(lambda: _FakeIPList(V4, V6)))

    module.get_cloudflare_ips()

    ctx = sc.plugin_context["plugin.cloudflare"]
    assert ctx["cloudflare_ipv4_nets"] == [ipaddress.ip_network(c) for c in V4]
    assert ctx["cloudflare_ipv6_nets"] == [ipaddress.ip_network(c) for c in V6]


def test_client_failure_exits(load_ips, monkeypatch):
    def boom():
        raise RuntimeError("cloudflare down")

    module, _sc = load_ips
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare(boom))

    with pytest.raises(SystemExit):
        module.get_cloudflare_ips()
