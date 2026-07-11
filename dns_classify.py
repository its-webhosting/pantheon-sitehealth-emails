"""Site-level DNS engine: A/AAAA resolution + Cloudflare classification.

Pure data producer for the site_post_dns contract (see CLAUDE.md and
docs/superpowers/specs/2026-07-10-modular-dns-checks-design.md).  Imports only sc +
stdlib + dnspython; NEVER the dash-named core script.  Presentation (notices) lives in
check/dns/, not here.  Named dns_classify (not dns) to avoid shadowing dnspython's `dns`.
"""
import ipaddress
from typing import NamedTuple

import dns.resolver
from rich.markup import escape as rich_escape

import script_context as sc


def resolve(hostname: str, rrtype: str):
    """The one seam over dns.resolver.resolve; tests monkeypatch dns_classify.resolve."""
    return dns.resolver.resolve(hostname, rrtype)


def classify_hostname_dns(
    hostname: str,
    cloudflare_enabled: bool,
    cf_v4_nets: list,
    cf_v6_nets: list,
) -> (int, int, bool):
    """Resolve hostname A/AAAA and count addresses inside/outside the Cloudflare ranges.

    Returns (points_at_cloudflare, points_elsewhere, transient).  Timeout/NoNameservers ->
    transient=True (NOT reported as "not in DNS", P4).  NXDOMAIN/NoAnswer are definitive and
    leave both counts 0 with transient=False (the caller aggregates "not in DNS").
    """
    points_at_cloudflare = 0
    points_elsewhere = 0
    transient = False

    for rrtype, nets in (("A", cf_v4_nets), ("AAAA", cf_v6_nets)):
        try:
            answer = resolve(hostname, rrtype)
            for rdata in answer:
                address = ipaddress.ip_address(rdata.address)
                if cloudflare_enabled and any(address in net for net in nets):
                    points_at_cloudflare += 1
                    sc.console.print(
                        f"{hostname} has [green]Cloudflare IP address {rdata.address}[/green]")
                else:
                    points_elsewhere += 1
                    sc.console.print(
                        f"{hostname} has IP address [red]{rdata.address}[/red]")
        except dns.resolver.NoAnswer:
            sc.console.print(f"No {rrtype} record for {hostname}", style="red")
        except dns.resolver.NXDOMAIN:
            sc.console.print(f"NXDOMAIN for {hostname} ({rrtype})", style="red")
        except (dns.resolver.NoNameservers, dns.resolver.Timeout) as e:
            transient = True
            sc.console.print(
                f"Transient DNS error resolving {hostname} ({rrtype}): {type(e).__name__}",
                style="red")

    return points_at_cloudflare, points_elsewhere, transient
