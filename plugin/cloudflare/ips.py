
import sys
import ipaddress

from rich.pretty import pprint

import script_context as sc


def get_cloudflare_ips():

    # Reuse the one shared client (built lazily on first use; no hook-ordering dependency).
    cloudflare = sc.plugin_context['plugin.cloudflare']['get_client']()

    with sc.console.status('[bold green]Getting Cloudflare IP ranges ...'):
        try:
            cloudflare_ips = cloudflare.ips.list()
        except Exception as e:
            sys.exit(f'ERROR: Unable to get lists of Cloudflare IPs: {e}')
        if sc.options.verbose > 2:
            sc.debug('Cloudfare IPs:')
            pprint(cloudflare_ips)
        sc.plugin_context['plugin.cloudflare']['cloudflare_ipv4_nets'] = [ipaddress.ip_network(cidr) for cidr in cloudflare_ips.ipv4_cidrs]
        sc.plugin_context['plugin.cloudflare']['cloudflare_ipv6_nets'] = [ipaddress.ip_network(cidr) for cidr in cloudflare_ips.ipv6_cidrs]
