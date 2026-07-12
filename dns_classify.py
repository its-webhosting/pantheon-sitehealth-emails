"""Site-level DNS engine: A/AAAA resolution + Cloudflare classification.

Pure data producer for the site_post_dns contract (see CLAUDE.md and
development/2026-07-10-modular-dns-checks/SPEC.md).  Imports only sc +
stdlib + dnspython; NEVER the dash-named core script.  Presentation (notices) lives in
check/dns/, not here.  Named dns_classify (not dns) to avoid shadowing dnspython's `dns`.
"""
import ipaddress
import struct
from typing import NamedTuple

import dns.exception
import dns.name
import dns.resolver
from rich.markup import escape as rich_escape

import script_context as sc


class MalformedNameError(Exception):
    """`hostname` is not a syntactically valid DNS name.

    dnspython raises dns.name.EmptyLabel / LabelTooLong / BadEscape (all dns.exception.
    SyntaxError) and dns.name.NameTooLong (a dns.exception.FormError) for these.  Two more
    escape that class hierarchy: dns.name.IDNAException derives from dns.exception.DNSException
    but NOT from SyntaxError (raised by IDNACodec.decode() on an "xn--" label whose punycode
    tail doesn't decode); and a byte-escape sequence out of range (e.g. the literal text
    "\\300.com", verified live) makes dns.name.from_text's own struct.pack("!B", ...) raise the
    stdlib struct.error -- not a DNSException at all.  None of the four derive from
    dns.resolver.*, so no resolver-exception handler catches them -- and the per-site loop in
    the main script has no try/except, so an escaped one aborts the entire run (a single
    malformed Pantheon domain id -- or, for the CNAME-chain walk, a malformed name from an
    arbitrary Cloudflare `origins` string -- would take down an --all run).  resolve() converts
    them here, ONCE, at the single DNS seam, so no caller can forget them.
    """


def resolve(hostname: str, rrtype: str):
    """The one seam over dns.resolver.resolve; tests monkeypatch dns_classify.resolve.

    Raises MalformedNameError for a syntactically invalid name (see that class).  Every other
    dnspython exception (NoAnswer/NXDOMAIN/NoNameservers/Timeout) propagates unchanged to the
    caller, which knows what each one means.
    """
    try:
        return dns.resolver.resolve(hostname, rrtype)
    except (dns.exception.SyntaxError, dns.name.NameTooLong, dns.name.IDNAException,
            struct.error) as e:
        raise MalformedNameError(f"{hostname}: {type(e).__name__}") from e


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
        except MalformedNameError as e:
            # Returns immediately -- if the *name* is malformed the second rrtype lookup fails
            # identically, and one ATTENTION line is enough.  rich_escape BOTH hostname and e:
            # e's message embeds the raw hostname, so leaving it unescaped would put the
            # unescaped name straight back into a rich-markup string.
            sc.console.print(
                f":exclamation: [bold red] ATTENTION: {rich_escape(str(hostname))} is not a "
                f"valid DNS name ({rich_escape(str(e))}); it cannot be in DNS",
                style="red")
            return 0, 0, False       # definitive -- the caller aggregates this into not_in_dns

    return points_at_cloudflare, points_elsewhere, transient


class DnsFacts(NamedTuple):
    custom_domains: list
    primary_domain: list
    main_fqdn: str
    not_in_dns: list
    fqdns_behind_cloudflare: list
    fqdns_not_behind_cloudflare: list
    behind_cloudflare_not_proxied: list
    proxied_in_multiple_zones: list
    dns_transient: list


