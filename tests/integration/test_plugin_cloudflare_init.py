"""Integration tests for plugin/cloudflare/__init__.py registration gating.

The package must register its two setup hooks (in order: ips, then fqdns) only when
[Cloudflare].enabled is true, and must publish the shared-client accessor in the state
bag so ips.py/fqdns.py can reach it without importing this package.

Registration goes through sc.add_hook(), not a raw sc.hooks['setup'].append() -- that is
what validates the phase name.  These tests pin both the gating and the hook order.

Loading trick: as in test_check_cloudflare_init.py, the real __init__.py is executed
under a probe name with submodule_search_locations pointing at the package dir, so its
relative imports (.client/.ips/.fqdns) resolve without touching
sys.modules["plugin.cloudflare"].
"""
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ENABLED_CONFIG = {"Cloudflare": {"enabled": True, "api_token": "t0ken"}}


def _load_init(psh, monkeypatch, probe_name="cf_plugin_probe"):
    pkg_dir = Path(psh.__file__).parent / "plugin" / "cloudflare"
    spec = importlib.util.spec_from_file_location(
        probe_name,
        str(pkg_dir / "__init__.py"),
        submodule_search_locations=[str(pkg_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, probe_name, module)
    for sub in ("client", "ips", "fqdns"):
        monkeypatch.delitem(sys.modules, f"{probe_name}.{sub}", raising=False)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "config",
    [
        {},  # no [Cloudflare] at all
        {"Cloudflare": {}},  # section present, no 'enabled' key
        {"Cloudflare": {"enabled": False}},
    ],
    ids=["no-section", "no-enabled-key", "disabled"],
)
def test_disabled_configs_register_nothing(psh, reset_sc, monkeypatch, config):
    sc = reset_sc
    sc.config = config
    _load_init(psh, monkeypatch)
    assert sc.hooks["setup"] == []
    assert "plugin.cloudflare" not in sc.plugin_context


def test_enabled_registers_both_setup_hooks_in_order(psh, reset_sc, monkeypatch):
    sc = reset_sc
    sc.config = ENABLED_CONFIG
    _load_init(psh, monkeypatch)
    # ips before fqdns: the client is built lazily, so this order is not a correctness
    # dependency, but it is the documented/observed run order -- pin it so a reordering
    # is a deliberate act.
    assert [h["name"] for h in sc.hooks["setup"]] == [
        "plugin.cloudflare.ips.get_cloudflare_ips",
        "plugin.cloudflare.fqdns.update_and_load_proxied_fqdns",
    ]
    assert all(callable(h["func"]) for h in sc.hooks["setup"])


def test_enabled_publishes_get_client_in_the_state_bag(psh, reset_sc, monkeypatch):
    sc = reset_sc
    sc.config = ENABLED_CONFIG
    _load_init(psh, monkeypatch)
    assert callable(sc.plugin_context["plugin.cloudflare"]["get_client"])


def test_registration_uses_add_hook(psh, reset_sc, monkeypatch):
    """A raw sc.hooks['setup'].append() would bypass phase-name validation."""
    sc = reset_sc
    sc.config = ENABLED_CONFIG
    seen = []
    real_add_hook = sc.add_hook
    monkeypatch.setattr(
        sc, "add_hook", lambda phase, target: (seen.append(phase), real_add_hook(phase, target))[1]
    )
    _load_init(psh, monkeypatch)
    assert seen == ["setup", "setup"]
