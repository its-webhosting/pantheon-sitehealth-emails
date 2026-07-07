"""Integration tests for plugin/cloudflare/ips.py (test-suite SPEC §7.4).

ips.py no longer builds its own client; it reads the ONE shared client from
sc.plugin_context['plugin.cloudflare']['client'] (built by client.init_cloudflare_client).
So these tests seed a fake client there and call get_cloudflare_ips.  ips.py has no
`from cloudflare import Cloudflare` anymore, so no fake `cloudflare` module is needed to load it.
Auth-selection tests live in test_plugin_cloudflare_client.py.
"""
import importlib.util
import ipaddress
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


def _fake_client(ips_list_impl):
    """A stand-in for the shared Cloudflare client exposing only `.ips.list`."""
    return types.SimpleNamespace(ips=types.SimpleNamespace(list=ips_list_impl))


@pytest.fixture
def load_ips(psh):
    """Load plugin/cloudflare/ips.py, returning (module, sc) with an empty plugin_context bag."""
    import script_context as sc

    path = Path(psh.__file__).parent / "plugin" / "cloudflare" / "ips.py"
    loader = SourceFileLoader("cloudflare_ips_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {}}
    return module, sc


def test_cidrs_become_ip_networks(load_ips):
    module, sc = load_ips
    sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: _fake_client(
        lambda: _FakeIPList(V4, V6)
    )

    module.get_cloudflare_ips()

    ctx = sc.plugin_context["plugin.cloudflare"]
    assert ctx["cloudflare_ipv4_nets"] == [ipaddress.ip_network(c) for c in V4]
    assert ctx["cloudflare_ipv6_nets"] == [ipaddress.ip_network(c) for c in V6]


def test_client_failure_exits(load_ips):
    def boom():
        raise RuntimeError("cloudflare down")

    module, sc = load_ips
    sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: _fake_client(boom)

    with pytest.raises(SystemExit):
        module.get_cloudflare_ips()


def test_cloudflare_enabled_reads_config(psh):
    """Lock the detection fix by exercising the real helper: cloudflare_enabled() must read
    config, not `"plugin.cloudflare" in sc.plugin` (always True because every plugin package is
    imported regardless of `enabled`).  A revert to the buggy form would fail these assertions.
    """
    import script_context as sc

    sc.config = {"Cloudflare": {"enabled": True}}
    assert psh.cloudflare_enabled() is True

    sc.config = {"Cloudflare": {"enabled": False}}
    # The package is present in sc.plugin (the bug's always-True condition), yet the helper is False.
    sc.plugin = {"plugin.cloudflare": object()}
    assert psh.cloudflare_enabled() is False

    sc.config = {}  # section absent
    assert psh.cloudflare_enabled() is False
