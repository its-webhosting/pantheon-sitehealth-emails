"""Offline tests for the find-platform-domains-cloudflare utility (SPEC section 7).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone scripts and check/plugin modules (see
tests/unit/test_find_platform_domains_dns.py).  It is loaded FRESH PER TEST so no module-level
state leaks between tests -- which is also what makes monkeypatching module attributes safe in
the main() tests at the bottom (SPEC section 4, seams).

Imports: each task ADDS to the block below, in the task that first needs the name.  Editing the
top block is fine; adding an import further down the file is what ruff's E402 forbids, and E402
is not in the tests/** ignore list.

TEMPORARY, deleted with the script after the Pantheon CDN migration -- see
development/2026-07-30-platform-domain-util2/SPEC.md section 11.
"""
import importlib.util
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "find-platform-domains-cloudflare"


@pytest.fixture
def fpc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("find_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def record(**overrides):
    """A stand-in for a cloudflare RecordResponse; the code under test only reads attributes."""
    fields = {"type": "CNAME", "name": "www.example.edu", "id": "rec-1",
              "content": "live-umich-example1.pantheonsite.io", "proxied": True,
              "ttl": 1, "comment": None, "tags": [], "settings": None}
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


# --- Task 1: the match rule ------------------------------------------------------------------

def test_normalize_strips_case_whitespace_and_the_root_dot(fpc):
    assert fpc.normalize("  LIVE-Umich-X.PantheonSite.IO.  ") == "live-umich-x.pantheonsite.io"


@pytest.mark.parametrize("name", [
    "live-umich-example1.pantheonsite.io",
    "LIVE-UMICH-EXAMPLE1.PANTHEONSITE.IO",
    "live-umich-example1.pantheonsite.io.",
])
def test_is_platform_domain_accepts_platform_hostnames(fpc, name):
    assert fpc.is_platform_domain(name) is True


@pytest.mark.parametrize("name", [
    "notpantheonsite.io",          # the leading dot in PLATFORM_SUFFIX is what rejects this
    "pantheonsite.io",             # the bare apex is not a site's platform domain
    "www.example.edu",
    "live-umich-example1.pantheonsite.io.evil.example",
])
def test_is_platform_domain_rejects_everything_else(fpc, name):
    assert fpc.is_platform_domain(name) is False
