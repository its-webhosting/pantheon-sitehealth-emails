
import os

import script_context as sc


if 'Cloudflare' in sc.config and 'enabled' in sc.config['Cloudflare'] and sc.config['Cloudflare']['enabled']:

    if os.getenv('CLOUDFLARE_EMAIL') is not None:
        sc.config['Cloudflare']['member_email'] = os.getenv('CLOUDFLARE_EMAIL')
    if os.getenv('CLOUDFLARE_API_KEY') is not None:
        sc.config['Cloudflare']['member_api_key'] = os.getenv('CLOUDFLARE_API_KEY')

    from .ips import get_cloudflare_ips
    sc.plugin_context['plugin.cloudflare'] = {}
    sc.hooks['setup'].append({ 'name': 'plugin.cloudflare.ips.get_cloudflare_ips', 'func': get_cloudflare_ips})
