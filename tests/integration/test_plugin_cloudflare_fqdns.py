"""Integration tests for plugin/cloudflare/fqdns.py.

No live Cloudflare: a fake `cloudflare` module is injected into sys.modules before the plugin
file is loaded (so `import cloudflare` / `cloudflare.CloudflareError` resolve), and a fake client
object is passed in / seeded into plugin_context.
"""
import importlib.util
import io
import json
import os
import sys
import time
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from rich.console import Console

pytestmark = pytest.mark.integration


def _ns(**kw):
    return types.SimpleNamespace(**kw)


class FakeClient:
    """Stand-in for the shared Cloudflare client: accounts -> zones -> proxied DNS records.

    accounts: list of account namespaces (.id)
    zones_by_account: {account_id: [zone namespace(.id,.name), ...]}
    records_by_zone: {zone_id: [record namespace(.name,.content), ...]}
    records_error: if set, dns.records.list raises it (a cloudflare.CloudflareError)
    """

    def __init__(self, accounts, zones_by_account, records_by_zone, records_error=None):
        self.calls = {"accounts": 0, "zones": 0, "records": 0}

        def _accounts_list():
            self.calls["accounts"] += 1
            return list(accounts)

        def _zones_list(account):
            self.calls["zones"] += 1
            return list(zones_by_account.get(account["id"], []))

        def _records_list(zone_id, proxied):
            self.calls["records"] += 1
            if records_error is not None:
                raise records_error
            return list(records_by_zone.get(zone_id, []))

        self.accounts = _ns(list=_accounts_list)
        self.zones = _ns(list=_zones_list)
        self.dns = _ns(records=_ns(list=_records_list))


