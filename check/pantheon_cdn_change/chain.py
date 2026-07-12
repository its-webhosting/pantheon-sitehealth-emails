"""CNAME-chain walking for the Pantheon CDN-change check.  DETECTION ONLY.

There is deliberately NO address lookup in this module.  Replacement addresses come from
Pantheon (check/pantheon_cdn_change/pantheon.py -> terminus domain:dns), never from resolving
the legacy-GCDN name a broken record happens to point at: when that name is STALE it belongs to
a DIFFERENT Pantheon site, and we would email its addresses to the wrong owner (SPEC §4.1).

Every lookup goes through dns_classify.resolve -- the one monkeypatchable DNS seam (CLAUDE.md).
dns.resolver is imported ONLY for its exception classes.

walk() checks `start` itself before resolving anything, so a Cloudflare origin that already IS
a legacy-GCDN name is a hit with zero queries:

     start ---> [ legacy-GCDN name? ] -- yes --> HIT(name)
                        | no
                        v
             [ resolve(name, "CNAME") ]
              |      |       |               |
   NoAnswer / |      | CNAME | Timeout /     | MalformedNameError
   NXDOMAIN   |      | target| NoNameservers | (not a valid DNS name at all)
              v      v       v               v
          NO-HIT  (loop   TRANSIENT       NO-HIT + ATTENTION
                   back)  (UNKNOWN;        (F10 -- MUST NOT escape: the
                          ATTENTION;        per-site loop has no try/except,
                          caller must NOT   so an escaped exception aborts
                          report the FQDN)  the whole run)
                        |
       depth > MAX_CNAME_DEPTH, or the name was already seen (CNAME loop)
                        `--> NO-HIT + ATTENTION
"""
import ipaddress
from typing import NamedTuple

import dns.resolver                       # exception classes only; resolution goes via the seam
from rich.markup import escape as rich_escape

import dns_classify
import script_context as sc

LEGACY_GCDN_SUFFIX = ".pantheonsite.io"   # the legacy Pantheon GCDN (Fastly) edge names
MAX_CNAME_DEPTH = 8


class ChainResult(NamedTuple):
    target: str        # the legacy-GCDN name reached; "" when none was
    transient: bool    # True: a transient resolver error stopped the walk -> result UNKNOWN


def normalize(name: str) -> str:
    """Lowercase, strip whitespace and the trailing root dot dnspython includes."""
    return str(name).strip().rstrip(".").lower()


def is_legacy_gcdn(name: str) -> bool:
    return normalize(name).endswith(LEGACY_GCDN_SUFFIX)


def is_hostname(value: str) -> bool:
    """False for an IPv4/IPv6 literal (a proxied A/AAAA record's content), True for a name.

    Load-bearing, not theoretical: 1003 of the 2323 origins in the current fqdns.json are IP
    literals.  Resolving one would be a pointless query at best.
    """
    name = normalize(value)
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return True
    return False


def walk(start: str) -> ChainResult:
    """Follow the CNAME chain from `start`, looking for a legacy-GCDN name.  See the diagram."""
    name = normalize(start)
    seen = set()
    for hop in range(MAX_CNAME_DEPTH + 1):
        if is_legacy_gcdn(name):
            return ChainResult(name, False)
        if hop == MAX_CNAME_DEPTH:
            break
        if name in seen:
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: CNAME chain for "
                f"{rich_escape(normalize(start))} loops at {rich_escape(name)}")
            return ChainResult("", False)
        seen.add(name)
        try:
            answer = dns_classify.resolve(name, "CNAME")
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return ChainResult("", False)          # definitive: no CNAME here, chain ends
        except (dns.resolver.NoNameservers, dns.resolver.Timeout) as e:
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: could not check "
                f"{rich_escape(normalize(start))} for a legacy-GCDN CNAME "
                f"(transient DNS error at {rich_escape(name)}: {type(e).__name__})")
            return ChainResult("", True)           # UNKNOWN -- never reported as a finding
        except dns_classify.MalformedNameError as e:
            # F10.  A name that is not syntactically valid cannot be in DNS, so it cannot be
            # CNAME'd to the legacy GCDN -- and this MUST NOT escape (the per-site loop has no
            # try/except).  rich_escape the exception: its message embeds the raw name.
            sc.console.print(
                ":exclamation: [bold red] ATTENTION: not a valid DNS name, skipping the "
                f"legacy-GCDN check for it: {rich_escape(str(e))}")
            return ChainResult("", False)
        targets = [normalize(rdata.target) for rdata in answer]
        if not targets:
            return ChainResult("", False)
        sc.debug(f"{rich_escape(name)} is a CNAME to {rich_escape(targets[0])}", level=2)
        name = targets[0]
    sc.console.print(
        ":exclamation: [bold red] ATTENTION: CNAME chain for "
        f"{rich_escape(normalize(start))} exceeds {MAX_CNAME_DEPTH} hops")
    return ChainResult("", False)
