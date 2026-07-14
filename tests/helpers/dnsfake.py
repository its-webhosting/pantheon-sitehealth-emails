"""The offline DNS seam used by the new DNS-touching tests, plus a capturable console.

dns_classify.resolve is the ONE monkeypatchable DNS seam (CLAUDE.md); patching it here keeps
the offline tier off the network.  A zone maps (name, rrtype) -> a list of values, or an
exception INSTANCE to raise.  An absent key raises NoAnswer -- the definitive "no such record"
answer, which is what the healthy path looks like.
"""
import io

import dns.resolver
from rich.console import Console


class FakeCname:
    def __init__(self, target):
        self.target = target


class FakeAddress:
    def __init__(self, address):
        self.address = address


def make_resolver(zone, calls=None):
    """Build a stand-in for dns_classify.resolve over `zone`.

    `calls`, if given, records every (name, rrtype) looked up -- so a test can assert an IP
    literal was never resolved, or that a clean site issued no lookups at all.
    """
    def _resolve(name, rrtype):
        key = (str(name).rstrip(".").lower(), rrtype)
        if calls is not None:
            calls.append(key)
        value = zone.get(key)
        if value is None:
            raise dns.resolver.NoAnswer
        if isinstance(value, Exception):
            raise value
        if rrtype == "CNAME":
            return [FakeCname(v) for v in value]
        return [FakeAddress(v) for v in value]
    return _resolve


def patch_resolve(monkeypatch, zone, calls=None):
    """Point dns_classify.resolve at `zone` for the duration of one test."""
    import dns_classify
    monkeypatch.setattr(dns_classify, "resolve", make_resolver(zone, calls))


def recording_console(monkeypatch, sc, width=200):
    """Replace sc.console with a wide recording Console; read it back with export_text().

    NOT capsys: rich wraps at width 80 on a non-tty, so a substring assertion on capsys output
    breaks as soon as a message grows and the wrap lands mid-phrase.  width=200 + record=True is
    the pattern the repo already uses (tests/integration/test_plugin_cloudflare_fqdns.py:73-75).

    `width` exists so a test can deliberately reproduce PRODUCTION's console: the real sc.console
    is a bare Console(), which on a non-tty (cron, nohup, a redirect -- how every --all run is
    launched) is 80 columns wide and hard-wraps.  The wide default here is what made the suite blind
    to a wrapped, dangerous-to-paste resume command.
    """
    console = Console(file=io.StringIO(), record=True, width=width)
    monkeypatch.setattr(sc, "console", console)
    return console
