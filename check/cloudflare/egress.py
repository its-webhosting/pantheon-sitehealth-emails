"""Egress-IP allowlist check (setup hook, once per run).

Before any site cache checks run, verify this host's external IP address(es) appear in an
institutional Cloudflare list (IPs/CIDRs) so cache results are not skewed by challenges
or other rules applied to outside networks.  Both IP families are verified (D4): a family
with no connectivity at all is skipped with a console note; finding NO address at all, an
address that is not on the list, or any allowlist-fetch problem is fatal.

Runs only on report paths (full report or --only-warn): --update, --import-older-metrics,
--create-tables, and --allow-any-source-ip all skip it.  NOTE the --create-tables guard is
REQUIRED, not defensive: setup hooks run on that path before it exits.

Discovery decision tree, per family (probes cascade on any failure):

    https://1.1.1.1/cdn-cgi/trace  /  https://[2606:4700:4700::1111]/cdn-cgi/trace
        └─ parse the `ip=` line
    https://ip-check-perf.radar.cloudflare.com/     (JSON: ip_address)
    https://ifconfig.me/ip                          (bare IP body)
        └─ hostname fallbacks force the family via a local_address-bound transport;
           every answer is validated to be an address OF THAT family (the backstop for
           any local_address/happy-eyeballs subtlety).
"""

import ipaddress
import json
import sys

import cloudflare
import httpx

import script_context as sc

from .cfg import cachecheck_config

TRACE_URLS = {
    4: "https://1.1.1.1/cdn-cgi/trace",
    6: "https://[2606:4700:4700::1111]/cdn-cgi/trace",
}
FALLBACK_RADAR = "https://ip-check-perf.radar.cloudflare.com/"  # JSON: ip_address
# The bare / path of ifconfig.me content-negotiates on User-Agent and can return HTML;
# /ip always returns the bare address:
FALLBACK_IFCONFIG = "https://ifconfig.me/ip"
LOCAL_ADDR = {4: "0.0.0.0", 6: "::"}


def _parse_trace(text: str):  # -> str | None
    for line in text.splitlines():
        if line.startswith("ip="):
            return line[3:].strip()
    return None


def _parse_radar(text: str):  # -> str | None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data.get("ip_address") if isinstance(data, dict) else None


def _parse_ifconfig(text: str):  # -> str | None
    return text.strip() or None


_ENDPOINTS = {
    family: (
        (TRACE_URLS[family], _parse_trace),
        (FALLBACK_RADAR, _parse_radar),
        (FALLBACK_IFCONFIG, _parse_ifconfig),
    )
    for family in (4, 6)
}


def _probe(url: str, family: int, timeout: float, user_agent: str):  # -> str | None
    """GET one probe endpoint over the given IP family; body text, or None on any
    failure (connection-level failures cascade to the next endpoint)."""
    try:
        transport = httpx.HTTPTransport(local_address=LOCAL_ADDR[family])
        with httpx.Client(transport=transport, timeout=timeout, trust_env=False,
                          headers={"user-agent": user_agent}) as client:
            response = client.get(url)
    except httpx.HTTPError:
        return None
    except OSError:  # e.g. no IPv6 support at the socket level
        return None
    if response.status_code != 200:
        return None
    return response.text


probe = _probe  # module attribute = the egress-check monkeypatch seam


def _discover_ip(family: int, timeout: float, user_agent: str):  # -> str | None
    """This host's external IPv4/IPv6 address via the probe chain; None when the family
    has no working endpoint at all (= no connectivity, skipped by the caller)."""
    for url, parser in _ENDPOINTS[family]:
        text = probe(url, family, timeout, user_agent)
        if text is None:
            continue
        ip = parser(text)
        if ip is None:
            sc.debug(f"Egress probe {url} returned no usable IPv{family} address", level=2)
            continue
        try:
            address = ipaddress.ip_address(ip.strip())
        except ValueError:
            sc.debug(f"Egress probe {url} returned unparseable address {ip!r}", level=2)
            continue
        if address.version != family:
            # A mismatched-family answer counts as probe failure (the backstop for the
            # local_address family-pinning caveat in the module docstring):
            sc.debug(f"Egress probe {url} answered with an IPv{address.version} address "
                     f"while probing IPv{family}; ignoring", level=2)
            continue
        sc.debug(f"Egress IPv{family} address {address} (via {url})")
        return str(address)
    return None


