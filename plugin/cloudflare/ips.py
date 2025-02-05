
import sys
import ipaddress

from cloudflare import Cloudflare
from rich.pretty import pprint

import script_context as sc


def get_cloudflare_ips():

    global cloudflare_ipv4_nets, cloudflare_ipv6_nets

    cloudflare = Cloudflare(
        api_email=sc.config['Cloudflare']['member_email'],
        api_key=sc.config['Cloudflare']['member_api_key']
    )

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


def get_cloudflare_ipv4_nets():
    return cloudflare_ipv4_nets


def get_cloudflare_ipv6_nets():
    return cloudflare_ipv6_nets
