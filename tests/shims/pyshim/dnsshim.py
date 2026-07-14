"""Offline DNS for the subprocess-based e2e goldens.

run_program() launches the real program in a subprocess, so an in-process monkeypatch of
dns_classify.resolve cannot reach it.  Python imports `sitecustomize` at interpreter startup if it
is importable, so putting this directory on PYTHONPATH replaces dnspython's resolver BEFORE the
program imports anything -- the same philosophy as the PATH-based fake `terminus` shim.  This
module is imported by that one sitecustomize (see sitecustomize.py for why there is only one).

Zone file (JSON, named by the DNS_SHIM_ZONE env var):

    { "name|RRTYPE": ["value", ...], ... }
    e.g. {"x.example.edu|CNAME": ["live-x.pantheonsite.io."]}

An absent key raises NoAnswer -- the definitive "no such record" answer.  With no DNS_SHIM_ZONE
set this module does nothing, so the directory can sit on PYTHONPATH harmlessly (the terminus
shim subprocess inherits PYTHONPATH too, and must not break).
"""
import json
import os

_zone_path = os.environ.get("DNS_SHIM_ZONE")
if _zone_path:
    import dns.resolver

    with open(_zone_path, encoding="utf-8") as _f:
        _ZONE = json.load(_f)

    class _Rdata:
        def __init__(self, value):
            self.target = value        # CNAME answers read .target
            self.address = value       # A/AAAA answers read .address

    def _fake_resolve(name, rrtype, *args, **kwargs):
        key = f"{str(name).rstrip('.').lower()}|{rrtype}"
        values = _ZONE.get(key)
        if values is None:
            raise dns.resolver.NoAnswer
        return [_Rdata(v) for v in values]

    dns.resolver.resolve = _fake_resolve
