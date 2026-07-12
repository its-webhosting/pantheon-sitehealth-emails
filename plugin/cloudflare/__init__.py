
import script_context as sc


# Cloudflare credentials come entirely from the [Cloudflare] config section (email/api_key or the
# preferred api_token); the operator decides in the config file where those values come from
# (literals, <{secret env ...}>, <{secret aws ...}>, ...).  There is no direct-environment
# fallback here.
if 'Cloudflare' in sc.config and 'enabled' in sc.config['Cloudflare'] and sc.config['Cloudflare']['enabled']:

    from .client import get_client
    from .ips import get_cloudflare_ips
    from .fqdns import update_and_load_proxied_fqdns

    # Expose the shared-client accessor in the state bag so ips.py / fqdns.py can reach it without
    # importing this package (keeps them standalone-loadable) and without any hook-ordering
    # dependency -- the client is built lazily on first use, whichever hook runs first.
    bag = sc.plugin_context.setdefault('plugin.cloudflare', {})
    bag['get_client'] = get_client

    sc.add_hook('setup', {'name': 'plugin.cloudflare.ips.get_cloudflare_ips',
                          'func': get_cloudflare_ips})
    sc.add_hook('setup', {'name': 'plugin.cloudflare.fqdns.update_and_load_proxied_fqdns',
                          'func': update_and_load_proxied_fqdns})
