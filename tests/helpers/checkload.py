"""Load a check/ package (or one module of it) standalone, without importing the dash-named
main script.

A check module that uses relative imports (`from . import chain`) cannot be loaded with a bare
SourceFileLoader: Python needs a parent package with a __path__ first.  These helpers register a
probe package in sys.modules, then load under it -- the pattern established by
tests/integration/test_check_cloudflare_init.py.
"""
import importlib.util
import sys
from pathlib import Path


def _package_dir(psh, package, base="check"):
    return Path(psh.__file__).resolve().parents[1] / base / package


def _purge(probe):
    """Remove the probe package AND every submodule the import machinery created under it.

    monkeypatch.delitem(..., raising=False) on a key that does not exist yet records NO undo
    entry -- so submodules created later by `from . import chain` would survive teardown and be
    "restored" into the next test under a parent that no longer exists.  Purge by prefix instead
    of guessing a submodule list.  (This is the same class of bug as the reset_sc escape_url leak
    already recorded in this repo.)
    """
    for name in [m for m in sys.modules if m == probe or m.startswith(probe + ".")]:
        del sys.modules[name]


def load_check_package(psh, package, probe, request, base="check"):
    """Execute <base>/<package>/__init__.py as `probe` -- i.e. RUN its hook registration.

    `base` defaults to "check"; pass base="plugin" to load a plugin/ package instead --
    same probe-package mechanics, the two trees are siblings (CLAUDE.md)."""
    pkg_dir = _package_dir(psh, package, base)
    _purge(probe)
    request.addfinalizer(lambda: _purge(probe))
    spec = importlib.util.spec_from_file_location(
        probe, str(pkg_dir / "__init__.py"), submodule_search_locations=[str(pkg_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[probe] = module
    spec.loader.exec_module(module)
    return module


def load_check_module(psh, package, module, probe, request):
    """Load ONE module out of check/<package>/ WITHOUT running the package __init__.py (so no
    hooks are registered).  Relative imports inside it resolve against the real directory: a
    package shell with __path__ set (and NOT exec_module'd) is enough for `from . import chain,
    pantheon` and `from .model import Finding`.
    """
    pkg_dir = _package_dir(psh, package)
    _purge(probe)
    request.addfinalizer(lambda: _purge(probe))
    pkg_spec = importlib.util.spec_from_file_location(
        probe, str(pkg_dir / "__init__.py"), submodule_search_locations=[str(pkg_dir)])
    pkg = importlib.util.module_from_spec(pkg_spec)
    pkg.__path__ = [str(pkg_dir)]          # a package shell: __path__ WITHOUT exec_module
    sys.modules[probe] = pkg
    spec = importlib.util.spec_from_file_location(
        f"{probe}.{module}", str(pkg_dir / f"{module}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{probe}.{module}"] = mod
    spec.loader.exec_module(mod)
    return mod