def classify_domains(
    domains,
    cloudflare_enabled: bool,
    cf_v4_nets: list,
    cf_v6_nets: list,
    proxied_fqdns,
    fqdn_zone_conflicts: dict,
    fqdn_re,
) -> DnsFacts:
    """Iterate the terminus domain:list result and produce the site_post_dns contract facts.

    Non-dict `domains` -> all-empty DnsFacts (preserves the core's isinstance guard); a
    malformed domain entry (missing keys) is skipped, not fatal.  Console prints are
    observability only (not captured by goldens).

    Classification is driven by the addresses that resolved DEFINITIVELY:

        resolved nothing ── transient only (Timeout/NoNameservers) ─▶ dns_transient (unknown;
        (0 CF, 0 elsewhere)  │                                        retry) -- NO alert, NO CF checks
                             └─ definitive (NXDOMAIN/NoAnswer) ──────▶ not_in_dns (alert) -- points
                                                                       nowhere, so NO CF checks
        resolved >=1 address ─▶ classify on those.  A transient sibling lookup does NOT block
                                this: if any record points at Cloudflare the CF proxy/zone checks
                                still run, and a definitive non-CF address still yields
                                'not behind Cloudflare'.  No transient notice (we did check).
    """
    main_fqdn = ""
    not_in_dns = []
    fqdns_behind_cloudflare = []
    fqdns_not_behind_cloudflare = []
    behind_cloudflare_not_proxied = []
    proxied_in_multiple_zones = []
    dns_transient = []
    custom_domains = []
    primary_domain = []

    if isinstance(domains, dict):
        for d in domains.keys():
            domain = domains[d]
            # .get(): a malformed domain entry (missing keys) is skipped, never a KeyError.
            if not isinstance(domain, dict) or domain.get("type") == "platform":
                continue
            hostname = domain.get("id")
            if not hostname or not fqdn_re.match(hostname):
                # rich_escape the un-validated hostname: it failed fqdn_re, so it is arbitrary
                # and a bracket sequence would otherwise be parsed as rich markup (matches the
                # rich_escape convention in check/cloudflare/cache.py). Console-only.
                sc.console.log(f"[bold red]ERROR: Invalid domain: {rich_escape(str(hostname))}")
                continue
            if domain.get("primary") or main_fqdn == "":
                main_fqdn = hostname

            points_at_cf, points_elsewhere, transient = classify_hostname_dns(
                hostname, cloudflare_enabled, cf_v4_nets, cf_v6_nets)

            if points_at_cf == 0 and points_elsewhere == 0:
                # Nothing resolved.  A transient failure is "unknown -> retry" (P4); a definitive
                # empty (NXDOMAIN/NoAnswer) is "not in DNS" -> alert.  Either way the FQDN points
                # nowhere, so we do NOT run the Cloudflare checks.
                if transient:
                    dns_transient.append(hostname)
                else:
                    sc.console.print(
                        f":exclamation: [bold red] ATTENTION: {hostname} is not in DNS")
                    not_in_dns.append(hostname)
                continue

            # At least one address resolved definitively; classify on those.  A transient sibling
            # lookup does NOT block this -- if any record points at Cloudflare, the CF checks run.
            if cloudflare_enabled:
                if points_at_cf == 0 or points_elsewhere != 0:
                    sc.console.print(
                        f":exclamation: [bold red] ATTENTION: {hostname} is not behind Cloudflare")
                    fqdns_not_behind_cloudflare.append(hostname)
                if points_at_cf > 0:
                    if hostname not in proxied_fqdns:
                        sc.console.print(
                            f":exclamation: [bold red] ATTENTION: {hostname} is behind "
                            "Cloudflare but not proxied")
                        behind_cloudflare_not_proxied.append(hostname)
                    else:
                        fqdns_behind_cloudflare.append(hostname)
                        if hostname in fqdn_zone_conflicts:
                            sc.console.print(
                                f":exclamation: [bold red] ATTENTION: {hostname} is proxied "
                                "through more than one Cloudflare zone")
                            proxied_in_multiple_zones.append(hostname)

        custom_domains = [d for d in domains.keys()
                          if isinstance(domains[d], dict) and domains[d].get("type") == "custom"]
        primary_domain = [d for d in custom_domains if domains[d].get("primary")]

    return DnsFacts(
        custom_domains, primary_domain, main_fqdn, not_in_dns, fqdns_behind_cloudflare,
        fqdns_not_behind_cloudflare, behind_cloudflare_not_proxied, proxied_in_multiple_zones,
        dns_transient)


def stuff_dns_contract(site_context, domains, facts: DnsFacts) -> None:
    """Publish every site_post_dns data-contract key from a DnsFacts (see CLAUDE.md).

    Pure mapping (dict writes only), extracted from main() so a value-swap mis-map is
    unit-testable — main() itself is not callable in isolation.  main() calls this immediately
    before invoke_hooks('site_post_dns').
    """
    site_context["domains"] = domains
    site_context["custom_domains"] = facts.custom_domains
    site_context["primary_domain"] = facts.primary_domain
    site_context["main_fqdn"] = facts.main_fqdn
    site_context["fqdns_behind_cloudflare"] = facts.fqdns_behind_cloudflare
    site_context["fqdns_not_behind_cloudflare"] = facts.fqdns_not_behind_cloudflare
    site_context["not_in_dns"] = facts.not_in_dns
    site_context["behind_cloudflare_not_proxied"] = facts.behind_cloudflare_not_proxied
    site_context["proxied_in_multiple_zones"] = facts.proxied_in_multiple_zones
    site_context["dns_transient"] = facts.dns_transient