def _fetch_allowlist(cfg: dict) -> list:
    """The configured Cloudflare list's entries as ip_network objects.  Any API error,
    a missing list, or a list with no IP entries is fatal."""
    account_id = cfg["account_id"]
    list_name = cfg["list_name"]
    client = sc.plugin_context["plugin.cloudflare"]["get_client"]()
    try:
        lists = list(client.rules.lists.list(account_id=account_id))
    except cloudflare.CloudflareError as e:
        sys.exit(f"ERROR: unable to fetch the Cloudflare lists for account {account_id}: "
                 f"{e}  (the credentials may lack the \"Account Filter Lists: Read\" scope)")
    matches = [l for l in lists if getattr(l, "name", None) == list_name]
    if not matches:
        sys.exit(f"ERROR: Cloudflare list '{list_name}' was not found in account "
                 f"{account_id}.  Check [Cloudflare.cachecheck].list_name and the "
                 f"credentials' \"Account Filter Lists: Read\" scope.")
    try:
        items = list(client.rules.lists.items.list(account_id=account_id,
                                                   list_id=matches[0].id))
    except cloudflare.CloudflareError as e:
        sys.exit(f"ERROR: unable to fetch the items of Cloudflare list '{list_name}' "
                 f"(account {account_id}): {e}")
    networks = []
    for item in items:
        ip = getattr(item, "ip", None)
        if not ip:
            sc.console.print(f"[yellow]Ignoring a non-IP entry in Cloudflare list "
                             f"'{list_name}' (only IP lists make sense here)")
            continue
        try:
            networks.append(ipaddress.ip_network(ip, strict=False))
        except ValueError:
            sc.console.print(f"[yellow]Ignoring unparseable entry {ip!r} in Cloudflare "
                             f"list '{list_name}'")
    if not networks:
        sys.exit(f"ERROR: Cloudflare list '{list_name}' (account {account_id}) contains "
                 f"no IP entries; the egress-IP check can never pass.  Populate the list "
                 f"or run with --allow-any-source-ip.")
    return networks


def check_egress_ip() -> None:
    """The setup hook.  Fatal unless every IP family with connectivity egresses from an
    address on the configured allowlist."""
    options = sc.options
    if (options.update or options.import_older_metrics or options.create_tables
            or options.allow_any_source_ip):
        sc.debug("Skipping the egress-IP allowlist check (not a report run, or "
                 "--allow-any-source-ip was given)")
        return
    cfg = cachecheck_config()
    with sc.console.status("[bold green]Verifying this host's egress IP addresses "
                           "against the Cloudflare allowlist"):
        ips = {}
        for family in (4, 6):
            ips[family] = _discover_ip(family, cfg["timeout"], cfg["user_agent"])
            if ips[family] is None:
                sc.console.print(f"[yellow]No IPv{family} connectivity detected; "
                                 f"skipping the IPv{family} egress check")
        if not any(ips.values()):
            sys.exit("ERROR: could not determine this host's external IP address "
                     "(all probe endpoints failed for both IPv4 and IPv6)")
        networks = _fetch_allowlist(cfg)
        for family, ip in ips.items():
            if ip is None:
                continue
            address = ipaddress.ip_address(ip)
            if not any(address in net for net in networks if net.version == family):
                sys.exit(f"ERROR: this host's IPv{family} egress address {ip} is not in "
                         f"Cloudflare list '{cfg['list_name']}' (account "
                         f"{cfg['account_id']}).  Cache checks from here would see "
                         f"challenge/external behavior.  Run from an allow-listed "
                         f"network, add this address to the list, or pass "
                         f"--allow-any-source-ip.")
    sc.console.print("Egress IP allowlist check passed: "
                     + ", ".join(f"IPv{family} {ip}"
                                 for family, ip in ips.items() if ip))
