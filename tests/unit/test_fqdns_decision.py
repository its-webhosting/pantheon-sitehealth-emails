"""Unit tests for plugin/cloudflare/fqdns.py `decide_fqdns_update` (pure decision function).

Load fqdns.py standalone with a fake `cloudflare` module (so no dependency on the real SDK); the
decision function itself does no I/O and touches no Cloudflare API.
"""
import importlib.util
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

pytestmark = pytest.mark.unit


@pytest.fixture
def fqdns(psh, monkeypatch):
    fake_pkg = types.ModuleType("cloudflare")
    fake_pkg.CloudflareError = type("CloudflareError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "cloudflare", fake_pkg)

    path = Path(psh.__file__).parent / "plugin" / "cloudflare" / "fqdns.py"
    loader = SourceFileLoader("cloudflare_fqdns_probe", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _decide(fqdns, **overrides):
    args = dict(
        exists=True,
        age_seconds=0,
        multi_site=False,
        force=False,
        suppress=False,
        traffic_only=False,
    )
    args.update(overrides)
    return fqdns.decide_fqdns_update(**args)


def test_force_always_updates(fqdns):
    # force wins even in a traffic-only run and even with a fresh single-site file.
    assert _decide(fqdns, force=True, traffic_only=True)[0] is True
    assert _decide(fqdns, force=True, exists=True, age_seconds=0)[0] is True


def test_traffic_only_skips(fqdns):
    assert _decide(fqdns, traffic_only=True, exists=False)[0] is False
    assert _decide(fqdns, traffic_only=True, exists=True, age_seconds=10**9, multi_site=True)[0] is False


def test_missing_file_updates(fqdns):
    assert _decide(fqdns, exists=False)[0] is True


def test_stale_multi_updates(fqdns):
    assert _decide(fqdns, exists=True, age_seconds=fqdns.STALE_SECONDS + 1, multi_site=True)[0] is True


def test_stale_multi_but_suppressed_skips(fqdns):
    assert _decide(
        fqdns, exists=True, age_seconds=fqdns.STALE_SECONDS + 1, multi_site=True, suppress=True
    )[0] is False


def test_stale_single_site_skips(fqdns):
    assert _decide(fqdns, exists=True, age_seconds=fqdns.STALE_SECONDS + 1, multi_site=False)[0] is False


def test_fresh_multi_skips(fqdns):
    assert _decide(fqdns, exists=True, age_seconds=0, multi_site=True)[0] is False


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    exists=st.booleans(),
    age_seconds=st.floats(min_value=0, max_value=10**9, allow_nan=False),
    multi_site=st.booleans(),
    force=st.booleans(),
    suppress=st.booleans(),
    traffic_only=st.booleans(),
)
def test_decision_invariants(fqdns, exists, age_seconds, multi_site, force, suppress, traffic_only):
    should, reason = fqdns.decide_fqdns_update(
        exists=exists,
        age_seconds=age_seconds,
        multi_site=multi_site,
        force=force,
        suppress=suppress,
        traffic_only=traffic_only,
    )
    assert isinstance(should, bool)
    assert isinstance(reason, str) and reason
    if force:
        assert should is True
    if traffic_only and not force:
        assert should is False
