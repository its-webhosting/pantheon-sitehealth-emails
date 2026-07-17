
import sys
import ipaddress

import cloudflare
from rich.pretty import pprint

import script_context as sc


def get_cloudflare_ips():

    # Reuse the one shared client (built lazily on first use; no hook-ordering dependency).
    client = sc.plugin_context['plugin.cloudflare']['get_client']()

    with sc.console.status('[bold green]Getting Cloudflare IP ranges ...'):
        try:
            cloudflare_ips = client.ips.list()
        # CloudflareError is the base of the SDK's exception tree (APIError, APIConnectionError,
        # APIStatusError, ...), so this catches every way the API itself can fail -- and nothing
        # else.  A bare `except Exception` here relabelled OUR bugs (a renamed attribute, a
        # changed SDK shape) as a Cloudflare outage, sending the operator to check their API
        # token while the real defect sat in this file.  Those now propagate with their
        # traceback.  tests/integration/test_plugin_cloudflare_ips.py guards both halves.
        except cloudflare.CloudflareError as e:
            sys.exit(f'ERROR: Unable to get lists of Cloudflare IPs: {e}')
        if sc.options.verbose > 2:
            sc.debug('Cloudflare IPs:')
            pprint(cloudflare_ips)
        sc.plugin_context['plugin.cloudflare']['cloudflare_ipv4_nets'] = [ipaddress.ip_network(cidr) for cidr in cloudflare_ips.ipv4_cidrs]
        sc.plugin_context['plugin.cloudflare']['cloudflare_ipv6_nets'] = [ipaddress.ip_network(cidr) for cidr in cloudflare_ips.ipv6_cidrs]
