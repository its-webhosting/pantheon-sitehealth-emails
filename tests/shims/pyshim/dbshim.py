"""Make the traffic DB fail inside a subprocess run, for tests/e2e/test_abort_e2e.py.

Python auto-imports sitecustomize at interpreter startup, before the program imports anything --
the same trick dnsshim.py uses to replace dns.resolver.resolve, and it is that one sitecustomize
(see sitecustomize.py) which imports this module.  Active only when DB_SHIM_FAIL is set, so having
the shim directory on PYTHONPATH is otherwise inert (it is inherited by the PATH-based fake
`terminus`, which is a Python script too).

Session.get() is the seam: sessionmaker builds a runtime SUBCLASS of Session and does not override
get(), so patching the base class here reaches the program's session.  Note the first call to fire
is inside update_traffic_rows()' session.merge() -- SQLAlchemy's Session._merge() calls self.get()
for a persistent key that is not in the identity map -- not build_traffic_table_rows() as one might
assume.  Either way the failure lands INSIDE a db_retry() unit, which is what the test asserts.
"""

import os

if os.environ.get("DB_SHIM_FAIL"):
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    def _dead_get(self, *args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("(2013, 'Lost connection')"))

    Session.get = _dead_get
