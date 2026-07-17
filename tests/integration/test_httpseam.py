"""Integration tests for check/cloudflare/httpseam.py internals that the cache tests
(which monkeypatch the fetch seam away) cannot cover: exception containment for
remote-derived URLs, and the per-FQDN ClientPool.

Offline by construction: httpx raises InvalidURL during URL parsing, before any socket
is opened, and the ClientPool tests never issue a request.
"""
import importlib.util
import sys
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

FQDN = "www.example.edu"


@pytest.fixture
def httpseam(psh, monkeypatch):
    """Load httpseam.py under a probe package so its relative import (.pages) resolves."""
    pkg_dir = Path(psh.__file__).resolve().parents[1] / "check" / "cloudflare"
    package = types.ModuleType("cf_seam_pkg")
    package.__path__ = [str(pkg_dir)]
    monkeypatch.setitem(sys.modules, "cf_seam_pkg", package)
    monkeypatch.delitem(sys.modules, "cf_seam_pkg.pages", raising=False)
    loader = SourceFileLoader("cf_seam_pkg.httpseam", str(pkg_dir / "httpseam.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "cf_seam_pkg.httpseam", module)
    loader.exec_module(module)
    return module


def test_invalid_url_is_contained_not_raised(httpseam):
    # Regression (code review): httpx.InvalidURL does NOT subclass httpx.HTTPError; a
    # control byte in a remote href previously escaped the seam and aborted the whole
    # run.  httpx raises during URL parsing, so this never touches the network.
    result = httpseam.fetch(f"https://{FQDN}/foo\x01bar", fqdn=FQDN, timeout=1,
                            user_agent="test")
    assert result.error == "connection"
    assert "invalid URL" in result.error_detail


def test_absurdly_long_url_is_contained(httpseam):
    result = httpseam.fetch(f"https://{FQDN}/" + "a" * 70000, fqdn=FQDN, timeout=1,
                            user_agent="test")
    assert result.error == "connection"


def test_client_pool_reuses_and_closes(httpseam):
    with httpseam.ClientPool(timeout=1, user_agent="test") as pool:
        secure = pool.client(True)
        assert pool.client(True) is secure          # reused, not rebuilt
        insecure = pool.client(False)
        assert insecure is not secure               # verify modes are separate clients
        assert pool.client(False) is insecure
    assert pool._clients == {}                      # context exit closed and cleared


def test_fetch_without_pool_still_works_ephemerally(httpseam):
    # pool=None keeps the old per-call client behavior (used by nothing in production
    # after the pool change, but the seam contract allows it).
    result = httpseam.fetch(f"https://{FQDN}/x\x00y", fqdn=FQDN, timeout=1,
                            user_agent="test", pool=None)
    assert result.error == "connection"