@pytest.fixture
def fqdns(psh, monkeypatch):
    """Load fqdns.py with a fake `cloudflare` module and a quiet recording console."""
    import script_context as sc

    fake_pkg = types.ModuleType("cloudflare")
    fake_pkg.CloudflareError = type("CloudflareError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "cloudflare", fake_pkg)

    path = Path(psh.__file__).parent / "plugin" / "cloudflare" / "fqdns.py"
    loader = SourceFileLoader("cloudflare_fqdns_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    # Quiet, capturable console so progress bars / warnings don't spam test output.
    rec = Console(file=io.StringIO(), record=True, width=200)
    monkeypatch.setattr(sc, "console", rec)
    return module, sc, fake_pkg


# --------------------------------------------------------------------------------------------
# fetch_proxied_fqdns
# --------------------------------------------------------------------------------------------

def test_fetch_builds_structure_and_merges_origins(fqdns):
    module, _sc, _cf = fqdns
    client = FakeClient(
        accounts=[_ns(id="acct1")],
        zones_by_account={"acct1": [_ns(id="zoneA", name="example.com")]},
        records_by_zone={
            "zoneA": [
                _ns(name="www.example.com", content="1.2.3.4"),
                _ns(name="www.example.com", content="2606:4700::1"),
                _ns(name="blog.example.com", content="cname.target."),
            ]
        },
    )
    result, conflicts = module.fetch_proxied_fqdns(client)
    assert result == {
        "www.example.com": {"zone_id": "zoneA", "origins": ["1.2.3.4", "2606:4700::1"]},
        "blog.example.com": {"zone_id": "zoneA", "origins": ["cname.target."]},
    }
    assert conflicts == {}


def test_fetch_multiple_accounts_all_scanned(fqdns):
    module, _sc, _cf = fqdns
    client = FakeClient(
        accounts=[_ns(id="a1"), _ns(id="a2")],
        zones_by_account={
            "a1": [_ns(id="z1", name="one.edu")],
            "a2": [_ns(id="z2", name="two.edu")],
        },
        records_by_zone={
            "z1": [_ns(name="a.one.edu", content="1.1.1.1")],
            "z2": [_ns(name="b.two.edu", content="2.2.2.2")],
        },
    )
    result, conflicts = module.fetch_proxied_fqdns(client)
    assert set(result) == {"a.one.edu", "b.two.edu"}
    assert result["b.two.edu"]["zone_id"] == "z2"
    assert conflicts == {}


def test_fetch_same_fqdn_across_zones_keeps_first_zone_and_warns(fqdns):
    module, sc, _cf = fqdns
    client = FakeClient(
        accounts=[_ns(id="a1")],
        zones_by_account={"a1": [_ns(id="zFirst", name="first.edu"), _ns(id="zSecond", name="second.edu")]},
        records_by_zone={
            "zFirst": [_ns(name="dup.example.edu", content="1.1.1.1")],
            "zSecond": [_ns(name="dup.example.edu", content="2.2.2.2")],
        },
    )
    result, conflicts = module.fetch_proxied_fqdns(client)
    assert result["dup.example.edu"]["zone_id"] == "zFirst"
    assert result["dup.example.edu"]["origins"] == ["1.1.1.1", "2.2.2.2"]
    assert conflicts == {"dup.example.edu": ["zFirst", "zSecond"]}
    assert "more than one Cloudflare zone" in sc.console.export_text()


def test_fetch_zero_zones_raises(fqdns):
    module, _sc, _cf = fqdns
    client = FakeClient(accounts=[_ns(id="a1")], zones_by_account={"a1": []}, records_by_zone={})
    with pytest.raises(module.CloudflareFqdnsError):
        module.fetch_proxied_fqdns(client)


def test_fetch_zero_proxied_warns_not_fatal(fqdns):
    module, sc, _cf = fqdns
    client = FakeClient(
        accounts=[_ns(id="a1")],
        zones_by_account={"a1": [_ns(id="z1", name="empty.edu")]},
        records_by_zone={"z1": []},
    )
    result, conflicts = module.fetch_proxied_fqdns(client)
    assert result == {}
    assert conflicts == {}
    assert "zero proxied FQDNs" in sc.console.export_text()


def test_fetch_api_error_wrapped(fqdns):
    module, _sc, cf = fqdns
    client = FakeClient(
        accounts=[_ns(id="a1")],
        zones_by_account={"a1": [_ns(id="z1", name="x.edu")]},
        records_by_zone={},
        records_error=cf.CloudflareError("boom"),
    )
    with pytest.raises(module.CloudflareFqdnsError):
        module.fetch_proxied_fqdns(client)


# --------------------------------------------------------------------------------------------
# write_fqdns_atomic / _load_existing
# --------------------------------------------------------------------------------------------

def test_write_atomic_replaces_symlink_with_plain_file(fqdns, tmp_path):
    module, _sc, _cf = fqdns
    target = tmp_path / "fqdns.json"
    real = tmp_path / "dated.json"
    real.write_text("{}\n")
    target.symlink_to(real)
    assert target.is_symlink()

    data = {"host.edu": {"zone_id": "z", "origins": ["1.1.1.1"]}}
    module.write_fqdns_atomic(str(target), data)

    assert not target.is_symlink()  # replaced with a plain file
    assert json.loads(target.read_text()) == data
    assert real.read_text() == "{}\n"  # the old symlink target is untouched


def test_load_existing_missing_returns_empty(fqdns, tmp_path):
    module, _sc, _cf = fqdns
    assert module._load_existing(str(tmp_path / "nope.json")) == {}


def test_load_existing_malformed_exits(fqdns, tmp_path):
    module, _sc, _cf = fqdns
    bad = tmp_path / "fqdns.json"
    bad.write_text("{not json")
    with pytest.raises(SystemExit):
        module._load_existing(str(bad))


def test_load_existing_tolerates_old_array_format(fqdns, tmp_path):
    module, _sc, _cf = fqdns
    old = tmp_path / "fqdns.json"
    old.write_text(json.dumps({"host.edu": ["1.2.3.4", "cname.target."]}))
    loaded = module._load_existing(str(old))
    assert "host.edu" in loaded  # keys usable regardless of value shape


# --------------------------------------------------------------------------------------------
# update_and_load_proxied_fqdns (the setup hook)
# --------------------------------------------------------------------------------------------

def _client_with_one_fqdn():
    return FakeClient(
        accounts=[_ns(id="a1")],
        zones_by_account={"a1": [_ns(id="z1", name="site.edu")]},
        records_by_zone={"z1": [_ns(name="www.site.edu", content="1.2.3.4")]},
    )


def test_hook_force_update_writes_and_loads(fqdns, psh, monkeypatch, tmp_path):
    module, sc, _cf = fqdns
    monkeypatch.chdir(tmp_path)
    client = _client_with_one_fqdn()
    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    sc.options = psh.parse_args(["--update-cloudflare-fqdns", "its-wws-test1"])

    module.update_and_load_proxied_fqdns()

    written = json.loads((tmp_path / "fqdns.json").read_text())
    assert written == {"www.site.edu": {"zone_id": "z1", "origins": ["1.2.3.4"]}}
    assert sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"] == written
    assert sc.plugin_context["plugin.cloudflare"]["fqdn_zone_conflicts"] == {}


def test_hook_fresh_single_site_does_not_fetch(fqdns, psh, monkeypatch, tmp_path):
    module, sc, _cf = fqdns
    monkeypatch.chdir(tmp_path)
    existing = {"already.edu": {"zone_id": "z9", "origins": ["9.9.9.9"]}}
    (tmp_path / "fqdns.json").write_text(json.dumps(existing))  # fresh mtime
    client = _client_with_one_fqdn()
    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    sc.options = psh.parse_args(["its-wws-test1"])  # single site, no force

    module.update_and_load_proxied_fqdns()

    assert client.calls["accounts"] == 0  # never fetched
    assert sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"] == existing


def test_hook_fetch_error_exits(fqdns, psh, monkeypatch, tmp_path):
    module, sc, cf = fqdns
    monkeypatch.chdir(tmp_path)
    client = FakeClient(
        accounts=[_ns(id="a1")],
        zones_by_account={"a1": [_ns(id="z1", name="x.edu")]},
        records_by_zone={},
        records_error=cf.CloudflareError("boom"),
    )
    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    sc.options = psh.parse_args(["--update-cloudflare-fqdns", "its-wws-test1"])

    with pytest.raises(SystemExit):
        module.update_and_load_proxied_fqdns()


def test_hook_create_tables_does_not_fetch(fqdns, psh, monkeypatch, tmp_path):
    """--create-tables never consumes fqdns and exits before the per-site loop; the hook must not
    trigger a live Cloudflare crawl (which could also abort table creation on a Cloudflare error),
    even with fqdns.json missing."""
    module, sc, _cf = fqdns
    monkeypatch.chdir(tmp_path)  # no fqdns.json present
    client = _client_with_one_fqdn()
    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    sc.options = psh.parse_args(["--create-tables"])

    module.update_and_load_proxied_fqdns()

    assert client.calls["accounts"] == 0  # never fetched despite the missing file
    assert sc.plugin_context["plugin.cloudflare"]["proxied_fqdns"] == {}


def test_hook_traffic_only_suppresses_stale_warning(fqdns, psh, monkeypatch, tmp_path):
    """A traffic-only run (--update) never reads fqdns.json, so a stale file must NOT emit the
    'more than a day old' warning (and must not fetch)."""
    module, sc, _cf = fqdns
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fqdns.json").write_text(json.dumps({"x.edu": {"zone_id": "z", "origins": ["1.1.1.1"]}}))
    stale = time.time() - 2 * 24 * 3600
    os.utime(tmp_path / "fqdns.json", (stale, stale))
    client = _client_with_one_fqdn()
    sc.config = {"Cloudflare": {"enabled": True}}
    sc.plugin_context = {"plugin.cloudflare": {"get_client": lambda: client}}
    sc.options = psh.parse_args(["--update", "its-wws-test1"])

    module.update_and_load_proxied_fqdns()

    assert client.calls["accounts"] == 0
    assert "more than a day old" not in sc.console.export_text()
