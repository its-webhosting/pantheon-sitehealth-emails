"""The ONE sitecustomize the test subprocesses get, so the shims compose instead of colliding.

Python's site.py does `import sitecustomize` -- exactly ONE module of that name is ever imported,
whichever directory wins on sys.path.  While dnsshim and dbshim each owned a `sitecustomize.py` in
its own directory, putting BOTH on PYTHONPATH silently ran only the first: no error, no warning,
the other shim just never patched anything.  A test that needs both (say, a DB abort inside the
CDN-change golden, which needs offline DNS) would have run with the loser inactive -- and the
`not in`-shaped assertions in tests/e2e/test_abort_e2e.py can pass green against a run that did
nothing.

So there is one shim directory (`tests/shims/pyshim`, `conftest.PYSHIM_DIR`) and one
sitecustomize, which activates each shim from its own env var:

    DNS_SHIM_ZONE=<zone.json>   offline DNS      (dnsshim.py)
    DB_SHIM_FAIL=1              a dead database  (dbshim.py)

Both, either, or neither -- they are independent.  With neither set the directory is inert, which
matters because PYTHONPATH is inherited by the PATH-based fake `terminus` (a Python script too).
`tests/integration/test_shim_composability.py` guards both properties: only one sitecustomize
exists, and both shims really do take effect in a single interpreter.
"""

import dbshim  # noqa: F401  -- each module self-activates at import time, gated on its env var
import dnsshim  # noqa: F401
