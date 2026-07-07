
import sys
import ipaddress

from cloudflare import Cloudflare
from rich.pretty import pprint

import script_context as sc


def get_cloudflare_ips():

    global cloudflare_ipv4_nets, cloudflare_ipv6_nets

    cf = sc.config['Cloudflare']
    api_token = cf.get('api_token')
    if api_token:
        cloudflare = Cloudflare(api_token=api_token)
    else:
        email = cf.get('email')
        api_key = cf.get('api_key')
        if not email or not api_key:
            sys.exit('ERROR: [Cloudflare] is enabled but needs either api_token, '
                     'or both email and api_key.')
        cloudflare = Cloudflare(api_email=email, api_key=api_key)

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
