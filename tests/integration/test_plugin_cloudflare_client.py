"""Integration tests for plugin/cloudflare/client.py (the shared Cloudflare client factory).

The auth-selection logic (api_token preferred, else email+api_key, else exit) lives here now,
so its tests live here too.  As with test_plugin_cloudflare.py, a fake `cloudflare` module is
injected into sys.modules before the plugin file is loaded, so `from cloudflare import Cloudflare`
binds to the fake.
"""
import importlib.util
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _make_cloudflare(seen_kwargs=None):
    class FakeCloudflare:
        def __init__(self, **kwargs):
            if seen_kwargs is not None:
                seen_kwargs.update(kwargs)

    return FakeCloudflare


@pytest.fixture
def load_client(psh, monkeypatch):
    """Load plugin/cloudflare/client.py with a fake `cloudflare` module, returning (module, sc)."""
    import script_context as sc

    fake_pkg = types.ModuleType("cloudflare")
    fake_pkg.Cloudflare = object  # placeholder; each test monkeypatches module.Cloudflare
    monkeypatch.setitem(sys.modules, "cloudflare", fake_pkg)

    path = Path(psh.__file__).resolve().parents[1] / "plugin" / "cloudflare" / "client.py"
    loader = SourceFileLoader("cloudflare_client_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    sc.config = {"Cloudflare": {"email": "e@example.com", "api_key": "k"}}
    sc.plugin_context = {}
    return module, sc


def test_auth_uses_email_and_api_key(load_client, monkeypatch):
    module, _sc = load_client
    seen = {}
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare(seen))

    module.build_client()
    assert seen == {"api_email": "e@example.com", "api_key": "k"}


def test_auth_prefers_api_token(load_client, monkeypatch):
    module, sc = load_client
    sc.config["Cloudflare"]["api_token"] = "tok-123"
    seen = {}
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare(seen))

    module.build_client()
    assert seen == {"api_token": "tok-123"}


def test_auth_missing_credentials_exits(load_client, monkeypatch):
    """Enabled but neither api_token nor email+api_key -> a clear exit, not a bare KeyError."""
    module, sc = load_client
    sc.config["Cloudflare"] = {}
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare())

    with pytest.raises(SystemExit):
        module.build_client()


def test_get_client_builds_once_and_caches(load_client, monkeypatch):
    """get_client() builds the shared client lazily on first use and caches it in plugin_context
    (setdefault, so it works from an empty plugin_context with no pre-seeded bag)."""
    module, sc = load_client
    sc.plugin_context = {}
    builds = []

    def factory(**kwargs):
        obj = object()
        builds.append(obj)
        return obj

    monkeypatch.setattr(module, "Cloudflare", factory)

    first = module.get_client()
    second = module.get_client()

    assert first is second                       # cached
    assert len(builds) == 1                       # built exactly once
    assert sc.plugin_context["plugin.cloudflare"]["client"] is first


def test_get_client_returns_preseeded_without_building(load_client, monkeypatch):
    """If a client is already present (e.g. seeded by a test), get_client returns it and never
    calls the factory."""
    module, sc = load_client
    sentinel = object()
    sc.plugin_context = {"plugin.cloudflare": {"client": sentinel}}

    def boom(**kwargs):
        raise AssertionError("should not build when a client is already present")

    monkeypatch.setattr(module, "Cloudflare", boom)

    assert module.get_client() is sentinel
