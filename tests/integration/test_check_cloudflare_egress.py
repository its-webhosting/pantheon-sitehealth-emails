"""Integration tests for check/cloudflare/egress.py (the egress-IP allowlist check).

Offline by construction: `egress.probe` (the HTTP seam) is monkeypatched with canned
endpoint bodies, and the shared SDK client is a fake injected via
sc.plugin_context['plugin.cloudflare']['get_client'] (house pattern; the real `cloudflare`
package is also faked in sys.modules so the test extra does not need the SDK installed).
"""
import importlib.util
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ACCOUNT = "acct123"
LIST = "um_networks"
CONFIG = {"Cloudflare": {"enabled": True, "api_token": "t",
                         "cachecheck": {"enabled": True, "account_id": ACCOUNT,
                                        "list_name": LIST}}}

V4 = "141.211.0.10"
V6 = "2607:f018::10"
TRACE_V4 = "https://1.1.1.1/cdn-cgi/trace"
TRACE_V6 = "https://[2606:4700:4700::1111]/cdn-cgi/trace"


class FakeCloudflareError(Exception):
    pass


@pytest.fixture
def egress(psh, monkeypatch):
    """Load egress.py under a probe package so its relative import (.cfg) resolves."""
    fake_cf = types.ModuleType("cloudflare")
    fake_cf.CloudflareError = FakeCloudflareError
    monkeypatch.setitem(sys.modules, "cloudflare", fake_cf)

    pkg_dir = Path(psh.__file__).resolve().parents[1] / "check" / "cloudflare"
    package = types.ModuleType("cf_egress_pkg")
    package.__path__ = [str(pkg_dir)]
    monkeypatch.setitem(sys.modules, "cf_egress_pkg", package)
    monkeypatch.delitem(sys.modules, "cf_egress_pkg.cfg", raising=False)

    loader = SourceFileLoader("cf_egress_pkg.egress", str(pkg_dir / "egress.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "cf_egress_pkg.egress", module)
    loader.exec_module(module)
    return module


def _fake_probe(bodies):
    """probe(url, family, timeout, user_agent) returning canned bodies; records calls."""
    calls = []

    def probe(url, family, timeout, user_agent):
        calls.append((url, family))
        return bodies.get(url)

    probe.calls = calls
    return probe


class _Item:
    def __init__(self, ip):
        self.ip = ip


class _List:
    def __init__(self, name, list_id="lid1"):
        self.name = name
        self.id = list_id


def _fake_client(lists, items, errors=None):
    errors = errors or {}

    def list_lists(account_id):
        if "lists" in errors:
            raise errors["lists"]
        assert account_id == ACCOUNT
        return iter(lists)

    def list_items(account_id, list_id):
        if "items" in errors:
            raise errors["items"]
        assert account_id == ACCOUNT
        return iter(items)

    return types.SimpleNamespace(rules=types.SimpleNamespace(lists=types.SimpleNamespace(
        list=list_lists, items=types.SimpleNamespace(list=list_items))))


@pytest.fixture
def env(egress, psh, reset_sc, monkeypatch):
    """Standard passing environment: both families discoverable, both in the list."""
    sc = reset_sc
    sc.config = CONFIG
    sc.options = psh.parse_args([])
    client = _fake_client([_List(LIST)], [_Item("141.211.0.0/16"), _Item("2607:f018::/32")])
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    probe = _fake_probe({TRACE_V4: f"fl=1\nip={V4}\nts=1\n", TRACE_V6: f"ip={V6}\n"})
    monkeypatch.setattr(egress, "probe", probe)
    return types.SimpleNamespace(sc=sc, psh=psh, probe=probe, monkeypatch=monkeypatch)


def test_both_families_on_list_passes(egress, env):
    egress.check_egress_ip()  # no SystemExit
    assert {c[1] for c in env.probe.calls} == {4, 6}


def test_one_family_unreachable_is_skipped(egress, env, monkeypatch, capsys):
    monkeypatch.setattr(egress, "probe",
                        _fake_probe({TRACE_V4: f"ip={V4}\n"}))  # every v6 probe dead
    egress.check_egress_ip()
    assert "No IPv6 connectivity" in capsys.readouterr().out


def test_off_list_ip_is_fatal(egress, env, monkeypatch):
    monkeypatch.setattr(egress, "probe",
                        _fake_probe({TRACE_V4: "ip=203.0.113.9\n", TRACE_V6: f"ip={V6}\n"}))
    with pytest.raises(SystemExit) as exc:
        egress.check_egress_ip()
    message = str(exc.value)
    assert "203.0.113.9" in message and LIST in message and "--allow-any-source-ip" in message


def test_all_probes_dead_is_fatal(egress, env, monkeypatch):
    monkeypatch.setattr(egress, "probe", _fake_probe({}))
    with pytest.raises(SystemExit) as exc:
        egress.check_egress_ip()
    assert "external IP address" in str(exc.value)


def test_fallback_chain_radar_then_ifconfig(egress, env, monkeypatch):
    probe = _fake_probe({
        egress.FALLBACK_RADAR: f'{{"ip_address": "{V4}"}}',   # v4 via radar (trace dead)
        egress.FALLBACK_IFCONFIG: f"{V6}\n",                  # v6 via ifconfig... but the
        # same body answers the v4 ifconfig probe too -- family validation must reject
        # the v6 address when probing v4 and vice versa, so give radar the v4 answer.
    })
    monkeypatch.setattr(egress, "probe", probe)
    egress.check_egress_ip()
    urls_v4 = [u for u, f in probe.calls if f == 4]
    assert urls_v4 == [TRACE_V4, egress.FALLBACK_RADAR]  # stopped once radar answered


def test_mismatched_family_answer_counts_as_failure(egress, env, monkeypatch):
    # Every v6 endpoint answers with a v4 address -> treated as no IPv6 connectivity.
    monkeypatch.setattr(egress, "probe", _fake_probe({
        TRACE_V4: f"ip={V4}\n",
        TRACE_V6: f"ip={V4}\n",
        egress.FALLBACK_RADAR: f'{{"ip_address": "{V4}"}}',
        egress.FALLBACK_IFCONFIG: f"{V4}\n",
    }))
    egress.check_egress_ip()  # passes: v4 on list, v6 skipped (never claims the v4 answer)


@pytest.mark.parametrize("argv", [["--update"], ["--import-older-metrics"],
                                  ["--create-tables"], ["--allow-any-source-ip"]])
def test_gating_flags_skip_the_check_entirely(egress, env, argv):
    env.sc.options = env.psh.parse_args(argv)
    egress.check_egress_ip()
    assert env.probe.calls == []  # zero probes, zero API calls


def test_missing_list_is_fatal(egress, env):
    client = _fake_client([_List("other-list")], [])
    env.sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: client
    with pytest.raises(SystemExit) as exc:
        egress.check_egress_ip()
    assert LIST in str(exc.value) and "Account Filter Lists" in str(exc.value)


def test_empty_list_is_fatal(egress, env):
    client = _fake_client([_List(LIST)], [])
    env.sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: client
    with pytest.raises(SystemExit) as exc:
        egress.check_egress_ip()
    assert "no IP entries" in str(exc.value)


def test_api_error_is_fatal(egress, env):
    client = _fake_client([], [], errors={"lists": FakeCloudflareError("boom")})
    env.sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: client
    with pytest.raises(SystemExit) as exc:
        egress.check_egress_ip()
    assert "boom" in str(exc.value)


def test_non_ip_items_skipped_with_warning(egress, env, capsys):
    client = _fake_client([_List(LIST)],
                          [_Item(None), _Item("141.211.0.0/16"), _Item("2607:f018::/32")])
    env.sc.plugin_context["plugin.cloudflare"]["get_client"] = lambda: client
    egress.check_egress_ip()
    assert "non-IP entry" in capsys.readouterr().out
