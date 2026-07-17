"""Integration tests for check/cloudflare/__init__.py registration gating.

The package must register its two hooks ONLY when [Cloudflare].enabled AND
[Cloudflare.cachecheck].enabled are both true; missing required settings and missing
Python dependencies are loud fatal errors.

Loading trick: the real __init__.py is executed under a probe name with
submodule_search_locations pointing at the package dir, so its relative imports
(.egress/.cache/.cfg) resolve without touching sys.modules["check.cloudflare"].
The missing-dependency test points submodule_search_locations at a temp dir whose
egress.py imports a nonexistent package.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ENABLED_CONFIG = {
    "Cloudflare": {
        "enabled": True,
        "api_token": "t0ken",
        "cachecheck": {"enabled": True, "account_id": "acct", "list_name": "nets"},
    }
}


def _load_init(psh, monkeypatch, probe_name="cf_check_probe", search_dir=None):
    pkg_dir = Path(psh.__file__).resolve().parents[1] / "check" / "cloudflare"
    spec = importlib.util.spec_from_file_location(
        probe_name,
        str(pkg_dir / "__init__.py"),
        submodule_search_locations=[str(search_dir or pkg_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    # Relative imports (.egress/.cache/.cfg) resolve against sys.modules[probe_name], so the
    # probe package must be registered before exec; monkeypatch restores sys.modules after.
    monkeypatch.setitem(sys.modules, probe_name, module)
    for sub in ("egress", "cache", "cfg"):
        monkeypatch.delitem(sys.modules, f"{probe_name}.{sub}", raising=False)
    spec.loader.exec_module(module)
    return module


def _registered(sc):
    return (
        [h["name"] for h in sc.hooks["setup"]],
        [h["name"] for h in sc.hooks["site_post_dns"]],
    )


@pytest.mark.parametrize(
    "config",
    [
        {},  # no [Cloudflare] at all
        {"Cloudflare": {"enabled": False}},
        {"Cloudflare": {"enabled": True, "api_token": "t"}},  # no cachecheck subsection
        {"Cloudflare": {"enabled": True, "api_token": "t",
                        "cachecheck": {"enabled": False}}},
    ],
    ids=["no-section", "cloudflare-disabled", "no-cachecheck", "cachecheck-disabled"],
)
def test_disabled_configs_register_nothing(psh, reset_sc, monkeypatch, config):
    sc = reset_sc
    sc.config = config
    _load_init(psh, monkeypatch)
    assert _registered(sc) == ([], [])


def test_enabled_registers_both_hooks(psh, reset_sc, monkeypatch):
    sc = reset_sc
    sc.config = ENABLED_CONFIG
    _load_init(psh, monkeypatch)
    setup_hooks, dns_hooks = _registered(sc)
    assert setup_hooks == ["check.cloudflare.egress.check_egress_ip"]
    assert dns_hooks == ["check.cloudflare.cache.check_cloudflare_cache"]


@pytest.mark.parametrize(
    "cachecheck, missing",
    [
        ({"enabled": True}, "account_id, list_name"),
        ({"enabled": True, "account_id": "a"}, "list_name"),
        ({"enabled": True, "list_name": "l"}, "account_id"),
    ],
)
def test_enabled_but_missing_required_settings_is_fatal(psh, reset_sc, monkeypatch, cachecheck, missing):
    sc = reset_sc
    sc.config = {"Cloudflare": {"enabled": True, "api_token": "t", "cachecheck": cachecheck}}
    with pytest.raises(SystemExit) as exc:
        _load_init(psh, monkeypatch)
    assert missing in str(exc.value)


def test_internal_import_typo_reraises_instead_of_install_hint(psh, reset_sc, monkeypatch, tmp_path):
    # Regression (code review): an ImportError raised by a typo'd INTERNAL import inside
    # egress.py/cache.py must re-raise with the real traceback, not exit with the
    # misleading "install .[cloudflare]" message (e.name is the package-local module
    # path in that case, e.g. '<probe>.cfg').
    sc = reset_sc
    sc.config = ENABLED_CONFIG
    (tmp_path / "egress.py").write_text("from .cfg import nonexistent_helper\n")
    with pytest.raises(ImportError) as exc:
        _load_init(psh, monkeypatch, probe_name="cf_check_typo_probe", search_dir=tmp_path)
    assert not isinstance(exc.value, SystemExit)
    assert "cfg" in str(exc.value)


def test_missing_python_dependency_is_fatal_with_install_hint(psh, reset_sc, monkeypatch, tmp_path, capsys):
    sc = reset_sc
    sc.config = ENABLED_CONFIG
    # A broken sibling: importing it raises ImportError for a nonexistent package.
    (tmp_path / "egress.py").write_text("import nonexistent_cachecheck_dep_xyz\n")
    with pytest.raises(SystemExit) as exc:
        _load_init(psh, monkeypatch, probe_name="cf_check_broken_probe", search_dir=tmp_path)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "nonexistent_cachecheck_dep_xyz" in out
    assert "uv pip install .[cloudflare]" in out
