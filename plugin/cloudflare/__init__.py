
import script_context as sc


# Cloudflare credentials come entirely from the [Cloudflare] config section (email/api_key or the
# preferred api_token); the operator decides in the config file where those values come from
# (literals, <{secret env ...}>, <{secret aws ...}>, ...).  There is no direct-environment
# fallback here.
if 'Cloudflare' in sc.config and 'enabled' in sc.config['Cloudflare'] and sc.config['Cloudflare']['enabled']:

    from .ips import get_cloudflare_ips
    sc.plugin_context['plugin.cloudflare'] = {}
    sc.hooks['setup'].append({ 'name': 'plugin.cloudflare.ips.get_cloudflare_ips', 'func': get_cloudflare_ips})
