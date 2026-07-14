"""The subprocess shims must COMPOSE, not collide.

site.py imports exactly one module named `sitecustomize` -- whichever directory wins on sys.path.
When dnsshim and dbshim each had their own `sitecustomize.py`, putting both dirs on PYTHONPATH ran
only one of them, silently: no error, no warning, the loser simply never patched anything.  A DB
abort test whose assertions are `not in`-shaped (tests/e2e/test_abort_e2e.py) would then pass green
against a run that never failed.  These tests fail if anyone reintroduces that shape.
"""
import json
import os
import subprocess
import sys

import pytest

from conftest import PYSHIM_DIR, SHIM_DIR

pytestmark = pytest.mark.integration


def _probe(tmp_path, env_extra, code):
    """Run `code` in a fresh interpreter with PYSHIM_DIR on PYTHONPATH (so sitecustomize loads)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(PYSHIM_DIR), env.get("PYTHONPATH", "")]).rstrip(
        os.pathsep
    )
    env.pop("DNS_SHIM_ZONE", None)
    env.pop("DB_SHIM_FAIL", None)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code], env=env, cwd=str(tmp_path), capture_output=True, text=True
    )


def test_exactly_one_sitecustomize_lives_under_tests_shims():
    # Two would mean one of them never runs -- see this module's docstring.  A new subprocess shim
    # goes in pyshim/ as its own module, imported by pyshim/sitecustomize.py.
    found = sorted(p.relative_to(SHIM_DIR) for p in SHIM_DIR.rglob("sitecustomize.py"))
    assert [str(p) for p in found] == [os.path.join("pyshim", "sitecustomize.py")]


def test_both_shims_are_active_in_one_interpreter(tmp_path):
    # The stacking scenario that used to be impossible: DNS offline AND the database dead, in the
    # same subprocess.  If sitecustomize ever runs only one of them, one of these prints changes.
    zone = tmp_path / "zone.json"
    zone.write_text(json.dumps({"shim.example.edu|A": ["192.0.2.7"]}))
    proc = _probe(
        tmp_path,
        {"DNS_SHIM_ZONE": str(zone), "DB_SHIM_FAIL": "1"},
        """
import dns.resolver
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
print("DNS:", dns.resolver.resolve("shim.example.edu", "A")[0].address)
try:
    Session.get(None, object, 1)
except OperationalError as e:
    print("DB: OperationalError")
else:
    print("DB: no failure -- the db shim did not load")
""",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DNS: 192.0.2.7" in proc.stdout, proc.stdout + proc.stderr
    assert "DB: OperationalError" in proc.stdout, proc.stdout + proc.stderr


def test_the_shim_dir_is_inert_with_neither_env_var(tmp_path):
    # PYTHONPATH is inherited by the PATH-based fake `terminus` (a Python script too), so the mere
    # presence of the shim dir must patch nothing.
    proc = _probe(
        tmp_path,
        {},
        """
import dns.resolver
from sqlalchemy.orm import Session
print("DNS patched:", dns.resolver.resolve.__module__ == "dnsshim")
print("DB patched:", Session.get.__module__ == "dbshim")
""",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DNS patched: False" in proc.stdout
    assert "DB patched: False" in proc.stdout
