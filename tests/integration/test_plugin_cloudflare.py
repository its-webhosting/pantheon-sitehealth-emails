"""Integration tests for plugin/cloudflare/ips.py (test-suite SPEC §7.4).

ips.py doesn't build its own client; it reads the ONE shared client via
sc.plugin_context['plugin.cloudflare']['get_client'] (built lazily by client.py).  So these
tests seed a fake client there and call get_cloudflare_ips.  Auth-selection tests live in
test_plugin_cloudflare_client.py.

ips.py DOES `import cloudflare` -- it needs `cloudflare.CloudflareError` to name what it
catches (PD#2) -- so, as in test_plugin_cloudflare_client.py, a fake `cloudflare` module is
injected into sys.modules before the file is loaded.  That keeps this tier runnable without
the optional [cloudflare] extra installed.
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


class FakeCloudflareError(Exception):
    """Stands in for cloudflare.CloudflareError -- the base of the SDK's exception tree.

    Real hierarchy (verified against the installed SDK): APIError -> CloudflareError, with
    APIConnectionError / APIStatusError / RateLimitError / ... beneath it.  Catching the base
    therefore covers every way the API itself can fail, and nothing else.
    """


class _FakeIPList:
    def __init__(self, v4, v6):
        self.ipv4_cidrs = v4
        self.ipv6_cidrs = v6


def _fake_client(ips_list_impl):
    """A stand-in for the shared Cloudflare client exposing only `.ips.list`."""
    return types.SimpleNamespace(ips=types.SimpleNamespace(list=ips_list_impl))


@pytest.fixture
def load_ips(psh, monkeypatch):
    """Load plugin/cloudflare/ips.py, returning (module, sc) with an empty plugin_context bag."""
    import script_context as sc

    fake_pkg = types.ModuleType("cloudflare")
    fake_pkg.CloudflareError = FakeCloudflareError
    monkeypatch.setitem(sys.modules, "cloudflare", fake_pkg)

    path = Path(psh.__file__).resolve().parents[1] / "plugin" / "cloudflare" / "ips.py"
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
    """An SDK failure is expected and survivable: exit cleanly, naming the cause.

    The stand-in used to be a bare RuntimeError, back when ips.py caught `except Exception`.
    It is a CloudflareError now because that is what "the client failed" actually MEANS under
    the named-exception contract -- a RuntimeError from the SDK is our bug, not an outage,
    and test_a_programming_bug_propagates_instead_of_being_relabelled pins that half.  The
    assertion is unchanged and no weaker; only the stand-in's class now matches the intent
    the test name always stated.
    """
    def boom():
        raise FakeCloudflareError("403 Forbidden: token lacks #zone:read")

    module, sc = load_ips
    sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: _fake_client(boom)

    with pytest.raises(SystemExit) as exc:
        module.get_cloudflare_ips()

    assert "Unable to get lists of Cloudflare IPs" in str(exc.value)
    assert "403 Forbidden" in str(exc.value), "the operator needs the underlying cause"


def test_a_programming_bug_propagates_instead_of_being_relabelled(load_ips):
    """THE POINT OF THE NAMED CATCH (PD#2).

    An AttributeError here means the SDK's shape moved or we called it wrong -- a bug, not a
    Cloudflare outage.  Reporting it as "Unable to get lists of Cloudflare IPs" sends the
    operator to check their API token while the real defect sits in our code.  It MUST
    propagate with its traceback intact.

    RED DEMONSTRATION (PD#14, observed 2026-07-16): against the previous `except Exception`
    this test failed with
        SystemExit: ERROR: Unable to get lists of Cloudflare IPs: 'Ips' object has no
        attribute 'list'
    -- the defect, made visible.  That red run is why the green one here is evidence.
    """
    def boom():
        raise AttributeError("'Ips' object has no attribute 'list'")

    module, sc = load_ips
    sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: _fake_client(boom)

    with pytest.raises(AttributeError, match="no attribute 'list'"):
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
