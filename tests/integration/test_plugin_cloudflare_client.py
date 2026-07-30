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
            # Set them as ATTRIBUTES too: pinned_client nulls the credentials the config did not
            # supply, and that is only observable on the instance.
            for name, value in kwargs.items():
                setattr(self, name, value)

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
    assert seen == {"api_email": "e@example.com", "api_key": "k",
                    "base_url": module.API_BASE_URL}


def test_auth_prefers_api_token(load_client, monkeypatch):
    module, sc = load_client
    sc.config["Cloudflare"]["api_token"] = "tok-123"
    seen = {}
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare(seen))

    module.build_client()
    assert seen == {"api_token": "tok-123", "base_url": module.API_BASE_URL}


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
        # SimpleNamespace, not object(): pinned_client setattr()s the unsupplied credential
        # fields onto whatever the constructor returned, and object() cannot hold attributes.
        obj = types.SimpleNamespace(**kwargs)
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


# ---------------------------------------------------------------------------------------------
# Pinning the client against the ambient environment.
#
# Found by measurement while building find-platform-domains-cloudflare, then flagged by review:
# build_client's own docstring promised "There is no direct-environment fallback", and the SDK
# provides four.  See development/2026-07-30-platform-domain-util2/SPEC.md R2a.
# ---------------------------------------------------------------------------------------------


def test_build_client_pins_the_base_url_and_clears_custom_headers(load_client, monkeypatch):
    """$CLOUDFLARE_BASE_URL would otherwise redirect every request -- sending the configured
    credential to an arbitrary host -- and $CLOUDFLARE_CUSTOM_HEADERS is merged LAST into
    default_headers, overriding any credential pinning above it."""
    module, sc = load_client
    seen = {}
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare(seen))
    sc.config = {"Cloudflare": {"api_token": "tok-123"}}

    client = module.build_client()

    assert seen["base_url"] == module.API_BASE_URL
    assert client._custom_headers == {}


@pytest.mark.parametrize(("config", "supplied", "nulled"), [
    ({"api_token": "tok-123"}, ["api_token"], ["api_key", "api_email", "user_service_key"]),
    ({"email": "e@example.com", "api_key": "k"}, ["api_email", "api_key"],
     ["api_token", "user_service_key"]),
])
def test_build_client_nulls_every_credential_the_config_did_not_supply(
        load_client, monkeypatch, config, supplied, nulled):
    """The SDK back-fills each credential left None from the environment, and auth_headers then
    returns the FIRST of email -> key -> token -> user_service_key that is set -- so an ambient
    CLOUDFLARE_EMAIL beats a configured api_token and the token is never sent."""
    module, sc = load_client
    monkeypatch.setattr(module, "Cloudflare", _make_cloudflare())
    sc.config = {"Cloudflare": config}

    client = module.build_client()

    for field in nulled:
        assert getattr(client, field) is None, f"{field} was left for the environment to fill"
    for field in supplied:
        assert getattr(client, field, "unset") != "unset"


def test_build_client_sends_only_the_configured_credential(psh, monkeypatch):
    """The security property itself, against the REAL SDK -- the fake above can only pin the
    mechanism.  Skipped when the optional [cloudflare] extra is absent, which is why the
    mechanism tests exist alongside it.
    """
    pytest.importorskip("cloudflare")
    from cloudflare._models import FinalRequestOptions

    import script_context as sc

    path = Path(psh.__file__).resolve().parents[1] / "plugin" / "cloudflare" / "client.py"
    loader = SourceFileLoader("cloudflare_client_real_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)          # the REAL cloudflare package, not the fake

    ambient = {"CLOUDFLARE_API_KEY": "ambient-key", "CLOUDFLARE_EMAIL": "ambient@example.edu",
               "CLOUDFLARE_API_USER_SERVICE_KEY": "ambient-usk",
               "CLOUDFLARE_BASE_URL": "https://evil.example/v4",
               "CLOUDFLARE_CUSTOM_HEADERS": "X-Auth-Email: attacker@evil.example"}
    for name, value in ambient.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sc, "config", {"Cloudflare": {"api_token": "tok-123"}}, raising=False)

    client = module.build_client()
    request = client._build_request(FinalRequestOptions(method="get", url="/zones"))

    assert str(request.url).startswith("https://api.cloudflare.com/client/v4/")
    assert request.headers.get("authorization") == "Bearer tok-123"
    # Named explicitly, NOT as a set-intersection against the env var strings: the value of
    # $CLOUDFLARE_CUSTOM_HEADERS is "X-Auth-Email: attacker@..." while the header it injects is
    # just "attacker@...", so an intersection silently misses route 3 entirely.  Mutation-tested:
    # deleting `client._custom_headers = {}` left the intersection form green.
    assert request.headers.get("x-auth-email") is None
    assert request.headers.get("x-auth-key") is None
    assert "evil.example" not in str(request.headers)
